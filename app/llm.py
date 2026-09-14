"""LLM — интеллектуальное ядро (Разделы 6-9, 21-22 ТЗ).

LLM принимает решения и возвращает валидируемые структуры.
Python выполняет файловые операции. LLM не получает прямого доступа к FS.
"""

import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from .config import settings
from .schemas import TopicAnalysis, WikiAnswer, WikiPlan

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Ошибка обращения к LLM или невалидный structured output."""


SYSTEM_BASE = (
    "Ты — интеллектуальное ядро Telegram-интерфейса персональной базы знаний. "
    "Твоя задача — понимать смысл сообщений пользователя и планировать изменения "
    "Markdown-Wiki, следуя правилам AGENTS.md. "
    "Отвечай строго валидным JSON нужной структуры, без пояснений вне JSON."
)


def _build_client() -> AsyncOpenAI:
    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        raise LLMError(
            "LLM не настроен: задайте LLM_BASE_URL, LLM_API_KEY, LLM_MODEL в .env"
        )
    return AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)


class LLMService:
    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None):
        self.client = client or _build_client()
        self.model = model or settings.llm_model

    async def _json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("LLM request failed: %s", exc)
            raise LLMError(f"LLM недоступна: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise LLMError("LLM вернула пустой ответ")
        try:
            return schema.model_validate_json(content)
        except Exception as exc:
            logger.warning("invalid structured output: %s", exc)
            raise LLMError(f"LLM вернула невалидный structured output: {exc}") from exc

    async def analyze_topic(
        self,
        agents: str,
        message: str,
        wiki_pages: list[str],
    ) -> TopicAnalysis:
        """Этап 1: LLM понимает тему и даёт поисковые термины (Раздел 21)."""
        system = (
            SYSTEM_BASE
            + "\n\nПравила базы знаний (AGENTS.md):\n"
            + agents
            + "\n\nОпредели тему сообщения, связанные понятия и search_terms "
            "(2-6 коротких терминов для локального поиска по Wiki), "
            "likely_page_type и possible_types (1-3 вероятных типа создаваемых страниц "
            "из набора concept|decision|gap|idea|source|synthesis). "
            'Верни JSON {"topic": ..., "search_terms": [...], '
            '"related_concepts": [...], "likely_page_type": ..., "possible_types": [...]}.'
        )
        page_list = "\n".join(f"- {p}" for p in wiki_pages) or "- (пусто)"
        user = (
            f"Существующие страницы Wiki:\n{page_list}\n\n"
            f"Новое сообщение пользователя:\n{message}"
        )
        analysis = await self._json(system, user, TopicAnalysis)
        assert isinstance(analysis, TopicAnalysis)
        return analysis

    async def build_wiki_plan(
        self,
        agents: str,
        message: str,
        related_pages: list[tuple[str, str]],
        templates: dict[str, str],
    ) -> WikiPlan:
        """Этап 3: формирует окончательный WikiPlan по существующему контексту.

        related_pages: список (относительный путь, содержимое).
        templates: имя -> содержимое template-файла.
        """
        system = (
            SYSTEM_BASE
            + "\n\nПравила базы знаний (AGENTS.md):\n"
            + agents
            + "\n\nСпланируй изменения Wiki. Действуй консервативно: "
            "создавай страницу, когда темы нет в контексте; обновляй существующую, "
            "когда новая мысль дополняет её. Различай идеи/мнения/гипотезы и факты "
            "(Раздел 26). Не превращай мнение пользователя в утверждённый факт. "
            "Если страница уже отражает сообщение полностью — action=none. "
            'Верни JSON {"summary": "...", "actions": [{"action": "create|update|none", '
            '"page_type": "concept|decision|gap|idea|source|synthesis", '
            '"area": "business|personal", "existing_path": "...|null", "title": "...", '
            '"content": "полный markdown", "related_paths": [...]}]}. '
            "Ответ в JSON вложенного объекта — summary, actions. "
            "Одно сообщение может дать несколько actions (Раздел 11). "
            "Относительные пути и title пиши на русском без кавычек-артефактов."
        )
        pages_block = "\n\n".join(f"### {path}\n{content}" for path, content in related_pages)
        if not pages_block:
            pages_block = "(релевантных страниц не найдено)"
        templates_block = "\n\n".join(
            f"### template {name}.md\n{content}" for name, content in templates.items()
        )
        user = (
            f"Новое сообщение:\n{message}\n\n"
            f"## Релевантные страницы Wiki:\n{pages_block}\n\n"
            f"## Доступные templates (оформление):\n{templates_block}"
        )
        plan = await self._json(system, user, WikiPlan)
        assert isinstance(plan, WikiPlan)
        return plan

    async def answer_from_wiki(
        self,
        agents: str,
        question: str,
        related_pages: list[tuple[str, str]],
    ) -> WikiAnswer:
        """Ответ на вопрос по релевантным страницам (/ask, Раздел 13)."""
        system = (
            SYSTEM_BASE
            + "\n\nПравила базы знаний (AGENTS.md):\n"
            + agents
            + "\n\nОтвечай на вопрос пользователя ТОЛЬКО по содержимому приведённых "
            "страниц. Если знания не хватает — честно скажи об этом (knows=false). "
            'Верни JSON {"answer": "...", "used_sources": ["..."], "knows": true|false}.'
        )
        pages_block = "\n\n".join(f"### {path}\n{content}" for path, content in related_pages)
        user = (
            f"Вопрос пользователя:\n{question}\n\n"
            f"## Доступные страницы Wiki:\n{pages_block or '(нет)'}"
        )
        answer = await self._json(system, user, WikiAnswer)
        assert isinstance(answer, WikiAnswer)
        return answer