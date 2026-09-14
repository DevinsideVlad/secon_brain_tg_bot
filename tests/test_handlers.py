from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import handlers as h
from app.wiki import append_log


class FakeMessage:
    def __init__(self, chat_id: int, text: str, message_id: int = 1):
        self.chat = SimpleNamespace(id=chat_id)
        self.text = text
        self.message_id = message_id
        self.answered: str | None = None

    async def answer(self, text: str, **kwargs) -> None:
        self.answered = text


@pytest.mark.asyncio
async def test_ingest_resets_to_capture(tmp_wiki):
    async def fake_capture(root, text, *, kind, message_id=None, llm=None, when=None):
        assert kind == "external_source"
        return {
            "summary": "",
            "created": [],
            "updated": [],
            "related": [],
            "concepts": [],
            "raw": "raw/sources/x.md",
        }

    with patch.object(h, "perform_capture", fake_capture), patch(
        "app.handlers.settings.wiki_root", tmp_wiki
    ):
        h.set_mode(1, h.Mode.INGEST)
        msg = FakeMessage(1, "статья про X")
        await h.on_text(msg)
    assert h.get_mode(1) == h.Mode.CAPTURE
    assert msg.answered is not None


@pytest.mark.asyncio
async def test_ingest_resets_to_capture_on_error(tmp_wiki):
    from app.wiki import WikiError

    async def boom(*args, **kwargs):
        raise WikiError("тест")

    with patch.object(h, "perform_capture", boom), patch(
        "app.handlers.settings.wiki_root", tmp_wiki
    ):
        h.set_mode(1, h.Mode.INGEST)
        msg = FakeMessage(1, "статья")
        await h.on_text(msg)
    assert h.get_mode(1) == h.Mode.CAPTURE


@pytest.mark.asyncio
async def test_capture_mode_stays_capture(tmp_wiki):
    async def fake_capture(root, text, *, kind, message_id=None, llm=None, when=None):
        assert kind == "user_thought"
        return {
            "summary": "",
            "created": [],
            "updated": [],
            "related": [],
            "concepts": [],
            "raw": "raw/sources/x.md",
        }

    with patch.object(h, "perform_capture", fake_capture), patch(
        "app.handlers.settings.wiki_root", tmp_wiki
    ):
        h.set_mode(1, h.Mode.CAPTURE)
        msg = FakeMessage(1, "мысль")
        await h.on_text(msg)
    assert h.get_mode(1) == h.Mode.CAPTURE


@pytest.mark.asyncio
async def test_recent_button_shows_log(tmp_wiki):
    append_log(tmp_wiki, source_rel="raw/sources/x.md", created=["areas/business/ideas/x.md"])
    with patch("app.handlers.settings.wiki_root", tmp_wiki):
        msg = FakeMessage(1, "🕘 Последнее")
        await h.on_recent_button(msg)
    assert "areas/business/ideas/x.md" in (msg.answered or "")
    assert h.get_mode(1) == h.Mode.CAPTURE


def test_recent_button_is_not_fallback_to_capture():
    assert "🕘 Последнее" in h.BUTTON_TO_MODE or True
    assert "🕘 Последнее" not in h.BUTTON_TO_MODE
    assert h.BUTTON_TO_MODE == {
        "💭 Новая мысль": h.Mode.CAPTURE,
        "📥 Ingest": h.Mode.INGEST,
        "🔎 Спросить Wiki": h.Mode.ASK,
    }