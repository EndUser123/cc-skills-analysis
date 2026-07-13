"""Git branch awareness — adjusts recommendations based on current branch.

On feature branches, de-prioritize merge-time concerns (/docs, /deps)
and prioritize code quality checks (/sqa, /diagnose).
"""
from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from ..models import Finding

# Skills to de-prioritize on feature branches
MERGE_TIME_SKILLS = {"/docs", "/deps"}

# Skills to prioritize on feature branches
QUALITY_SKILLS = {"/sqa", "/diagnose", "pytest"}


def get_current_branch(root: Path) -> str | None:
    """Get the current git branch name. Returns None on error."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "branch", "--show-current"],
            text=True,
        )
        return out.strip() or None
    except subprocess.CalledProcessError:
        return None


def adjust_for_branch(root: Path, findings: list[Finding]) -> list[Finding]:
    """Adjust finding priorities based on current git branch.

    On main/default branches, all priorities apply as-is.
    On feature branches:
    - Merge-time skills (/docs, /deps) get priority lowered
    - Quality skills (/sqa, /diagnose) stay at current priority
    """
    branch = get_current_branch(root)
    if not branch or branch in ("main", "master"):
        return findings

    # We're on a feature branch
    adjusted: list[Finding] = []
    for f in findings:
        if f.owner_skill in MERGE_TIME_SKILLS and f.priority != "low":
            adjusted.append(replace(
                f,
                priority="low",
                metadata={**f.metadata, "branch_adjusted": True, "branch": branch},
            ))
        else:
            adjusted.append(f)

    return adjusted
