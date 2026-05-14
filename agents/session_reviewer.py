"""Session Reviewer Agent — reviews session outcomes for completion status.

Takes detected session outcomes (uncompleted goals, open questions, deferred items)
along with surrounding transcript context, and produces a filtered set where
goals that were actually completed during the session are marked as resolved.

This is the only gap where LLM judgment beats deterministic regex: distinguishing
"I want to build X" → assistant builds X → user confirms (completed)
from "I want to build X" → never addressed (genuine gap).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import parse_agent_result
from ..models import AgentResult
from ..__lib.session_outcome_detector import SessionOutcomeItem


def write_handoff(
    path: Path,
    outcomes: list[SessionOutcomeItem],
    transcript_excerpts: list[dict[str, str]],
) -> None:
    """Write session outcomes + transcript context for the reviewer agent.

    Args:
        path: Handoff file path (result path derived from sibling).
        outcomes: Detected session outcome items to review.
        transcript_excerpts: Surrounding transcript context as
            [{"role": "user/assistant", "content": "..."}] pairs.
    """
    handoff = {
        "role": "session_reviewer",
        "outcomes": [
            {
                "category": item.category,
                "content": item.content,
                "confidence": item.confidence,
                "recurrence_count": item.recurrence_count,
                "session_age": item.session_age,
            }
            for item in outcomes
        ],
        "transcript_context": transcript_excerpts,
        "output_path": str(path.parent / "session_reviewer_result.json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")


def read_result(path: Path) -> AgentResult:
    """Read the session reviewer result."""
    return parse_agent_result(path, "session_reviewer")
