import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app import git
from app.handlers import perform_capture


def _run(cwd: Path, *args: str):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def git_env(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    assert _run(origin, "init", "--bare", "--initial-branch=master").returncode == 0

    work = tmp_path / "work"
    work.mkdir()
    _run(work, "init")
    _run(work, "checkout", "-b", "master")
    _run(work, "config", "user.email", "bot@test.local")
    _run(work, "config", "user.name", "Test Bot")
    _run(work, "remote", "add", "origin", str(origin))
    (work / "base.md").write_text("# base\n", encoding="utf-8")
    _run(work, "add", "--", "base.md")
    _run(work, "commit", "-m", "initial")
    _run(work, "push", "-u", "origin", "master")
    return {"origin": origin, "work": work}


def test_is_repo(git_env):
    assert git.is_repo(git_env["work"])
    assert not git.is_repo(git_env["origin"].parent)


def test_pull_integration(git_env):
    base = git_env["work"].parent
    other = base / "other"
    proc = subprocess.run(
        ["git", "clone", str(git_env["origin"]), str(other)],
        cwd=base,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    _run(other, "config", "user.email", "bot@test.local")
    _run(other, "config", "user.name", "Test Bot")
    (Path(other) / "from-other.md").write_text("new", encoding="utf-8")
    _run(Path(other), "add", "--", "from-other.md")
    _run(Path(other), "commit", "-m", "other change")
    _run(Path(other), "push")

    with patch("app.git.settings.git_remote", "origin"), patch(
        "app.git.settings.git_branch", "master"
    ):
        git.pull(git_env["work"])
    assert (git_env["work"] / "from-other.md").is_file()


def test_pull_uses_explicit_branch_and_autostash(tmp_path):
    with patch("app.git._run") as run, patch(
        "app.git.settings.git_remote", "origin"
    ), patch("app.git.settings.git_branch", "main"):
        git.pull(tmp_path)
    run.assert_called_once_with(
        tmp_path, "pull", "--rebase", "--autostash", "origin", "main"
    )


def test_pull_keeps_dirty_changes_with_autostash(git_env):
    base = git_env["work"].parent
    other = base / "other-dirty"

    def git_other(*args: str):
        return subprocess.run(
            ["git", *args], cwd=other, capture_output=True, text=True
        )

    assert subprocess.run(
        ["git", "clone", str(git_env["origin"]), str(other)],
        cwd=base,
        capture_output=True,
        text=True,
    ).returncode == 0
    git_other("config", "user.email", "bot@test.local")
    git_other("config", "user.name", "Test Bot")
    (other / "remote.md").write_text("remote", encoding="utf-8")
    git_other("add", "--", "remote.md")
    git_other("commit", "-m", "remote change")
    git_other("push")

    work = git_env["work"]
    (work / "base.md").write_text("# base\nlocal dirty\n", encoding="utf-8")

    with patch("app.git.settings.git_remote", "origin"), patch(
        "app.git.settings.git_branch", "master"
    ):
        git.pull(work)

    assert (work / "remote.md").is_file()
    assert "local dirty" in (work / "base.md").read_text(encoding="utf-8")


def test_commit_only_specified_files(git_env):
    work = git_env["work"]
    (work / "a.md").write_text("a", encoding="utf-8")
    (work / "b.md").write_text("b", encoding="utf-8")
    git.commit(work, ["a.md"], "commit только a")
    names = _run(work, "log", "-1", "--name-only", "--format=").stdout.split()
    assert names == ["a.md"]
    assert (work / "b.md").is_file()  # остался untracked


def test_commit_empty_files_raises(git_env):
    with pytest.raises(git.GitError):
        git.commit(git_env["work"], [], "пусто")


def test_push_without_remote_raises(tmp_path):
    solo = tmp_path / "solo"
    solo.mkdir()
    _run(solo, "init")
    _run(solo, "checkout", "-b", "master")
    _run(solo, "config", "user.email", "x@y")
    _run(solo, "config", "user.name", "X")
    (solo / "f.md").write_text("f", encoding="utf-8")
    git.commit(solo, ["f.md"], "init")
    with patch("app.git.settings.git_remote", "origin"), patch(
        "app.git.settings.git_branch", "master"
    ):
        with pytest.raises(git.GitError):
            git.push(solo)


@pytest.mark.asyncio
async def test_capture_commits_and_pushes(tmp_wiki):
    from app.schemas import TopicAnalysis, WikiAction, WikiPlan

    class StubLLM:
        async def analyze_topic(self, agents, message, wiki_pages):
            return TopicAnalysis(
                topic="x", search_terms=["x"], likely_page_type="idea"
            )

        async def build_wiki_plan(self, agents, message, related_pages, templates):
            return WikiPlan(
                summary="s",
                actions=[
                    WikiAction(
                        action="create",
                        page_type="idea",
                        area="business",
                        title="Итоговый тест",
                        content="# Итоговый тест\n",
                    )
                ],
            )

    origin = tmp_wiki.parent / "origin"
    origin.mkdir()
    assert _run(origin, "init", "--bare", "--initial-branch=master").returncode == 0

    root = tmp_wiki
    _run(root, "init")
    _run(root, "checkout", "-b", "master")
    _run(root, "config", "user.email", "bot@test.local")
    _run(root, "config", "user.name", "Test Bot")
    _run(root, "remote", "add", "origin", str(origin))
    _run(root, "add", "--", ".")
    assert _run(root, "commit", "-m", "initial").returncode == 0
    assert _run(root, "push", "-u", "origin", "master").returncode == 0

    with patch("app.handlers.settings.git_enabled", True), patch(
        "app.handlers.settings.git_remote", "origin"
    ), patch("app.handlers.settings.git_branch", "master"):
        result = await perform_capture(root, "сохранить мысль", llm=StubLLM())

    assert result["created"]
    commit_msg = _run(root, "log", "-1", "--format=%s").stdout.strip()
    assert "Telegram" in commit_msg
    assert (root / "wiki" / result["created"][0]).is_file()
    names = _run(root, "log", "-1", "--name-only", "--format=").stdout
    assert "wiki/index.md" in names
    assert "wiki/log.md" not in names