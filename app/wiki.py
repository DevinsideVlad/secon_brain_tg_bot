"""Файловый слой работы с WIKI_ROOT (Разделы 19-27 ТЗ).

Код знает контракт структуры Wiki и не зависит от реального содержания.
Именно сюда Python применяет изменения, которые предлагает LLM.
"""

import re
from datetime import datetime
from pathlib import Path

PAGE_TYPE_DIRS: dict[str, str] = {
    "concept": "concepts",
    "decision": "decisions",
    "gap": "gaps",
    "idea": "ideas",
    "source": "sources",
    "synthesis": "synthesis",
}

SEO = {"idea", "decision", "gap", "concept", "source", "synthesis"}


class WikiError(Exception):
    """Базовая ошибка файлового слоя."""


class WikiStructureError(WikiError):
    """WIKI_ROOT не соответствует ожидаемому контракту структуры."""


class UnsafePathError(WikiError):
    """Путь выходит за пределы разрешённой директории."""


class PageNotFoundError(WikiError):
    """Запрошенная страница не найдена."""


class TemplateNotFoundError(WikiError):
    """Запрошенный template не найден."""


class PageExistsError(WikiError):
    """Страница с таким путём уже существует (нужен update)."""


class UnsafePageUpdateError(WikiError):
    """Обновление уничтожило бы основную часть страницы."""


REQUIRED_STRUCTURE = (
    "AGENTS.md",
    "raw/sources/",
    "templates/",
    "wiki/",
    "wiki/areas/",
)


def wiki_dir(wiki_root: Path) -> Path:
    return wiki_root / "wiki"


def check_structure(wiki_root: Path) -> None:
    """Проверяет, что WIKI_ROOT содержит минимально ожидаемую структуру.

    Не создаёт Wiki с нуля (Раздел 19).
    """
    missing = [entry for entry in REQUIRED_STRUCTURE if not (wiki_root / entry).exists()]
    if missing:
        joined = ", ".join(repr(m) for m in missing)
        raise WikiStructureError(f"WIKI_ROOT={wiki_root} не соответствует контракту: нет {joined}")


def read_agents(wiki_root: Path) -> str:
    path = wiki_root / "AGENTS.md"
    if not path.is_file():
        raise WikiError(f"AGENTS.md не найден в {wiki_root}")
    return path.read_text(encoding="utf-8")


def read_template(wiki_root: Path, template_name: str) -> str:
    path = wiki_root / "templates" / f"{template_name}.md"
    if not path.is_file():
        raise TemplateNotFoundError(f"template не найден: {path}")
    return path.read_text(encoding="utf-8")


def list_wiki_pages(wiki_root: Path) -> list[str]:
    """Относительные пути (posix, без 'wiki/') всех .md страниц Wiki."""
    root = wiki_dir(wiki_root)
    pages: list[str] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if rel == "log.md":
            continue
        pages.append(rel)
    return pages


def read_wiki_page(wiki_root: Path, rel_path: str) -> str:
    path = safe_wiki_path(wiki_root, rel_path)
    if not path.is_file():
        raise PageNotFoundError(f"страница не найдена: wiki/{rel_path}")
    return path.read_text(encoding="utf-8")


def safe_wiki_path(wiki_root: Path, rel_path: str) -> Path:
    """Проверяет, что rel_path внутри WIKI_ROOT/wiki без обхода каталогов."""
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise UnsafePathError(f"пустной путь: {rel_path!r}")
    if ".." in rel_path or "\\" in rel_path or "\x00" in rel_path:
        raise UnsafePathError(f"небезопасный путь: {rel_path!r}")
    root = wiki_dir(wiki_root).resolve()
    candidate = (root / rel_path).resolve()
    if not candidate.is_relative_to(root):
        raise UnsafePathError(f"путь выходит за пределы wiki/: {rel_path!r}")
    if rel_path == "log.md":
        raise UnsafePathError("log.md обновляется только через append_log()")
    return candidate


def _slugify(title: str) -> str:
    text = title.strip().lower()
    text = re.sub(r"[\s/\\]+", "-", text)
    text = re.sub(r"[^\w\u0400-\u04ff-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled"


def page_rel_path(page_type: str, area: str, title: str) -> str:
    """Вычисляет относительный путь страницы внутри wiki/ (Раздел 23).

    Путь определяет Python, а не LLM.
    """
    if page_type not in PAGE_TYPE_DIRS:
        raise WikiError(f"неизвестный тип страницы: {page_type}")
    subdir = PAGE_TYPE_DIRS[page_type]
    return (Path("areas") / area / subdir / f"{_slugify(title)}.md").as_posix()


def create_page(
    wiki_root: Path,
    page_type: str,
    area: str,
    title: str,
    content: str,
) -> str:
    """Создаёт страницу wiki/areas/<area>/<dir>/<slug>.md (Раздел 23).

    Возвращает относительный путь (posix). Каталоги создаются лениво.
    """
    rel = page_rel_path(page_type, area, title)
    path = safe_wiki_path(wiki_root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PageExistsError(f"страница уже существует: wiki/{rel}")
    path.write_text(content, encoding="utf-8")
    return rel


def update_page(
    wiki_root: Path,
    rel_path: str,
    content: str,
    min_keep_ratio: float = 0.4,
) -> str:
    """Обновляет существующую страницу (Раздел 24).

    Защита: нельзя заменить страницу на обрывок, который уничтожил бы
    основную часть прежнего содержания.
    """
    path = safe_wiki_path(wiki_root, rel_path)
    if not path.is_file():
        raise PageNotFoundError(f"страница не найдена: wiki/{rel_path}")
    old_size = len(path.read_text(encoding="utf-8"))
    if old_size and len(content) < old_size * min_keep_ratio:
        raise UnsafePageUpdateError(
            f"обновление уничтожило бы большую часть страницы wiki/{rel_path}"
        )
    path.write_text(content, encoding="utf-8")
    return rel_path


def save_raw_message(
    wiki_root: Path,
    text: str,
    kind: str,
    message_id: int | None = None,
    when: datetime | None = None,
) -> str:
    """Сохраняет оригинал сообщения в raw/sources/ (Раздел 20).

    Имя файла: raw/sources/YYYY-MM-DD-HHMMSS-telegram[-<id>].md
    Возвращает относительный путь (posix). Файл не переписывается.
    """
    when = when or datetime.now().astimezone()
    stamp = when.strftime("%Y-%m-%d-%H%M%S")
    suffix = f"-{message_id}" if message_id is not None else ""
    filename = f"{stamp}-telegram{suffix}.md"
    rel = Path("raw") / "sources" / filename
    path = wiki_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise WikiError(f"raw-файл уже существует: {rel.as_posix()}")
    lines = [
        "---",
        "source: telegram",
        f"kind: {kind}",
    ]
    if message_id is not None:
        lines.append(f"telegram_message_id: {message_id}")
    lines += [f"created_at: {when.isoformat()}", "---", ""]
    frontmatter = "\n".join(lines) + "\n"
    path.write_text(frontmatter + text, encoding="utf-8")
    return rel.as_posix()


def search_wiki(
    wiki_root: Path,
    terms: list[str],
    limit: int = 5,
) -> list[tuple[str, int]]:
    """Простой локальный поиск по filename, заголовкам и контенту.

    Возвращает список (относительный путь, score). Без векторной БД (Раздел 21).
    """
    root = wiki_dir(wiki_root)
    lower_terms = [t.lower() for t in terms if t.strip()]
    if not lower_terms:
        return []
    scored: list[tuple[str, int]] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if rel == "log.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        score = 0
        lowered = text.lower()
        filename = path.stem.lower()
        for term in lower_terms:
            if term in filename:
                score += 5
            for line in text.splitlines():
                if line.startswith("#") and term in line.lower():
                    score += 3
                    break
            score += lowered.count(term)
        if score > 0:
            scored.append((rel, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def append_log(
    wiki_root: Path,
    *,
    source_rel: str,
    created: list[str] | None = None,
    updated: list[str] | None = None,
    when: datetime | None = None,
) -> None:
    """Обновляет wiki/log.md (Раздел 27). Log формируется приложением, не LLM.

    Записи добавляются под заголовок сегодняшней даты.
    """
    when = when or datetime.now().astimezone()
    date_header = f"## {when.strftime('%Y-%m-%d')}"
    time_line = f"### {when.strftime('%H:%M')} — Telegram"

    block_lines = [time_line, "", "Source:", f"- `{source_rel}`", ""]
    if created:
        block_lines += ["Created:"]
        block_lines += [f"- `{p}`" for p in created]
        block_lines += [""]
    if updated:
        block_lines += ["Updated:"]
        block_lines += [f"- `{p}`" for p in updated]
        block_lines += [""]
    block = "\n".join(block_lines).rstrip() + "\n"

    log_path = wiki_dir(wiki_root) / "log.md"
    if not log_path.is_file():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        header_block = f"# Лог изменений\n\n{date_header}\n\n{block}"
        log_path.write_text(header_block, encoding="utf-8")
        return

    content = log_path.read_text(encoding="utf-8").rstrip() + "\n"
    if f"{date_header}\n" not in content:
        content += f"{date_header}\n\n{block}"
    else:
        insert_at = content.index(f"{date_header}\n") + len(date_header) + 1
        content = content[:insert_at] + "\n" + block + content[insert_at:]
    log_path.write_text(content, encoding="utf-8")


def recent_log(wiki_root: Path, limit: int = 15) -> str:
    """Возвращает последние записи wiki/log.md для /recent (Раздел 28)."""
    log_path = wiki_dir(wiki_root) / "log.md"
    if not log_path.is_file():
        return "Лог пуст."
    content = log_path.read_text(encoding="utf-8").rstrip()
    blocks = re.findall(r"## .*?(?=## |\Z)", content, flags=re.S)
    result = [block.strip() for block in blocks if block.strip()]
    return "\n".join(result[-limit:]) or "Лог пуст."


INDEX_HEADER = "# Индекс"


def index_path(wiki_root: Path) -> Path:
    """Путь к wiki/index.md."""
    return wiki_dir(wiki_root) / "index.md"


def extract_short_summary(content: str, limit: int = 160) -> str:
    """Краткое описание страницы для index.md — первая осмысленная строка.

    Пропускает YAML frontmatter и заголовки (# ...).
    """
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        idx = 1
        while idx < len(lines) and lines[idx].strip() != "---":
            idx += 1
        lines = lines[idx + 1 :]
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(stripped) <= limit:
            return stripped
        return stripped[: limit - 1].rstrip(" -–—") + "…"
    return ""


def _index_title(segment: str) -> str:
    return segment.capitalize()


def _index_group(rel_path: str) -> tuple[str, str] | None:
    """(заголовок секции, заголовок подсекции) для страницы из areas/.

    Пример: 'areas/business/domains/startups/ideas/x.md'
    -> ('### Startups', '#### Ideas').
    """
    if not rel_path.startswith("areas/"):
        return None
    parts = rel_path.split("/")
    if len(parts) < 3:
        return None
    return (
        f"### {_index_title(parts[-3])}",
        f"#### {_index_title(parts[-2])}",
    )


def _strip_md(rel_path: str) -> str:
    return rel_path[: -len(".md")] if rel_path.endswith(".md") else rel_path


def _entry_line(rel_path: str, summary: str) -> str:
    link = _strip_md(rel_path)
    return f"- [[{link}]] — {summary}" if summary else f"- [[{link}]]"


_ENTRY_RE = re.compile(r"^- \[\[([^\]]+)\]\]")
_INDEX_STOP = re.compile(r"^#{1,3} ")


def sync_index(
    wiki_root: Path,
    created: list[str] | None = None,
    updated: list[str] | None = None,
) -> None:
    """Синхронизирует wiki/index.md с фактическими страницами.

    - создана страница → добавляется запись в секцию по области/типу;
    - изменилось краткое описание → запись обновляется;
    - страница удалена/перемещена → «мёртвая» запись убирается.
    Ручные секции и записи вне areas/ не трогаются.
    """
    path = index_path(wiki_root)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(INDEX_HEADER + "\n\n", encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines()

    changes: dict[str, str] = {}
    for rel_path in list(created or []) + list(updated or []):
        try:
            summary = extract_short_summary(read_wiki_page(wiki_root, rel_path))
        except (WikiError, OSError):
            summary = ""
        changes[rel_path] = summary

    kept: list[str] = []
    for line in lines:
        m = _ENTRY_RE.match(line)
        if m:
            rel = m.group(1)
            if rel.startswith("areas/") and not (
                wiki_dir(wiki_root) / f"{rel}.md"
            ).is_file():
                continue
        kept.append(line)
    lines = kept

    for rel_path, summary in changes.items():
        group = _index_group(rel_path)
        if group is None:
            continue
        area_h, type_h = group
        link = _strip_md(rel_path)
        entry = _entry_line(rel_path, summary)
        replaced = False
        for i, line in enumerate(lines):
            m = _ENTRY_RE.match(line)
            if m and m.group(1) == link:
                if line != entry:
                    lines[i] = entry
                replaced = True
                break
        if replaced:
            continue
        _insert_index_entry(lines, area_h, type_h, entry)

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _insert_index_entry(
    lines: list[str], area_h: str, type_h: str, entry: str
) -> None:
    area_idx = next((i for i, ln in enumerate(lines) if ln == area_h), -1)
    if area_idx < 0:
        lines.extend(["", area_h, "", type_h, "", entry])
        return
    type_idx = -1
    for i in range(area_idx + 1, len(lines)):
        ln = lines[i]
        if _INDEX_STOP.match(ln):
            break
        if ln == type_h:
            type_idx = i
            break
    if type_idx < 0:
        lines.insert(area_idx + 1, "")
        lines.insert(area_idx + 2, type_h)
        lines.insert(area_idx + 3, "")
        lines.insert(area_idx + 4, entry)
    else:
        insert_at = type_idx + 1
        while insert_at < len(lines) and (
            not lines[insert_at].strip()
            or lines[insert_at].startswith("- [[")
        ):
            insert_at += 1
        lines.insert(insert_at, entry)