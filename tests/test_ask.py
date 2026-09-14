from unittest.mock import patch

import pytest

from app.handlers import _status_lines, perform_ask
from app.schemas import WikiAnswer


class AskStubLLM:
    def __init__(self, analysis, answer):
        self.analysis = analysis
        self.answer = answer

    async def analyze_topic(self, agents, message, wiki_pages):
        return self.analysis

    async def answer_from_wiki(self, agents, question, related_pages):
        self.seen_pages = related_pages
        return self.answer


@pytest.mark.asyncio
async def test_ask_returns_answer_and_sources(tmp_wiki):
    analysis = type(
        "A", (), {"search_terms": ["тест", "rag"], "related_concepts": []}
    )()
    stub = AskStubLLM(
        analysis,
        WikiAnswer(
            answer="Ответ про RAG",
            used_sources=["areas/business/concepts/rag.md"],
            knows=True,
        ),
    )
    result = await perform_ask(tmp_wiki, "Что по тестам RAG?", llm=stub)
    assert result["answer"] == "Ответ про RAG"
    assert result["sources"] == ["areas/business/concepts/rag.md"]
    assert result["knows"]


@pytest.mark.asyncio
async def test_ask_does_not_modify_wiki(tmp_wiki):
    from pathlib import Path

    before = {
        p.relative_to(tmp_wiki)
        for p in Path(tmp_wiki).rglob("*")
        if p.is_file()
    }
    analysis = type("A", (), {"search_terms": ["нет"], "related_concepts": []})()
    stub = AskStubLLM(analysis, WikiAnswer(answer="не знаю", knows=False))
    await perform_ask(tmp_wiki, "вопрос", llm=stub)
    after = {
        p.relative_to(tmp_wiki)
        for p in Path(tmp_wiki).rglob("*")
        if p.is_file()
    }
    assert before == after


def test_status_lines_with_ok_structure(tmp_wiki):
    with patch("app.handlers.settings.wiki_root", tmp_wiki), patch(
        "app.handlers.settings.llm_base_url", "https://x"
    ), patch("app.handlers.settings.llm_api_key", "k"), patch(
        "app.handlers.settings.llm_model", "m"
    ):
        lines = _status_lines()
    joined = "\n".join(lines)
    assert "✅ Структура Wiki — ОК" in joined
    assert "✅ AGENTS.md" in joined
    assert "✅ LLM настроен: m" in joined
    assert "GIT_ENABLED=false" in joined


def test_status_lines_missing_root():
    with patch("app.handlers.settings.wiki_root", ""):
        lines = _status_lines()
    assert "WIKI_ROOT не задан" in "\n".join(lines)