import json

import pytest
from pydantic import ValidationError

from app.schemas import WikiAction, WikiPlan


def test_wiki_action_create_valid():
    action = WikiAction(
        action="create",
        page_type="idea",
        area="business",
        title="Идея",
        content="# Идея\n",
    )
    assert action.action == "create"


def test_wiki_action_update_requires_path():
    with pytest.raises(ValidationError):
        WikiAction(action="update", page_type="gap", title="x", content="y")


def test_wiki_action_requires_title_content():
    with pytest.raises(ValidationError):
        WikiAction(action="create", page_type="idea", title="", content="")
    with pytest.raises(ValidationError):
        WikiAction(action="update", page_type="idea", existing_path="a.md", title="", content="")


def test_wiki_action_none_needs_nothing():
    action = WikiAction(action="none")
    assert action.title == ""


def test_wiki_action_invalid_page_type():
    with pytest.raises(ValidationError):
        WikiAction(
            action="create",
            page_type="comparison",
            title="x",
            content="y",
        )


def test_wiki_plan_parses_from_json():
    raw = {
        "summary": "новая идея про регрессию",
        "actions": [
            {
                "action": "create",
                "page_type": "idea",
                "area": "business",
                "title": "Регрессионные тесты RAG",
                "content": "# Регрессионные тесты RAG\n\nauto-запуск",
                "related_paths": ["areas/business/concepts/rag.md"],
            },
            {
                "action": "none",
                "page_type": "idea",
                "area": "business",
                "title": "",
                "content": "",
            },
        ],
    }
    plan = WikiPlan.model_validate_json(json.dumps(raw))
    assert len(plan.actions) == 2
    assert plan.actions[0].action == "create"
    assert plan.actions[1].action == "none"