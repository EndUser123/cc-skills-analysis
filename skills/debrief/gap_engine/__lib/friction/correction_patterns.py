"""Correction pattern detector — finds interaction friction markers in transcripts."""
from __future__ import annotations

import re
from pathlib import Path

from ...models import EvidenceRef, Finding


PATTERN_MARKERS = {
    "hook_contract_friction": re.compile(r"I disabled hooks", re.IGNORECASE),
    "context_loss": re.compile(r"You are confused", re.IGNORECASE),
    "pattern_mismatch": re.compile(r"enterprise bloat", re.IGNORECASE),
    "path_issues": re.compile(r"wrong directory", re.IGNORECASE),
    "cross_terminal": re.compile(r"errors in another terminal", re.IGNORECASE),
    "skill_dispatch": re.compile(r"you didn't call Skill", re.IGNORECASE),
    "stale_data": re.compile(r"old data|cached data", re.IGNORECASE),
    "repeated_problems": re.compile(r"same problem again", re.IGNORECASE),
}


def detect_correction_patterns(
    transcript_path: Path,
    terminal_id: str,
    session_id: str,
    git_sha: str | None,
) -> list[Finding]:
    findings: list[Finding] = []

    if not transcript_path.exists():
        return findings

    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return findings

    for line_num, line in enumerate(lines, 1):
        for category, pattern in PATTERN_MARKERS.items():
            match = pattern.search(line)
            if match:
                matched_substring = match.group(0)
                findings.append(
                    Finding(
                        id=f"FRIC-COR-{len(findings) + 1:03d}",
                        title=f"Correction pattern: {category}",
                        description=(
                            f"Interaction friction detected: {category}. "
                            f"Matched pattern '{pattern.pattern}' against "
                            f"substring '{matched_substring}' at line {line_num}."
                        ),
                        source_type="detector",
                        source_name="correction_patterns",
                        domain="friction",
                        gap_type="correction_pattern",
                        severity="medium",
                        evidence_level="verified",
                        scope="session",
                        terminal_id=terminal_id,
                        session_id=session_id,
                        git_sha=git_sha,
                        evidence=[
                            EvidenceRef(
                                kind="transcript_line",
                                value=str(transcript_path),
                                detail=f"line:{line_num}",
                            ),
                            EvidenceRef(
                                kind="pattern_definition",
                                value=pattern.pattern,
                                detail=f"regex for category={category}, flags={pattern.flags}",
                            ),
                            EvidenceRef(
                                kind="match_substring",
                                value=matched_substring,
                                detail=(
                                    f"line {line_num} char {match.start()}-{match.end()}: "
                                    f"...{line[max(0, match.start()-30):match.end()+30]}..."
                                ),
                            ),
                            EvidenceRef(
                                kind="quote",
                                value=line.strip(),
                                detail=f"{category} marker (full line)",
                            ),
                        ],
                    )
                )

    return findings
