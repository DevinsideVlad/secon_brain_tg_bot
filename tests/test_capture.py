import pytest
from pydantic import ValidationError

from app.handlers import perform_capture
from app.llm import LLMError
from app.schemas import TopicAnalysis, WikiAction, WikiPlan


class FakeAnalysis(TopicAnalysis):
    pass


class StubLLM:
    """Подставной LLM без сети для тестов пайплайна."""

    def __init__(self, analysis=None, plan=None, ask_answer=None):
        self.analysis = analysis or FakeAnalysis(
            topic="регрессия RAG",
            search_terms=["регрессия", "rag"],
            related_concepts=["RAG"],
            likely_page_type="idea",
            possible_types=["idea"],
        )
        self.plan = plan
        self.ask_answer = ask_answer

    async def analyze_topic(self, agents, message, wiki_pages):
        self.last_agents = agents
        return self.analysis

    async def build_wiki_plan(self, agents, message, related_pages, templates):
        if self.plan is not None:
            return self.plan

        def _stub(**kw):
            defaults = dict(
                action="create", page_type="idea", area="business",
                title="Регрессия RAG", content="# Регрессия RAG\n\nтекст",
            )
            defaults.update(kw)
            return WikiAction(**defaults)

        return WikiPlan(
            summary="сохранить идею",
            actions=[
                _stub(title="Регрессия RAG"),
                _stub(action="none"),
            ],
        )

    async def answer_from_wiki(self, agents, question, related_pages):
        return self.ask_answer


@pytest.mark.asyncio
async def test_capture_creates_page_and_updates_index(tmp_wiki):
    result = await perform_capture(
        tmp_wiki, "Есть идея про регрессию RAG", llm=StubLLM()
    )
    assert result["created"][0] == "areas/business/ideas/регрессия-rag.md"
    assert (tmp_wiki / "wiki" / result["created"][0]).is_file()
    index = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "### Business" in index
    assert "#### Ideas" in index
    assert "- [[areas/business/ideas/регрессия-rag]] — текст" in index
    log = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "регрессия-rag" not in log


@pytest.mark.asyncio
async def test_capture_decision_is_logged(tmp_wiki):
    stub = StubLLM(
        plan=WikiPlan(
            summary="решение",
            actions=[
                WikiAction(
                    action="create",
                    page_type="decision",
                    area="business",
                    title="Использовать RAG",
                    content="# Решение\n\nподробности выбора",
                )
            ],
        )
    )
    result = await perform_capture(tmp_wiki, "решение по RAG", llm=stub)
    assert result["created"][0] == "areas/business/decisions/использовать-rag.md"
    index = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "#### Decisions" in index
    log = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "использовать-rag" in log


@pytest.mark.asyncio
async def test_capture_saves_raw_before_analysis(tmp_wiki):
    class BoomLLM(StubLLM):
        async def analyze_topic(self, agents, message, wiki_pages):
            raise LLMError("нет модели")

    with pytest.raises(LLMError):
        await perform_capture(tmp_wiki, "мысль", llm=BoomLLM())
    sources = list((tmp_wiki / "raw" / "sources").glob("*.md"))
    assert len(sources) == 1


@pytest.mark.asyncio
async def test_capture_update_existing(tmp_wiki):
    stub = StubLLM(
        plan=WikiPlan(
            summary="дополнить",
            actions=[
                WikiAction(
                    action="update",
                    page_type="concept",
                    area="business",
                    existing_path="areas/business/concepts/rag.md",
                    title="RAG",
                    content="# RAG\n\nполный новый текст страницы",
                )
            ],
        )
    )
    from app.wiki import create_page

    create_page(tmp_wiki, "concept", "business", "RAG", "старая версия")
    result = await perform_capture(tmp_wiki, "мысль", llm=stub)
    assert result["updated"] == ["areas/business/concepts/rag.md"]
    assert (tmp_wiki / "wiki" / "areas" / "business" / "concepts" / "rag.md").read_text(
        encoding="utf-8"
    ) == "# RAG\n\nполный новый текст страницы"


@pytest.mark.asyncio
async def test_capture_ingest_external_kind(tmp_wiki):
    stub = StubLLM()
    result = await perform_capture(tmp_wiki, "статья о RAG", kind="external_source", llm=stub)
    assert result["created"]
    raw_files = list((tmp_wiki / "raw" / "sources").glob("*.md"))
    content = raw_files[0].read_text(encoding="utf-8")
    assert "kind: external_source" in content
    log = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "регрессия-rag" in log


@pytest.mark.asyncio
async def test_capture_rejects_dangerous_update(tmp_wiki):
    stub = StubLLM(
        plan=WikiPlan(
            summary="",
            actions=[
                WikiAction(
                    action="update",
                    page_type="gap",
                    area="business",
                    existing_path="../../AGENTS.md",
                    title="x",
                    content="длинный текст для страницы",
                )
            ],
        )
    )
    result = await perform_capture(tmp_wiki, "мысль", llm=stub)
    assert result["created"] == []
    assert result["updated"] == []
    assert (tmp_wiki / "AGENTS.md").read_text(encoding="utf-8") == (
        tmp_wiki / "AGENTS.md"
    ).read_text(encoding="utf-8")


def test_invalid_plan_rejected_at_schema():
    with pytest.raises(ValidationError):
        WikiAction(action="create", page_type="idea", title="", content="")