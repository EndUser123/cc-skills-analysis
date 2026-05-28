"""Workflow hygiene detector — session-scoped file edit tracking.

Uses transcript-extracted file edit lists instead of git status.
Terminal-scoped — only reflects what THIS session chain edited,
no noise from other terminals' uncommitted changes.
"""
from __future__ import annotations

from ..models import EvidenceRef, Finding

_MAX_FINDINGS = 5


def detect_workflow_hygiene(
    edited_files: list[str],
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Detect unpersisted edits from session transcript data.

    Uses transcript-extracted file edit list — terminal-scoped, no
    cross-terminal noise from git status.
    """
    if not edited_files:
        return []

    unique_files = sorted(set(edited_files))
    file_list = ", ".join(unique_files[:_MAX_FINDINGS])
    extra = f" (+{len(unique_files) - _MAX_FINDINGS} more)" if len(unique_files) > _MAX_FINDINGS else ""

    return [
        Finding(
            id="WORKFLOW-001",
            title=f"{len(unique_files)} file(s) edited this session",
            description=f"Session edited but may not be committed: {file_list}{extra}",
            source_type="detector",
            source_name="workflow_hygiene_detector",
            domain="workflow",
            gap_type="unpersisted_edits",
            severity="low",
            evidence_level="verified",
            action="recover",
            priority="low",
            scope="local",
            terminal_id=terminal_id,
            session_id=session_id,
            git_sha=git_sha,
            evidence=[
                EvidenceRef(kind="transcript_edits", value=f"{len(unique_files)} files", detail=file_list[:200]),
            ],
        )
    ]
