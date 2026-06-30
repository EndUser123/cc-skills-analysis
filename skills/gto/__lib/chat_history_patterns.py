"""Chat History Pattern Detectors - complex gap patterns beyond simple intent detection.

These detectors find nuanced patterns in chat history that indicate:
- Avoidance signals (topics skirted around)
- Recurring themes (issues across sessions)
- Dependency chains (natural next steps)
- Work trajectory (pattern-implied completions)
- Self-reflection triggers (quality gates)

Priority: P1.5 (runs during gap detection, after session_outcome_detector)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .transcript import read_turns


@dataclass
class AvoidanceSignal:
    """A topic mentioned once then skirted around."""
    topic: str
    mention_count: int
    deferral_count: int
    confidence: float
    turn_numbers: list[int] = field(default_factory=list)
    evidence_snippets: list[str] = field(default_factory=list)


@dataclass
class RecurringTheme:
    """A concern raised across multiple sessions."""
    theme: str
    session_count: int
    last_mentioned_session: int
    urgency: Literal["low", "medium", "high"]
    confidence: float


@dataclass
class DependencyGap:
    """A natural next step based on completed work."""
    completed_action: str
    missing_dependency: str
    priority: Literal["low", "medium", "high", "critical"]
    confidence: float
    evidence: str


@dataclass
class ImpliedNextStep:
    """A next step inferred from work trajectory pattern."""
    observed_pattern: str
    implied_action: str
    confidence: float
    file_affected: str | None = None


@dataclass
class ReflectionTrigger:
    """A self-reflection question triggered by completion patterns."""
    trigger_type: Literal[
        "goals_audit",
        "boundary_uncertainty",
        "failure_mode_first",
        "implementation_vs_capability",
    ]
    context: str
    suggested_reflection: str
    priority: str


class ChatHistoryPatterns:
    """Detect complex gap patterns from chat history."""

    # Avoidance signal patterns
    AVOIDANCE_PATTERNS = [
        r"(?:we'll|I'll)\s+(?:deal\s+with|handle|address)\s+([^\.\n]{10,60})\s+later",
        r"(?:for\s+now|temporarily)\s+(?:ignore|skip)\s+([^\.\n]{10,60})",
        r"let's\s+(?:move\s+on|put\s+that\s+aside)\s+([^\.\n]{10,40})",
        r"not\s+(?:a\s+priority|in\s+scope)\s+([^\.\n]{10,40})",
    ]

    # Dependency chain patterns
    DEPENDENCY_PATTERNS = [
        (r"(?:created|built|implemented)\s+([^\.\n]{5,30})", r"(?:test|test\s+for|tests?\s+for)"),
        (r"(?:added|wired)\s+([^\.\n]{5,30})", r"(?:document|document\s+for|docs?\s+for)"),
        (r"(?:changed|updated|modified)\s+([^\.\n]{5,30})", r"(?:verify|verify\s+that|test\s+that)"),
        (r"(?:refactored|rewrote)\s+([^\.\n]{5,30})", r"(?:regression\s+test|backwards\s+compatib)"),
    ]

    # Human-facing label per DEPENDENCY_PATTERNS entry (same index); keeps raw
    # regex out of user-facing fields. Drives output labels and priority.
    _DEPENDENCY_LABELS = ["tests", "docs", "verification", "regression tests"]

    # Work trajectory patterns
    TRAJECTORY_PATTERNS = [
        (
            r"created\s+(\w+)\s+(?:file|module|class)",
            r"no\s+(?:test|test\s+file|tests?\s+for)",
            "module_without_tests",
        ),
        (
            r"implemented\s+(\w+)",
            r"no\s+(?:doc|documentation|examples?\s+for)",
            "implementation_without_docs",
        ),
        (
            r"(?:added|created)\s+(?:\d+\s+)?(?:related|similar)",
            r"no\s+(?:integration\s+test|test\s+coverage)",
            "related_components_without_coverage",
        ),
    ]

    # Self-reflection trigger patterns
    REFLECTION_PATTERNS = {
        "goals_audit": r"(?:implemented|built|created|added)\s+([^\.\n]{10,50})\s+(?:feature|capability|function)",
        "boundary_uncertainty": r"(?:not\s+sure|uncertain|could\s+be)\s+([^\.\n]{10,50})",
        "failure_mode_first": r"(?:fixed|fixed\s+the|resolved)\s+([^\.\n]{10,50})",
        "implementation_vs_capability": r"(?:can't|unable|doesn't)\s+(?:handle|support|do)\s+([^\.\n]{10,50})",
    }

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def detect_avoidance_signals(self, transcript_path: Path) -> list[AvoidanceSignal]:
        """Detect topics mentioned once then skirted around.

        Patterns:
        - "We'll deal with X later" (mentioned once, never returned to)
        - "For now, ignore X" (acknowledged but deferred)
        - "Let's move on from X" (topic raised then immediately dropped)
        - "Not a priority: X" (explicit de-prioritization without resolution)
        """
        signals: list[AvoidanceSignal] = []

        if not transcript_path.exists():
            return signals

        turns = read_turns(transcript_path)
        user_turns = [t for t in turns if t.role == "user"]

        topic_mentions: dict[str, dict[str, any]] = {}

        for turn in user_turns:
            content = turn.content

            for pattern in self.AVOIDANCE_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    topic = match.group(1).strip().lower()
                    if len(topic) < 5:
                        continue

                    if topic not in topic_mentions:
                        topic_mentions[topic] = {
                            "mention_count": 0,
                            "deferral_count": 0,
                            "turn_numbers": [],
                            "snippets": [],
                        }

                    topic_mentions[topic]["mention_count"] += 1
                    topic_mentions[topic]["turn_numbers"].append(turn.turn_number)

                    # Count deferral keywords
                    if re.search(r"(?:later|for\s+now|ignore|skip|move\s+on)", content, re.IGNORECASE):
                        topic_mentions[topic]["deferral_count"] += 1

                    # Store snippet
                    start = max(0, match.start() - 30)
                    end = min(len(content), match.end() + 30)
                    snippet = content[start:end].strip()
                    if snippet not in topic_mentions[topic]["snippets"]:
                        topic_mentions[topic]["snippets"].append(snippet)

        # Convert to AvoidanceSignal objects
        # Only include topics that were deferred at least once and never revisited
        for topic, data in topic_mentions.items():
            if data["deferral_count"] == 0:
                continue

            # Check if topic was revisited (mentions spread across transcript)
            # If mentions are clustered in early turns only, it's likely avoided
            turns_mentioned = data["turn_numbers"]
            if not turns_mentioned:
                continue

            first_mention = min(turns_mentioned)
            last_mention = max(turns_mentioned)

            # If gap between first and last mention is small (<5 turns) and never revisited later
            if last_mention - first_mention < 5 and last_mention < len(user_turns) - 10:
                confidence = 0.7 if data["deferral_count"] >= 2 else 0.5

                signals.append(
                    AvoidanceSignal(
                        topic=topic,
                        mention_count=data["mention_count"],
                        deferral_count=data["deferral_count"],
                        confidence=confidence,
                        turn_numbers=data["turn_numbers"],
                        evidence_snippets=data["snippets"],
                    )
                )

        return signals

    def detect_recurring_themes(
        self, transcript_path: Path, session_chain: list[dict] | list[str] | None = None
    ) -> list[RecurringTheme]:
        """Detect concerns raised across multiple sessions.

        Args:
            transcript_path: Current session transcript
            session_chain: List of prior session metadata

        Patterns:
        - Same issue mentioned in 2+ sessions
        - Same domain gap repeated (security, testing, docs)
        - Unresolved blockers reappearing
        """
        themes: list[RecurringTheme] = []

        if not transcript_path.exists():
            return themes

        turns = read_turns(transcript_path)
        user_turns = [t for t in turns if t.role == "user"]

        # Extract potential themes from current session
        current_themes: dict[str, int] = {}

        theme_keywords = {
            "security": r"(?:security|auth|permission|access|token|key|encrypt)",
            "testing": r"(?:test|coverage|pytest|spec|verify)",
            "docs": r"(?:doc|readme|example|tutorial|guide)",
            "performance": r"(?:slow|latency|timeout|optimize|performance)",
            "error": r"(?:error|exception|fail|crash|bug)",
        }

        for turn in user_turns:
            content = turn.content.lower()

            for theme, pattern in theme_keywords.items():
                if re.search(pattern, content):
                    current_themes[theme] = current_themes.get(theme, 0) + 1

        # If session_chain provided, check prior sessions for recurring themes
        prior_themes: dict[str, int] = {}
        if session_chain:
            for session in session_chain:
                # Handle both dict and str session representations
                session_id = session.get("session_id", "") if isinstance(session, dict) else ""
                if not session_id:
                    continue

                # Extract themes from session metadata or tldr
                session_goal = session.get("goal", "") if isinstance(session, dict) else ""
                if session_goal:
                    for theme, pattern in theme_keywords.items():
                        if re.search(pattern, session_goal, re.IGNORECASE):
                            prior_themes[theme] = prior_themes.get(theme, 0) + 1

            # Merge prior themes with current
            for theme, count in prior_themes.items():
                if theme in current_themes:
                    current_themes[theme] += count

        # Convert to RecurringTheme objects
        for theme, count in current_themes.items():
            session_count = 2 if session_chain and theme in prior_themes else 1
            if count >= 3 or (session_count >= 2 and count >= 2):  # Theme appears 3+ times or in 2+ sessions
                urgency = "high" if count >= 5 or session_count >= 3 else "medium" if count >= 4 or session_count >= 2 else "low"

                themes.append(
                    RecurringTheme(
                        theme=theme,
                        session_count=session_count,
                        last_mentioned_session=0,
                        urgency=urgency,
                        confidence=0.6,
                    )
                )

        return themes

    def detect_dependency_chain(
        self, transcript_path: Path, file_edits: list[str] | list[Path] | None = None
    ) -> list[DependencyGap]:
        """Find natural next steps based on completed work.

        Patterns:
        - Module A created → no tests for A
        - Feature X wired → no docs for X
        - Config changed → no verification run

        Args:
            transcript_path: Current session transcript
            file_edits: List of files edited this session (from transcript)

        Returns:
            List of DependencyGap objects
        """
        gaps: list[DependencyGap] = []

        if not transcript_path.exists():
            return gaps

        turns = read_turns(transcript_path)
        user_turns = [t for t in turns if t.role == "user"]
        assistant_turns = [t for t in turns if t.role == "assistant"]

        # Build conversation history as text
        conversation_text = "\n".join([t.content for t in user_turns + assistant_turns])

        # Completion set: structured file edits are the POSITIVE source.
        # Prior logic used file_edits as a NEGATIVE filter (suppressed gaps when
        # a file was edited) — inverted, it hid the real signal. Structured edits
        # now drive the "module completed without tests" gap directly; prose is
        # only a low-confidence fallback when no edits are available.
        _NON_SOURCE_EXT = {".md", ".json", ".toml", ".yaml", ".yml", ".ini",
                           ".cfg", ".conf", ".txt", ".lock", ".csv"}
        _SKIP_STEMS = {"__init__", "conftest", "setup"}

        def _stem(f: str | Path) -> str:
            p = Path(f) if not isinstance(f, Path) else f
            return p.stem.lower()

        if file_edits:
            # Structured path: one precise gap per edited source module that
            # lacks a co-edited test file. Only "tests" is emitted here because
            # it's the one dependency type structurally detectable from edits;
            # docs/verification/regression would be pure guessing.
            edited_stems = [_stem(f) for f in file_edits]
            test_targets = {
                re.sub(r"^test[_-]+", "", s)
                for s in edited_stems
                if s.startswith("test_") or s.startswith("test-") or s == "conftest"
            }
            seen: set[str] = set()
            for f in file_edits:
                p = Path(f) if not isinstance(f, Path) else f
                if p.suffix.lower() in _NON_SOURCE_EXT:
                    continue
                stem = p.stem.lower()
                if stem in _SKIP_STEMS or stem.startswith("test_") or stem.startswith("test-"):
                    continue
                if stem in test_targets or stem in seen:
                    continue
                seen.add(stem)
                gaps.append(
                    DependencyGap(
                        completed_action=f"Completed: edited {p.name}",
                        missing_dependency=f"Missing: tests for {stem}",
                        priority="high",
                        confidence=0.8,
                        evidence=f"'{p.name}' edited this session with no co-edited test file",
                    )
                )
        else:
            # Prose fallback (low confidence): regex-extract completed actions,
            # check each dependency type via prose mention near the completion.
            for idx, (completed_pattern, dependency_pattern) in enumerate(self.DEPENDENCY_PATTERNS):
                completed_match = re.search(completed_pattern, conversation_text, re.IGNORECASE)
                if not completed_match:
                    continue
                completed = completed_match.group(1).strip()
                dependency_check = re.search(
                    dependency_pattern + r"[^\.\n]{0,30}" + re.escape(completed),
                    conversation_text,
                    re.IGNORECASE,
                )
                if dependency_check:
                    continue
                label = self._DEPENDENCY_LABELS[idx]
                priority = (
                    "high" if label in ("tests", "verification", "regression tests")
                    else "low" if label == "docs"
                    else "medium"
                )
                gaps.append(
                    DependencyGap(
                        completed_action=f"Completed: {completed}",
                        missing_dependency=f"Missing: {label} for {completed}",
                        priority=priority,
                        confidence=0.4,
                        evidence=f"Found '{completed}' in prose but no {label} mentioned (low-confidence prose path)",
                    )
                )

        return gaps

    def detect_work_trajectory(self, transcript_path: Path) -> list[ImpliedNextStep]:
        """Infer next steps from work trajectory pattern.

        Patterns:
        - Series of edits in same module → completion missing
        - Created 3 related components → integration test missing
        - Refactored X → regression test missing
        """
        steps: list[ImpliedNextStep] = []

        if not transcript_path.exists():
            return steps

        turns = read_turns(transcript_path)
        user_turns = [t for t in turns if t.role == "user"]
        assistant_turns = [t for t in turns if t.role == "assistant"]

        conversation_text = "\n".join([t.content for t in user_turns + assistant_turns])

        # Check trajectory patterns
        for pattern, missing, pattern_type in self.TRAJECTORY_PATTERNS:
            match = re.search(pattern, conversation_text, re.IGNORECASE)
            if match:
                file_affected = match.group(1).strip() if match.groups() else None

                # Check if missing item was mentioned
                missing_check = re.search(missing, conversation_text, re.IGNORECASE)

                if not missing_check:
                    implied_action = ""
                    if pattern_type == "module_without_tests":
                        implied_action = f"Write tests for {file_affected or 'created module'}"
                    elif pattern_type == "implementation_without_docs":
                        implied_action = f"Document {file_affected or 'implementation'}"
                    elif pattern_type == "related_components_without_coverage":
                        implied_action = "Add integration test for related components"

                    confidence = 0.6

                    steps.append(
                        ImpliedNextStep(
                            observed_pattern=pattern_type,
                            implied_action=implied_action,
                            confidence=confidence,
                            file_affected=file_affected,
                        )
                    )

        return steps

    def detect_self_reflection_triggers(self, transcript_path: Path) -> list[ReflectionTrigger]:
        """Detect when self-reflection questions are needed.

        Triggers:
        - Feature completion without testing
        - Fix implementation without verification
        - Architecture change without ADR

        Returns:
            List of ReflectionTrigger objects
        """
        triggers: list[ReflectionTrigger] = []

        if not transcript_path.exists():
            return triggers

        turns = read_turns(transcript_path)
        conversation_text = "\n".join([t.content for t in turns])

        for trigger_type, pattern in self.REFLECTION_PATTERNS.items():
            matches = list(re.finditer(pattern, conversation_text, re.IGNORECASE))

            for match in matches:
                context = match.group(1).strip()

                if trigger_type == "goals_audit":
                    suggested = (
                        f"For capability '{context}', is it tested? "
                        f"How would we test for it? Is this reflected in unit, "
                        f"regression, and integration tests?"
                    )
                    priority = "medium"

                elif trigger_type == "boundary_uncertainty":
                    suggested = (
                        f"What is the smallest discriminating check that would "
                        f"resolve uncertainty about '{context}'? Name the "
                        f"falsification condition."
                    )
                    priority = "high"

                elif trigger_type == "failure_mode_first":
                    suggested = (
                        f"Before celebrating the fix to '{context}', ask: what "
                        f"is the likely failure mode? What discriminating test "
                        f"would falsify it? Could this overfire?"
                    )
                    priority = "high"

                elif trigger_type == "implementation_vs_capability":
                    suggested = (
                        f"Is the limitation '{context}' due to current "
                        f"implementation, or is it a true capability boundary? "
                        f"Challenge assumed limits that are just implementation constraints."
                    )
                    priority = "medium"

                else:
                    continue

                triggers.append(
                    ReflectionTrigger(
                        trigger_type=trigger_type,
                        context=context,
                        suggested_reflection=suggested,
                        priority=priority,
                    )
                )

        return triggers