"""Skill invocation tracker — checks whether GTO recommendations were actioned.

Reads the session transcript for slash-command invocations, then compares
against the previous GTO artifact's owner_skill recommendations to determine
which were actioned and which were not.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from ..models import EvidenceRef, Finding
from .transcript import read_turns

# Pattern to match slash-command invocations in transcript text
# Matches "/skill", "/skill --flag", "/skill arg1 arg2"
SLASH_COMMAND_RE = re.compile(r"(?:^|\s)(/[a-z][\w-]*(?:\s+[\w=.-]+)*)", re.MULTILINE)


def extract_invoked_skills(transcript_path: Path | None) -> set[str]:
    """Extract slash-command invocations from a transcript.

    Returns a set of base skill names (e.g., {"/sqa", "/docs", "/deps"}).
    """
    if not transcript_path or not transcript_path.exists():
        return set[str]()

    turns = read_turns(transcript_path)
    skills: set[str] = set()
    for turn in turns:
        if turn.role != "user":
            continue
        for match in SLASH_COMMAND_RE.finditer(turn.content):
            command = match.group(1).strip().split()[0]  # Take just the /command part
            skills.add(command)
    return skills


def _normalize_skill(skill: str | None) -> str | None:
    """Normalize a skill name for comparison.

    "/sqa --layer=L7" → "/sqa", "pytest" → "pytest"
    """
    if not skill:
        return None
    return skill.split()[0].split("--")[0].rstrip()


def check_invocations(
    transcript_path: Path | None,
    prev_recommendations: list[Finding],
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Check which previous GTO recommendations were actioned.

    Compares the set of invoked skills against the owner_skill of previous
    recommendations. Emits findings for unactioned recommendations.

    Returns actioned/unactioned findings.
    """
    invoked = extract_invoked_skills(transcript_path)

    if not prev_recommendations:
        return []

    findings: list[Finding] = []
    unactioned: list[Finding] = []

    for rec in prev_recommendations:
        base = _normalize_skill(rec.owner_skill)
        if not base:
            continue

        # Check if the skill was invoked (match /sqa against both /sqa and /sqa --layer=L7)
        was_invoked = any(
            inv.startswith(base) or base.startswith(inv)
            for inv in invoked
        )

        if was_invoked:
            findings.append(replace(
                rec,
                status="resolved",
                metadata={**rec.metadata, "invocation_tracked": True},
            ))
        else:
            unactioned.append(rec)

    # Emit a single finding listing unactioned recommendations
    if unactioned:
        skills_list = sorted({
            _normalize_skill(f.owner_skill) or "unknown"
            for f in unactioned
        })
        findings.append(
            Finding(
                id="INVOCATION-UNACTIONED-001",
                title=f"{len(unactioned)} previous recommendations not actioned",
                description=(
                    f"Skills recommended by prior GTO run but not invoked this session: "
                    f"{', '.join(skills_list)}"
                ),
                source_type="detector",
                source_name="invocation_tracker",
                domain="session",
                gap_type="unactioned_recommendation",
                severity="low",
                evidence_level="verified" if invoked else "unverified",
                action="realize",
                priority="low",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(
                        kind="invocation_check",
                        value=", ".join(skills_list),
                        detail=f"{len(invoked)} skills invoked, {len(unactioned)} unactioned",
                    ),
                ],
            )
        )

    return findings
