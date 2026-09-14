"""Минимальная Git-интеграция (Разделы 30-32, 41 ТЗ).

При GIT_ENABLED=false вызовы не должны происходить вовсе (проверка в callers).
Git conflict не разрешается автоматически. Не используется `git add .`
или `git reset --hard`.
"""

import subprocess
from pathlib import Path

from .config import settings


class GitError(Exception):
    """Ошибка выполнения git-команды."""


def _run(root: Path, *args: str, check: bool = True) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise GitError(f"не удалось выполнить git {' '.join(args)}: {exc}") from exc
    if check and proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise GitError(f"git {' '.join(args)} завершилась ошибкой: {stderr}")
    return proc.stdout.strip()


def is_repo(root: Path) -> bool:
    return _run(root, "rev-parse", "--is-inside-work-tree", check=False) == "true"


def pull(root: Path) -> str:
    return _run(root, "pull", "--rebase")


def commit(root: Path, files: list[str], message: str) -> str:
    if not files:
        raise GitError("нет файлов для коммита")
    _run(root, "add", "--", *[str(f) for f in files])
    return _run(root, "commit", "-m", message)


def push(root: Path) -> str:
    return _run(root, "push", settings.git_remote, settings.git_branch)


def changed_commit_message(kind: str) -> str:
    return f"Telegram {kind}: обновление базы знаний"