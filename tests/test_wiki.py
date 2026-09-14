from datetime import UTC, datetime

import pytest

from app.wiki import (
    PageExistsError,
    PageNotFoundError,
    TemplateNotFoundError,
    UnsafePageUpdateError,
    UnsafePathError,
    WikiError,
    WikiStructureError,
    append_log,
    check_structure,
    create_page,
    list_wiki_pages,
    read_agents,
    read_template,
    read_wiki_page,
    recent_log,
    save_raw_message,
    search_wiki,
    update_page,
)


def test_check_structure_ok(tmp_wiki):
    check_structure(tmp_wiki)


def test_check_structure_raises_on_missing(tmp_wiki):
    (tmp_wiki / "templates").rename(tmp_wiki / "templates_renamed")
    with pytest.raises(WikiStructureError):
        check_structure(tmp_wiki)


def test_read_agents(tmp_wiki):
    assert "Правила базы знаний" in read_agents(tmp_wiki)


def test_read_template(tmp_wiki):
    assert "{title}" in read_template(tmp_wiki, "idea")
    with pytest.raises(TemplateNotFoundError):
        read_template(tmp_wiki, "comparison")


def test_list_wiki_pages_excludes_log(tmp_wiki):
    create_page(tmp_wiki, "idea", "business", "Тестовая идея", "контент")
    pages = list_wiki_pages(tmp_wiki)
    assert "log.md" not in pages
    assert "areas/business/ideas/тестовая-идея.md" in pages


def test_save_raw_user_thought(tmp_wiki):
    rel = save_raw_message(tmp_wiki, "Мысль без id", "user_thought")
    content = (tmp_wiki / rel).read_text(encoding="utf-8")
    assert content.startswith("---")
    assert "source: telegram" in content
    assert "kind: user_thought" in content
    assert "telegram_message_id" not in content
    assert content.rstrip().endswith("Мысль без id")
    assert rel.startswith("raw/sources/")


def test_save_raw_with_message_id_and_no_overwrite(tmp_wiki):
    when = datetime(2026, 9, 12, 17, 2, 1, tzinfo=UTC)
    rel = save_raw_message(tmp_wiki, "идея", "user_thought", message_id=391, when=when)
    assert rel == "raw/sources/2026-09-12-170201-telegram-391.md"
    content = (tmp_wiki / rel).read_text(encoding="utf-8")
    assert "telegram_message_id: 391" in content
    assert "created_at: 2026-09-12T17:02:01+00:00" in content
    with pytest.raises(WikiError):
        save_raw_message(tmp_wiki, "другое", "user_thought", message_id=391, when=when)


def test_save_raw_kind_external(tmp_wiki):
    rel = save_raw_message(tmp_wiki, "статья", "external_source")
    assert "kind: external_source" in (tmp_wiki / rel).read_text(encoding="utf-8")


def test_create_page_lazy_dirs(tmp_wiki):
    rel = create_page(tmp_wiki, "idea", "personal", "Личная идея", "# Личная идея\n")
    path = tmp_wiki / "wiki" / rel
    assert path.is_file()
    assert rel == "areas/personal/ideas/личная-идея.md"


def test_create_page_existing_raises(tmp_wiki):
    create_page(tmp_wiki, "idea", "business", "Идея", "text")
    with pytest.raises(PageExistsError):
        create_page(tmp_wiki, "idea", "business", "Идея", "text")


def test_create_page_unknown_type(tmp_wiki):
    with pytest.raises(WikiError):
        create_page(tmp_wiki, "comparison", "business", "x", "y")


def test_read_wiki_page_and_not_found(tmp_wiki):
    rel = create_page(tmp_wiki, "gap", "business", "CPU", "проверить CPU")
    assert read_wiki_page(tmp_wiki, rel) == "проверить CPU"
    with pytest.raises(PageNotFoundError):
        read_wiki_page(tmp_wiki, "areas/business/gaps/no.md")


def test_safe_wiki_path_rejects_traversal(tmp_wiki):
    with pytest.raises(UnsafePathError):
        update_page(tmp_wiki, "../templates/idea.md", "x")
    with pytest.raises(UnsafePathError):
        update_page(tmp_wiki, "..%2Fsecret.md", "x")
    with pytest.raises(UnsafePathError):
        update_page(tmp_wiki, "log.md", "x")


def test_update_page(tmp_wiki):
    rel = create_page(tmp_wiki, "concept", "business", "RAG", "старые заметки")
    updated = update_page(tmp_wiki, rel, "новый текст про RAG")
    assert updated == rel
    assert read_wiki_page(tmp_wiki, rel) == "новый текст про RAG"


def test_update_too_small_rejected(tmp_wiki):
    rel = create_page(tmp_wiki, "concept", "business", "RAG", "x" * 100)
    with pytest.raises(UnsafePageUpdateError):
        update_page(tmp_wiki, rel, "мало")


def test_search_wiki_by_content(tmp_wiki):
    create_page(tmp_wiki, "idea", "business", "Автотест RAG", "запускать тесты")
    create_page(tmp_wiki, "idea", "business", "Другое", "совсем другая тема")
    results = search_wiki(tmp_wiki, ["тест", "rag"])
    paths = [rel for rel, _ in results]
    assert paths and "areas/business/ideas/автотест-rag.md" in paths


def test_search_wiki_empty_terms(tmp_wiki):
    assert search_wiki(tmp_wiki, ["   "]) == []


def test_append_log_creates(tmp_wiki):
    append_log(
        tmp_wiki,
        source_rel="raw/sources/a.md",
        created=["areas/business/ideas/x.md"],
    )
    log = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "raw/sources/a.md" in log
    assert "areas/business/ideas/x.md" in log
    assert log.count("## " + "2026") >= 1


def test_append_log_collapses_same_day(tmp_wiki):
    when = datetime(2026, 9, 12, 17, 2, tzinfo=UTC)
    for i in range(2):
        append_log(
            tmp_wiki,
            source_rel=f"raw/sources/{i}.md",
            updated=["areas/business/ideas/z.md"],
            when=when,
        )
    log = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert log.count("## 2026-09-12") == 1
    assert log.count("raw/sources/0.md") == 1
    assert log.count("raw/sources/1.md") == 1


def test_recent_log(tmp_wiki):
    append_log(tmp_wiki, source_rel="raw/sources/a.md", created=["p1.md"])
    text = recent_log(tmp_wiki, limit=5)
    assert "p1.md" in text


def test_extract_short_summary(tmp_wiki):
    from app.wiki import extract_short_summary

    content = (
        "---\ntype: idea\n---\n# Название\n\n## Кратко\n\n"
        "Первая строка описания.\n\nВторая строка."
    )
    assert extract_short_summary(content) == "Первая строка описания."
    assert extract_short_summary("  \n# только заголовок\n") == ""
    long = "слово " * 100
    summary = extract_short_summary(long, limit=12)
    assert len(summary) <= 12 and summary.endswith("…")


def test_sync_index_adds_entry_and_group(tmp_wiki):
    from app.wiki import sync_index

    create_page(
        tmp_wiki, "idea", "business", "Рента плавок", "# Рента плавок\n\nидея аренды плавок"
    )
    sync_index(tmp_wiki, created=["areas/business/ideas/рента-плавок.md"])
    index = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "### Business" in index
    assert "#### Ideas" in index
    assert "- [[areas/business/ideas/рента-плавок]] — идея аренды плавок" in index


def test_sync_index_nested_area(tmp_wiki):
    from app.wiki import sync_index

    rel = "areas/business/domains/startups/ideas/swimwear-rental.md"
    page = tmp_wiki / "wiki" / rel
    page.parent.mkdir(parents=True)
    page.write_text("# Rent\n\nидея аренды плавок и шорт", encoding="utf-8")
    sync_index(tmp_wiki, created=[rel])
    index = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "### Startups" in index
    assert "#### Ideas" in index
    assert (
        "- [[areas/business/domains/startups/ideas/swimwear-rental]] — идея аренды плавок и шорт"
        in index
    )


def test_sync_index_updates_summary_when_changed(tmp_wiki):
    from app.wiki import sync_index

    rel = create_page(tmp_wiki, "concept", "business", "RAG", "# RAG\n\nпервое описание")
    sync_index(tmp_wiki, created=[rel])
    update_page(tmp_wiki, rel, "# RAG\n\nвторое, полное описание")
    sync_index(tmp_wiki, updated=[rel])
    index = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "- [[areas/business/concepts/rag]] — первое описание" not in index
    assert "- [[areas/business/concepts/rag]] — второе, полное описание" in index


def test_sync_index_same_summary_not_duplicated(tmp_wiki):
    from app.wiki import sync_index

    rel = create_page(tmp_wiki, "gap", "business", "Баг", "# Баг\n\nодинаковое описание")
    sync_index(tmp_wiki, created=[rel])
    sync_index(tmp_wiki, updated=[rel])
    index = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert index.count("- [[areas/business/gaps/баг]]") == 1


def test_sync_index_prunes_missing_page(tmp_wiki):
    from app.wiki import sync_index

    rel = create_page(tmp_wiki, "gap", "business", "Баг", "# Баг\n\nописание")
    sync_index(tmp_wiki, created=[rel])
    index_file = tmp_wiki / "wiki" / "index.md"
    assert "- [[areas/business/gaps/баг]]" in index_file.read_text(encoding="utf-8")
    (tmp_wiki / "wiki" / rel).unlink()
    sync_index(tmp_wiki)
    assert "- [[areas/business/gaps/баг]]" not in index_file.read_text(encoding="utf-8")


def test_sync_index_preserves_manual_lines(tmp_wiki):
    from app.wiki import sync_index

    index = tmp_wiki / "wiki" / "index.md"
    index.write_text("# Индекс\n\n## Личное\n\n<div>кастомная заметка\n", encoding="utf-8")
    rel = create_page(tmp_wiki, "idea", "business", "И", "# И\n\nописание")
    sync_index(tmp_wiki, created=[rel])
    content = index.read_text(encoding="utf-8")
    assert "<div>кастомная заметка" in content
    assert "- [[areas/business/ideas/и]] — описание" in content