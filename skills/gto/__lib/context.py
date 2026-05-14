from __future__ import annotations

from pathlib import Path
import subprocess


def get_git_sha(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        return out or None
    except Exception:
        return None


def git_dirty(root: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"], text=True
        )
        return bool(out.strip())
    except Exception:
        return False
