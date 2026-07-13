"""Session velocity / stuckness detection — detects repeated goals across sessions.

Reads the session chain to detect when the same goal or carryover finding
appears across multiple consecutive sessions, indicating the user may be stuck.
"""
from __future__ import annotations

from pathlib import Path

from ..models import EvidenceRef, Finding
from .session_goal_detector import SessionGoalDetector


def detect_stuckness(
    root: Path,
    chain: list[str],
    carryover_findings: list[Finding],
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Detect stuckness from repeated goals or carryover across sessions.

    Returns findings if the same goal appears in 3+ consecutive sessions
    or the same carryover finding persists across runs.
    """
    if not chain or len(chain) < 2:
        return []

    findings: list[Finding] = []

    # Check for repeated goals across sessions
    detector = SessionGoalDetector(root)
    goals: list[str | None] = []
    for transcript_path in chain:
        try:
            result = detector.detect_goal_from_chain([transcript_path])
            goals.append(result.session_goal)
        except Exception:
            goals.append(None)

    # Count consecutive identical non-None goals
    non_none_goals = [g for g in goals if g]
    if len(non_none_goals) >= 2:
        # Check if the last 3+ goals are the same
        recent = non_none_goals[-3:] if len(non_none_goals) >= 3 else non_none_goals
        if len(set(g.lower().strip()[:50] for g in recent)) == 1 and len(recent) >= 2:
            goal_text = recent[0]
            findings.append(
                Finding(
                    id="STUCK-001",
                    title=f"Same goal across {len(recent)} sessions — may be stuck",
                    description=(
                        f"Goal \"{goal_text[:80]}\" has appeared in {len(recent)} consecutive sessions. "
                        f"Consider escalating approach, breaking the task down differently, "
                        f"or running a diagnostic skill."
                    ),
                    source_type="detector",
                    source_name="stuckness_detector",
                    domain="session",
                    gap_type="stuckness",
                    severity="high",
                    evidence_level="verified",
                    action="recover",
                    priority="high",
                    terminal_id=terminal_id,
                    session_id=session_id,
                    git_sha=git_sha,
                    evidence=[
                        EvidenceRef(
                            kind="stuckness",
                            value=f"{len(recent)} sessions",
                            detail=goal_text[:100] if goal_text else "",
                        ),
                    ],
                )
            )

    # Check for carryover findings that have been around for many runs
    recurring_carryover = [
        f for f in carryover_findings
        if f.metadata.get("_carry_count", 0) >= 3
    ]
    if recurring_carryover:
        ids = [f.id for f in recurring_carryover]
        titles = [f.title[:60] for f in recurring_carryover]
        findings.append(
            Finding(
                id="STUCK-CARRYOVER-001",
                title=f"{len(recurring_carryover)} findings carried 3+ runs without resolution",
                description=(
                    f"Persistent findings that haven't been resolved: {', '.join(titles[:5])}. "
                    f"Consider running a targeted skill or changing approach."
                ),
                source_type="detector",
                source_name="stuckness_detector",
                domain="session",
                gap_type="stuckness",
                severity="medium",
                evidence_level="verified",
                action="recover",
                priority="medium",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(
                        kind="carryover_stuckness",
                        value=", ".join(ids[:5]),
                        detail=f"{len(recurring_carryover)} recurring carryover findings",
                    ),
                ],
            )
        )

    return findings
