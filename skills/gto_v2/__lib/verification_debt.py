"""Verification debt detector — detects edits without test verification.

Scans transcript for Edit/Write tool calls that weren't followed by a
test execution (pytest, unittest) within a reasonable window. This flags
code changes that lack regression proof.

What it detects:
- File edits with no test run in the surrounding N turns
- Multiple edits to test files (test fixes) without a re-run
- Edits to production code with no test invocation at all

What it does NOT detect:
- Edits to config/docs/non-code files (those don't need tests)
- Edits where the user explicitly says "no test needed"
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import EvidenceRef, Finding

# Tools that modify files
_EDIT_TOOLS = frozenset({"Edit", "Write"})

# Bash commands that count as test verification
_TEST_COMMAND_PATTERNS = ("pytest", "unittest", "test", "npm test", "cargo test")

# Window of turns after an edit to look for test verification
_VERIFICATION_WINDOW = 40

# File patterns that don't need test verification
_SKIP_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".rst")

_MAX_FINDINGS = 50


def detect_verification_debt(
    transcript_path: Path | None,
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Detect edits that weren't followed by test verification.

    Scans transcript for file edits, then checks if a test command
    was run within a window of turns after the edit.

    Returns:
        Findings for unverified edits.
    """
    if not transcript_path or not transcript_path.exists():
        return []

    # Parse all entries to find edit events and test runs
    entries: list[dict] = []
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (OSError, PermissionError):
        return []

    # Track edit events and test run positions
    edit_events: list[dict] = []  # {file_path, line_number}
    test_run_positions: list[int] = []  # line numbers where test commands ran

    for line_idx, entry in enumerate(entries):
        # Find test runs in Bash tool results
        if entry.get("type") == "assistant":
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") == "Bash":
                    cmd = (block.get("input") or {}).get("command", "")
                    if any(p in cmd.lower() for p in _TEST_COMMAND_PATTERNS):
                        test_run_positions.append(line_idx)

                # Find file edits
                if block.get("name") in _EDIT_TOOLS:
                    fp = (block.get("input") or {}).get("file_path", "")
                    if fp and not fp.endswith(_SKIP_SUFFIXES):
                        edit_events.append({"file_path": fp, "line_idx": line_idx})

    if not edit_events:
        return []

    # Check which edits have no test verification within the window
    unverified_edits: list[dict] = []
    for edit in edit_events:
        edit_pos = edit["line_idx"]
        # Look for a test run within the window after this edit
        has_verification = any(
            test_pos > edit_pos and test_pos <= edit_pos + _VERIFICATION_WINDOW
            for test_pos in test_run_positions
        )
        if not has_verification:
            unverified_edits.append(edit)

    if not unverified_edits:
        return []

    # Deduplicate by file path (keep last edit per file)
    seen_files: dict[str, dict] = {}
    for edit in unverified_edits:
        seen_files[edit["file_path"]] = edit

    # Limit to prevent noise
    files_to_report = list(seen_files.keys())[:_MAX_FINDINGS]
    extra = len(seen_files) - _MAX_FINDINGS

    file_list = ", ".join(f.split("/")[-1] for f in files_to_report)
    extra_text = f" (+{extra} more)" if extra > 0 else ""

    return [
        Finding(
            id="VERIFY-001",
            title=f"{len(seen_files)} file edit(s) without test verification",
            description=(
                f"Code edits detected without a subsequent test run: "
                f"{file_list}{extra_text}. "
                f"Consider running tests to verify these changes."
            ),
            source_type="detector",
            source_name="verification_debt_detector",
            domain="tests",
            gap_type="missingtests",
            severity="medium",
            evidence_level="verified",
            action="prevent",
            priority="medium",
            scope="local",
            terminal_id=terminal_id,
            session_id=session_id,
            git_sha=git_sha,
            evidence=[
                EvidenceRef(
                    kind="transcript_analysis",
                    value="unverified_edits",
                    detail=file_list[:200],
                ),
            ],
        )
    ]
