"""Workflow hygiene detector — detects uncommitted changes and dirty state.

Checks git working tree for uncommitted modifications that indicate
work-in-progress that hasn't been persisted. This is a gap detector
because uncommitted work is at risk of loss.

What it detects:
- Modified tracked files (unstaged or staged)
- Deleted tracked files
- Untracked files in key directories (packages/, .claude/)

What it does NOT detect:
- Stashed changes (git stash list)
- Unpushed commits (that's a separate concern)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import EvidenceRef, Finding

# Maximum findings to prevent noise from large untracked sets
_MAX_FINDINGS = 5

# Directories where untracked files are noteworthy
_NOTEWORTHY_DIRS = ("packages/", ".claude/hooks/", ".claude/skills/")


def detect_workflow_hygiene(
    root: Path,
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Check git working tree for uncommitted changes.

    Returns:
        Findings for uncommitted work in the working tree.
    """
    if not (root / ".git").exists():
        return []

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(root),
        )
        if result.returncode != 0:
            return []
        porcelain = result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return []

    if not porcelain:
        return []

    lines = porcelain.splitlines()

    # Categorize changes
    modified: list[str] = []
    deleted: list[str] = []
    untracked_noteworthy: list[str] = []

    for line in lines:
        if len(line) < 4:
            continue
        status = line[:2]
        filepath = line[3:].strip()

        # Untracked
        if "??" in status:
            if any(filepath.startswith(d) for d in _NOTEWORTHY_DIRS):
                untracked_noteworthy.append(filepath)
            continue

        # Deleted
        if "D" in status:
            deleted.append(filepath)
            continue

        # Modified (staged or unstaged)
        if "M" in status or "A" in status or "R" in status or "C" in status:
            modified.append(filepath)

    findings: list[Finding] = []

    if modified:
        file_list = ", ".join(modified[:_MAX_FINDINGS])
        extra = f" (+{len(modified) - _MAX_FINDINGS} more)" if len(modified) > _MAX_FINDINGS else ""
        findings.append(
            Finding(
                id="WORKFLOW-001",
                title=f"{len(modified)} uncommitted modified file(s)",
                description=f"Working tree has modified files not yet committed: {file_list}{extra}",
                source_type="detector",
                source_name="workflow_hygiene_detector",
                domain="git",
                gap_type="techdebt",
                severity="low",
                evidence_level="verified",
                action="recover",
                priority="low",
                scope="local",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(kind="git_status", value="modified", detail=file_list[:200]),
                ],
            )
        )

    if deleted:
        file_list = ", ".join(deleted[:_MAX_FINDINGS])
        findings.append(
            Finding(
                id="WORKFLOW-002",
                title=f"{len(deleted)} deleted file(s) not committed",
                description=f"Files deleted from working tree not yet committed: {file_list}",
                source_type="detector",
                source_name="workflow_hygiene_detector",
                domain="git",
                gap_type="techdebt",
                severity="medium",
                evidence_level="verified",
                action="recover",
                priority="medium",
                scope="local",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(kind="git_status", value="deleted", detail=file_list[:200]),
                ],
            )
        )

    if untracked_noteworthy:
        file_list = ", ".join(untracked_noteworthy[:_MAX_FINDINGS])
        findings.append(
            Finding(
                id="WORKFLOW-003",
                title=f"{len(untracked_noteworthy)} untracked file(s) in key directories",
                description=f"Untracked files in packages/ or .claude/: {file_list}",
                source_type="detector",
                source_name="workflow_hygiene_detector",
                domain="git",
                gap_type="techdebt",
                severity="low",
                evidence_level="verified",
                action="prevent",
                priority="low",
                scope="local",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(kind="git_status", value="untracked", detail=file_list[:200]),
                ],
            )
        )

    return findings
