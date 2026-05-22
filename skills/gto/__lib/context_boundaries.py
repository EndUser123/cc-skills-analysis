"""Work context boundary detection — detects context switches within a session.

Identifies when a user starts a new goal after already working on one,
indicating multiple work contexts that should be tracked separately.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..models import EvidenceRef, Finding
from .transcript import read_turns

# Goal-starting patterns that indicate a new work context
NEW_GOAL_PATTERNS = [
    re.compile(r"(?:now let's|also let's|next let's|I also want to|I also need to)\s+", re.IGNORECASE),
    re.compile(r"(?:let's (?:also |now )?(?:switch|move|pivot|start))\s+", re.IGNORECASE),
    re.compile(r"(?:actually,?\s+(?:let's|I want to|I need to))\s+", re.IGNORECASE),
    re.compile(r"(?:moving on to|switching to|pivoting to)\s+", re.IGNORECASE),
    re.compile(r"(?:one more thing|before I forget|also,?\s+(?:I|let's))\s+", re.IGNORECASE),
]


@dataclass
class WorkContext:
    """A single work context within a session."""
    start_turn: int
    goal_phrase: str | None
    is_complete: bool = False


def detect_context_boundaries(transcript_path: Path | None) -> list[WorkContext]:
    """Detect work context boundaries in a transcript.

    Returns a list of WorkContext objects, one per detected context switch.
    The first context (implicit, from session start) is not included.
    """
    if not transcript_path or not transcript_path.exists():
        return []

    turns = read_turns(transcript_path)
    contexts: list[WorkContext] = []

    for turn in turns:
        if turn.role != "user":
            continue
        for pattern in NEW_GOAL_PATTERNS:
            match = pattern.search(turn.content)
            if match:
                # Extract the goal phrase (rest of the sentence)
                remainder = turn.content[match.end():].strip()
                # Snap start AND end to word boundaries to avoid
                # mid-path/mid-word corruption when pattern ends mid-segment
                # or truncation cuts mid-word.
                start_r = re.search(r"\w", remainder)
                start_offset = start_r.start() if start_r else 0
                end_offset = start_offset + 100
                if end_offset < len(remainder):
                    pre_end = remainder[start_offset:end_offset]
                    # Find complete words (word followed by separator) in pre_end
                    last_match = None
                    for m in re.finditer(r"\w+(?=\W)", pre_end):
                        last_match = m
                    if last_match:
                        end_offset = start_offset + last_match.end()
                phrase = remainder[start_offset:end_offset]
                contexts.append(WorkContext(
                    start_turn=turn.turn_number,
                    goal_phrase=phrase,
                ))
                break  # One match per turn is enough

    return contexts


def context_boundary_findings(
    transcript_path: Path | None,
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Emit findings for detected context switches."""
    contexts = detect_context_boundaries(transcript_path)
    if not contexts:
        return []

    findings: list[Finding] = []
    for idx, ctx in enumerate(contexts, start=1):
        findings.append(
            Finding(
                id=f"CONTEXT-SWITCH-{idx:03d}",
                title=f"Context switch at turn {ctx.start_turn}",
                description=(
                    f"User started a new work context: \"{ctx.goal_phrase}\". "
                    f"Prior work context may have unfinished items."
                ),
                source_type="detector",
                source_name="context_boundaries",
                domain="session",
                gap_type="context_switch",
                severity="low",
                evidence_level="verified",
                action="realize",
                priority="low",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(
                        kind="context_boundary",
                        value=f"turn={ctx.start_turn}",
                        detail=ctx.goal_phrase or "",
                    ),
                ],
            )
        )

    return findings
