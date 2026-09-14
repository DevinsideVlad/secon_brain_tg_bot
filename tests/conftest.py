from pathlib import Path

import pytest

TEMPLATES = ("concept", "decision", "gap", "idea", "source", "synthesis")
AREA_DIRS = ("concepts", "decisions", "gaps", "ideas", "sources")


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Фиктивная Wiki для тестов (Раздел 33 ТЗ)."""
    root = tmp_path / "mozg"
    (root / "raw" / "sources").mkdir(parents=True)
    (root / "templates").mkdir(parents=True)
    for area in ("business", "personal"):
        area_root = root / "wiki" / "areas" / area
        area_root.mkdir(parents=True)
        for sub in AREA_DIRS:
            (area_root / sub).mkdir(parents=True)

    (root / "AGENTS.md").write_text(
        "# AGENTS\n\nПравила базы знаний mozg.\n"
        "- idea — собственная мысль или гипотеза пользователя.\n"
        "- decision — принятое решение.\n",
        encoding="utf-8",
    )
    for name in TEMPLATES:
        (root / "templates" / f"{name}.md").write_text(
            "# {title}\n\n{content}\n",
            encoding="utf-8",
        )
    (root / "raw" / "_about.md").write_text("# raw\n", encoding="utf-8")
    (root / "wiki" / "log.md").write_text("# Лог изменений\n", encoding="utf-8")
    (root / "wiki" / "index.md").write_text("# Индекс\n", encoding="utf-8")
    (root / "wiki" / "overview.md").write_text("# Обзор\n", encoding="utf-8")
    return root