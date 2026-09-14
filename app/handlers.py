import logging
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.text_decorations import html_decoration

from . import git, wiki
from .bot import main_keyboard
from .config import settings
from .llm import LLMError, LLMService

logger = logging.getLogger(__name__)

esc = html_decoration.quote

router = Router()

HELP_TEXT = (
    "🤖 <b>karpaty-bot</b> — интерфейс к базе знаний mozg\n\n"
    "💭 <b>Новая мысль</b> — просто напишите текст, "
    "бот сохранит исходник и постарается аккуратно уложить мысль в Wiki.\n"
    "📥 <b>Ingest</b> — /ingest, затем пришлите внешний материал.\n"
    "🔎 <b>Спросить Wiki</b> — /ask, затем вопрос по базе знаний.\n"
    "🕘 <b>Последнее</b> — /recent, последние записи wiki/log.md.\n\n"
    "Команды: /capture /ingest /ask /recent /status /cancel"
)


class Mode(StrEnum):
    CAPTURE = "capture"
    INGEST = "ingest"
    ASK = "ask"


# In-memory режимы (Раздел 14 ТЗ). После перезапуска по умолчанию — capture.
_client_modes: dict[int, Mode] = {}


def set_mode(chat_id: int, mode: Mode) -> None:
    _client_modes[chat_id] = mode


def clear_mode(chat_id: int) -> None:
    _client_modes.pop(chat_id, None)


def get_mode(chat_id: int) -> Mode:
    return _client_modes.get(chat_id, Mode.CAPTURE)


BUTTON_TO_MODE = {
    "💭 Новая мысль": Mode.CAPTURE,
    "📥 Ingest": Mode.INGEST,
    "🔎 Спросить Wiki": Mode.ASK,
}


async def perform_capture(
    root: Path,
    text: str,
    *,
    kind: str = "user_thought",
    message_id: int | None = None,
    llm: LLMService | None = None,
    when: datetime | None = None,
) -> dict:
    """Пайплайн Capture (Разделы 20-27, 38).

    Возвращает итог для ответа пользователю: summary, created, updated, related.
    """
    if settings.git_enabled:
        git.pull(root)

    raw_rel = wiki.save_raw_message(
        root, text, kind, message_id=message_id, when=when
    )
    llm = llm or LLMService()

    agents = wiki.read_agents(root)
    analysis = await llm.analyze_topic(agents, text, wiki.list_wiki_pages(root))

    related = wiki.search_wiki(root, analysis.search_terms)
    related_pages = [(path, wiki.read_wiki_page(root, path)) for path, _ in related]

    types = list(analysis.possible_types) or [analysis.likely_page_type]
    if analysis.likely_page_type not in types:
        types.append(analysis.likely_page_type)
    templates = {name: wiki.read_template(root, name) for name in types}

    plan = await llm.build_wiki_plan(agents, text, related_pages, templates)

    created: list[str] = []
    updated: list[str] = []
    related_for_reply: list[str] = []

    for action in plan.actions:
        if action.action == "none":
            continue
        related_for_reply.extend(action.related_paths)
        if action.action == "create":
            try:
                rel = wiki.create_page(
                    root, action.page_type, action.area, action.title, action.content
                )
                created.append(rel)
            except wiki.PageExistsError:
                rel = wiki.page_rel_path(action.page_type, action.area, action.title)
                try:
                    wiki.update_page(root, rel, action.content)
                    updated.append(rel)
                except wiki.WikiError:
                    logger.warning("конфликт при сохранении %s пропущен", rel)
        else:  # update
            if not action.existing_path:
                continue
            try:
                wiki.update_page(root, action.existing_path, action.content)
                updated.append(action.existing_path)
            except wiki.WikiError:
                logger.warning("обновление %s отклонено", action.existing_path)

    wiki.sync_index(root, created=created, updated=updated)

    significant = kind == "external_source" or any(
        p.split("/")[-2] in {"synthesis", "decisions"} for p in (*created, *updated)
    )
    if significant:
        wiki.append_log(
            root,
            source_rel=raw_rel,
            created=created,
            updated=updated,
            when=when,
        )
    if settings.git_enabled:
        changed = [
            raw_rel,
            *(f"wiki/{p}" for p in created),
            *(f"wiki/{p}" for p in updated),
            "wiki/index.md",
        ]
        if significant:
            changed.append("wiki/log.md")
        git.commit(root, changed, git.changed_commit_message(kind))
        git.push(root)
    return {
        "summary": plan.summary,
        "created": created,
        "updated": updated,
        "related": related_for_reply,
        "concepts": analysis.related_concepts,
        "raw": raw_rel,
    }


def _format_capture_result(result: dict) -> str:
    lines = ["✅ Сохранено"]
    if result["created"]:
        lines.append("\n<b>Создано:</b>")
        lines += [f"• {esc(Path(p).stem)}" for p in result["created"]]
    if result["updated"]:
        lines.append("\n<b>Обновлено:</b>")
        lines += [f"• {esc(Path(p).stem)}" for p in result["updated"]]
    if not result["created"] and not result["updated"]:
        lines.append("\nНичего не изменено в Wiki.")
    concepts = [c for c in result["concepts"] if c] + result["related"]
    if concepts:
        lines.append("\n<b>Связано с:</b>")
        lines += [f"• {esc(c)}" for c in dict.fromkeys(concepts)]
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    set_mode(message.chat.id, Mode.CAPTURE)
    await message.answer(
        "👋 Привет! Я бот-интерфейс к базе знаний <b>mozg</b>.\n"
        "Просто напишите мысль — я сохраню её и обновлю Wiki.",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode=ParseMode.HTML)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    clear_mode(message.chat.id)
    await message.answer("⛔ Отменено. Возвращаюсь в режим «Новая мысль».")


@router.message(Command("capture"))
async def cmd_capture(message: Message) -> None:
    set_mode(message.chat.id, Mode.CAPTURE)
    await message.answer("💭 Режим «Новая мысль». Напишите что-нибудь.")


@router.message(Command("ingest"))
async def cmd_ingest(message: Message) -> None:
    set_mode(message.chat.id, Mode.INGEST)
    await message.answer("📥 Режим Ingest. Пришлите внешний материал (текст).")


@router.message(Command("ask"))
async def cmd_ask(message: Message) -> None:
    set_mode(message.chat.id, Mode.ASK)
    await message.answer("🔎 Режим вопроса. Задайте вопрос по Wiki.")


async def perform_ask(root: Path, question: str, llm: LLMService | None = None) -> dict:
    """Режим /ask (Раздел 13). Wiki не изменяется."""
    llm = llm or LLMService()
    agents = wiki.read_agents(root)
    analysis = await llm.analyze_topic(agents, question, wiki.list_wiki_pages(root))
    related = wiki.search_wiki(root, analysis.search_terms, limit=8)
    pages = [(path, wiki.read_wiki_page(root, path)) for path, _ in related]
    answer = await llm.answer_from_wiki(agents, question, pages)
    return {
        "answer": answer.answer,
        "sources": answer.used_sources,
        "knows": answer.knows,
    }


def _status_lines() -> list[str]:
    lines = ["ℹ️ <b>Статус системы</b>"]
    root = settings.wiki_root
    if not root:
        lines.append("❌ WIKI_ROOT не задан (заполните .env)")
        return lines
    lines.append(f"📍 WIKI_ROOT: <code>{esc(str(root))}</code>")
    try:
        wiki.check_structure(root)
        lines.append("✅ Структура Wiki — ОК")
    except wiki.WikiStructureError as exc:
        lines.append(f"❌ {exc}")
    try:
        agents = wiki.read_agents(root)
        lines.append(f"✅ AGENTS.md читается ({len(agents)} симв.)")
    except wiki.WikiError as exc:
        lines.append(f"❌ AGENTS.md: {exc}")
    templates = [
        p.stem
        for p in (root / "templates").glob("*.md")
        if p.stem in wiki.PAGE_TYPE_DIRS
    ]
    lines.append(f"✅ templates: {esc(', '.join(sorted(templates)) or '(нет)')}")
    sources = root / "raw" / "sources"
    raw_count = len(list(sources.glob("*.md"))) if sources.is_dir() else 0
    lines.append(f"✅ raw/sources: {raw_count} файлов")
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        lines.append(f"✅ LLM настроен: {settings.llm_model}")
    else:
        lines.append("⚠️ LLM не настроен (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL)")
    lines.append(f"GIT_ENABLED={str(settings.git_enabled).lower()}")
    if settings.git_enabled:
        if git.is_repo(root):
            lines.append("✅ Git repository — ОК")
        else:
            lines.append("❌ Git repository не найден в WIKI_ROOT")
    return lines


def _recent_text() -> str:
    return "🕘 <b>Последние записи:</b>\n\n" + esc(wiki.recent_log(settings.wiki_root))


@router.message(Command("recent"))
async def cmd_recent(message: Message) -> None:
    await message.answer(_recent_text(), parse_mode=ParseMode.HTML)


@router.message(F.text == "🕘 Последнее")
async def on_recent_button(message: Message) -> None:
    await message.answer(_recent_text(), parse_mode=ParseMode.HTML)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    await message.answer("\n".join(_status_lines()), parse_mode=ParseMode.HTML)


@router.message(F.text.in_(BUTTON_TO_MODE))
async def on_mode_button(message: Message) -> None:
    mode = BUTTON_TO_MODE[message.text or ""]
    set_mode(message.chat.id, mode)
    texts = {
        Mode.CAPTURE: "💭 Режим «Новая мысль».",
        Mode.INGEST: "📥 Режим Ingest.",
        Mode.ASK: "🔎 Режим вопроса.",
    }
    await message.answer(texts[mode])


@router.message(F.text)
async def on_text(message: Message) -> None:
    mode = get_mode(message.chat.id)
    text = (message.text or "").strip()
    if not text:
        return

    if mode == Mode.CAPTURE:
        kind = "user_thought"
    elif mode == Mode.INGEST:
        kind = "external_source"
    else:  # Mode.ASK
        try:
            result = await perform_ask(settings.wiki_root, text)
        except LLMError:
            await message.answer("⚠️ Не удалось ответить: LLM недоступна.")
        except wiki.WikiError as exc:
            await message.answer(f"⚠️ Ошибка при обращении к Wiki: {exc}")
        else:
            lines = [esc(result["answer"])]
            if result["sources"]:
                lines.append("\n<b>Источники:</b>")
                lines += [f"• {esc(s)}" for s in dict.fromkeys(result["sources"])]
            await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    try:
        result = await perform_capture(
            settings.wiki_root,
            text,
            kind=kind,
            message_id=message.message_id,
        )
    except LLMError:
        logger.warning("LLM недоступна при обработке сообщения")
        await message.answer(
            "⚠️ Исходное сообщение сохранено,\n"
            "но обработать его в Wiki не удалось."
        )
    except wiki.WikiError as exc:
        logger.warning("wiki error: %s", exc)
        await message.answer(f"⚠️ Не удалось обработать сообщение: {exc}")
    except git.GitError as exc:
        logger.warning("git error: %s", exc)
        await message.answer(f"⚠️ Git-синхронизация не удалась: {exc}")
    else:
        await message.answer(
            _format_capture_result(result), parse_mode=ParseMode.HTML
        )
    finally:
        if mode == Mode.INGEST:
            set_mode(message.chat.id, Mode.CAPTURE)