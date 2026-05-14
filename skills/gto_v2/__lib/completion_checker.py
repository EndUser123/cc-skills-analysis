"""Completion checker — filters session outcomes that were actually completed.

For each detected outcome, reads the surrounding transcript context and checks
whether the goal was actually addressed during the session. This closes the gap
where the regex-based outcome detector can't distinguish:
  "I want to build X" → assistant builds X → user confirms (completed)
from:
  "I want to build X" → never addressed (genuine gap)
"""
from __future__ import annotations

import re
from pathlib import Path

from .session_outcome_detector import SessionOutcomeItem
from .transcript import read_turns

# Assistant completion signals — strong evidence the goal was addressed
ASSISTANT_COMPLETION_PATTERNS = [
    re.compile(r"(?:done|finished|completed)\s+(?:implementing|building|adding|creating|fixing)\b", re.IGNORECASE),
    re.compile(r"(?:implemented|built|added|created|fixed)\s+(?:the\s+)?\S", re.IGNORECASE),
    re.compile(r"successfully\s+(?:created|implemented|built|added|fixed|updated)", re.IGNORECASE),
]

# User confirmation signals — follows an assistant action, confirms completion
USER_CONFIRMATION_PATTERNS = [
    re.compile(r"(?:looks?\s+good|works?\s+(?:now|great|perfect)|that's?\s+it|perfect|great\s+job)", re.IGNORECASE),
    re.compile(r"(?:thanks?\s*(?:!|\.)|verified|confirmed|tested\s+and\s+it\s+works)", re.IGNORECASE),
]

# Weak signals — NOT enough to mark as completed (pass through for LLM review)
WEAK_SIGNALS = [
    re.compile(r"(?:started|began|working\s+on)\b", re.IGNORECASE),
]


def _turns_to_dicts(transcript_path: Path) -> list[dict[str, str]]:
    """Read transcript turns via shared reader, return as {role, content} dicts."""
    return [{"role": t.role, "content": t.content} for t in read_turns(transcript_path)]


def _content_keywords(content: str) -> set[str]:
    """Extract significant keywords from outcome content for matching."""
    # Remove stop words, keep substantive terms
    stop = {"the", "a", "an", "to", "for", "in", "on", "of", "and", "or", "is", "it", "with", "by"}
    words = re.findall(r"[a-z]{3,}", content.lower())
    return {w for w in words if w not in stop}


def _has_completion_evidence(
    window_turns: list[dict[str, str]],
    outcome_keywords: set[str],
) -> bool:
    """Check if the window turns contain strong completion evidence.

    Requires BOTH:
    1. An assistant completion signal (done implementing, built the X, etc.)
    2. Either keyword overlap with the outcome content OR a user confirmation
    """
    has_assistant_signal = False
    has_user_confirmation = False
    matched_keywords: set[str] = set()

    for turn in window_turns:
        role = turn["role"]
        content = turn["content"].lower()

        if role == "assistant":
            for pattern in ASSISTANT_COMPLETION_PATTERNS:
                if pattern.search(content):
                    has_assistant_signal = True
            # Check keyword overlap
            turn_words = set(re.findall(r"[a-z]{3,}", content))
            matched_keywords |= (turn_words & outcome_keywords)

        elif role == "user":
            for pattern in USER_CONFIRMATION_PATTERNS:
                if pattern.search(content):
                    has_user_confirmation = True

    if not has_assistant_signal:
        return False

    # Require keyword overlap with outcome content in all cases
    if matched_keywords & outcome_keywords:
        return True

    return False


def check_completions(
    transcript_path: Path | None,
    items: list[SessionOutcomeItem],
    window: int = 10,
) -> list[SessionOutcomeItem]:
    """Filter outcomes that were likely completed.

    For each detected outcome, reads the N turns after it in the transcript.
    If the surrounding context contains strong completion signals from the
    assistant (with keyword match or user confirmation), the item is removed.

    Returns the filtered list (completed items removed).
    """
    if not transcript_path or not transcript_path.exists() or not items:
        return items

    turns = _turns_to_dicts(transcript_path)
    if not turns:
        return items

    kept: list[SessionOutcomeItem] = []

    for item in items:
        turn_idx = item.turn_number - 1  # turn_number is 1-based
        if turn_idx < 0 or turn_idx >= len(turns):
            kept.append(item)
            continue

        # Extract window of turns after this item
        window_end = min(turn_idx + window + 1, len(turns))
        window_turns = turns[turn_idx + 1 : window_end]

        if not window_turns:
            kept.append(item)
            continue

        outcome_keywords = _content_keywords(item.content)

        if _has_completion_evidence(window_turns, outcome_keywords):
            continue  # Completed — filter out

        kept.append(item)

    return kept
