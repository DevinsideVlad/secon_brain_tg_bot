import json
from types import SimpleNamespace

import pytest

from app.llm import LLMError, LLMService
from app.schemas import TopicAnalysis, WikiAnswer, WikiPlan


def _fake_client(payload: str):
    """Минимальный фейковый OpenAI-клиент, отвечающий заданным JSON."""
    message = SimpleNamespace(content=payload)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])

    class _Completions:
        async def create(self, **_kwargs):
            return response

    class _Chat:
        completions = _Completions()

    return SimpleNamespace(chat=_Chat())


VALID_PLAN = {
    "summary": "решение и gap",
    "actions": [
        {
            "action": "create",
            "page_type": "decision",
            "area": "business",
            "title": "Faster-Whisper",
            "content": "# Faster-Whisper\n\nиспользовать",
        },
        {
            "action": "create",
            "page_type": "gap",
            "area": "business",
            "title": "CPU сервера",
            "content": "# CPU сервера\n\nпроверить",
        },
    ],
}


@pytest.mark.asyncio
async def test_build_wiki_plan_parses():
    svc = LLMService(client=_fake_client(json.dumps(VALID_PLAN)), model="test")
    plan = await svc.build_wiki_plan(
        agents="# AGENTS\n",
        message="Есть идея про регрессию",
        related_pages=[("areas/business/concepts/rag.md", "# RAG\nтекст")],
        templates={"idea.md": "# {title}\n"},
    )
    assert isinstance(plan, WikiPlan)
    assert [a.action for a in plan.actions] == ["create", "create"]
    assert plan.actions[0].page_type == "decision"


@pytest.mark.asyncio
async def test_analyze_topic_parses():
    payload = {
        "topic": "регрессия RAG",
        "search_terms": ["rag", "тест", "регрессия"],
        "related_concepts": ["обновление базы"],
        "likely_page_type": "idea",
    }
    svc = LLMService(client=_fake_client(json.dumps(payload)), model="test")
    result = await svc.analyze_topic("# AGENTS\n", "новое сообщение", ["a.md"])
    assert isinstance(result, TopicAnalysis)
    assert "rag" in result.search_terms


@pytest.mark.asyncio
async def test_answer_from_wiki_parses():
    payload = {"answer": "вот так", "used_sources": ["a.md"], "knows": True}
    svc = LLMService(client=_fake_client(json.dumps(payload)), model="test")
    answer = await svc.answer_from_wiki("rules", "вопрос", [("a.md", "text")])
    assert isinstance(answer, WikiAnswer)
    assert answer.knows is True


@pytest.mark.asyncio
async def test_invalid_json_raises_llm_error():
    svc = LLMService(client=_fake_client("not json at all"), model="test")
    with pytest.raises(LLMError):
        await svc.build_wiki_plan("r", "m", [], {})


@pytest.mark.asyncio
async def test_schema_mismatch_raises_llm_error():
    payload = json.dumps({"topic": "x"})  # не подходит под WikiPlan
    svc = LLMService(client=_fake_client(payload), model="test")
    with pytest.raises(LLMError):
        await svc.build_wiki_plan("r", "m", [], {})


@pytest.mark.asyncio
async def test_network_error_raises_llm_error():
    class _Boom:
        async def create(self, **_kwargs):
            raise ConnectionError("network down")

    class _Completions:
        completions = _Boom()

    client = SimpleNamespace(chat=_Completions())
    svc = LLMService(client=client, model="test")
    with pytest.raises(LLMError):
        await svc.build_wiki_plan("r", "m", [], {})


def test_service_requires_config():
    from unittest.mock import patch

    from app import llm as llm_module

    with patch.object(llm_module.settings, "llm_base_url", ""), patch.object(
        llm_module.settings, "llm_api_key", ""
    ), patch.object(llm_module.settings, "llm_model", ""):
        with pytest.raises(LLMError):
            LLMService()