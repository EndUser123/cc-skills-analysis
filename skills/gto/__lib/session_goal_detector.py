"""SessionGoalDetector - Extract stated session goal from oldest transcript.

Priority: P1 (runs during scope discovery, after Chain Integrity Check)
Purpose: Extract stated session goal from oldest transcript

Goal phrase patterns:
- "today I want to", "the goal is", "I need to"
- "let's build", "let's fix", "let's refactor"
- "I'm trying to", "we need to", "my goal today", "this session I want"

Behavior:
- Goal found → store as session_goal string in scope result
- Not found → session_goal = null (not an error)

Question-style intent patterns:
- "what are we doing", "what's the status", "what's needed next"
- "what were we working on", "how's it going", "how is it going"
- These trigger subagent path for chain-based session comprehension
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .transcript import read_turns


@dataclass
class SessionGoalResult:
    """Result of session goal detection."""

    session_goal: str | None  # Detected goal phrase or null
    source_turn: int | None  # Turn number where goal was found
    confidence: float  # 0.0 to 1.0 confidence score


class SessionGoalDetector:
    """
    Extract stated session goal from oldest transcript.

    Uses pattern matching on user messages to find goal statements.
    """

    # Goal phrase patterns with confidence weights
    GOAL_PATTERNS = [
        (r"today I want to\s+(.+?)[.!?]?$", 0.9),
        (r"the goal is\s+(?:to\s+)?(.+?)[.!?]?$", 0.9),
        (r"I need to\s+(.+?)[.!?]?$", 0.8),
        (r"let's (?:build|fix|refactor|implement|create|add)\s+(.+?)[.!?]?$", 0.9),
        (r"I'm trying to\s+(.+?)[.!?]?$", 0.7),
        (r"we need to\s+(.+?)[.!?]?$", 0.7),
        (r"my goal today is\s+(?:to\s+)?(.+?)[.!?]?$", 0.9),
        (r"this session I want to\s+(.+?)[.!?]?$", 0.9),
    ]

    # Question-style intent patterns - trigger subagent path
    QUESTION_PATTERNS = [
        r"what are we doing",
        r"what's the status",
        r"what's needed next",
        r"what were we working on",
        r"how's it going",
        r"how is it going",
    ]

    def __init__(self, project_root: Path | None = None):
        """Initialize detector with project root.

        Args:
            project_root: Project root directory (defaults to cwd)
        """
        self.project_root = project_root or Path.cwd()

    def detect_goal(self, transcript_path: Path) -> SessionGoalResult:
        """
        Extract session goal from transcript.

        Args:
            transcript_path: Path to transcript JSONL file

        Returns:
            SessionGoalResult with detected goal (or null)
        """
        if not transcript_path.exists():
            return SessionGoalResult(session_goal=None, source_turn=None, confidence=0.0)

        turns = read_turns(transcript_path)

        for turn in turns:
            if turn.role != "user":
                continue

            for pattern, confidence in self.GOAL_PATTERNS:
                match = re.search(pattern, turn.content, re.IGNORECASE)
                if match:
                    goal = match.group(1).strip()
                    return SessionGoalResult(
                        session_goal=goal,
                        source_turn=turn.turn_number,
                        confidence=confidence,
                    )

        # No goal found
        return SessionGoalResult(session_goal=None, source_turn=None, confidence=0.0)

    def detect_goal_from_chain(self, paths: list[str]) -> SessionGoalResult:
        """
        Extract session goal from oldest transcript in chain.

        Args:
            paths: List of transcript paths (ordered oldest to newest)

        Returns:
            SessionGoalResult with detected goal from oldest transcript
        """
        if not paths:
            return SessionGoalResult(session_goal=None, source_turn=None, confidence=0.0)

        # Check oldest transcript (first in list)
        oldest_path = Path(paths[0])
        return self.detect_goal(oldest_path)

    def is_question_style(self, query: str) -> bool:
        """Check if query is a question-style intent (triggers subagent path).

        Args:
            query: User query string to check

        Returns:
            True if query matches question-style patterns, False otherwise
        """
        query_lower = query.lower()
        return any(re.search(p, query_lower) for p in self.QUESTION_PATTERNS)


# Convenience function
def detect_session_goal(
    transcript_path: Path, project_root: Path | None = None
) -> SessionGoalResult:
    """
    Quick session goal detection.

    Args:
        transcript_path: Path to transcript file
        project_root: Project root directory

    Returns:
        SessionGoalResult with detected goal
    """
    detector = SessionGoalDetector(project_root)
    return detector.detect_goal(transcript_path)
