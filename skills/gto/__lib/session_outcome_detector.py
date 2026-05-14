"""SessionOutcomeDetector - Surface incomplete items from chat history.

Priority: P1 (runs during gap detection)
Purpose: Detect conversation-level outstanding items from session transcripts

What it detects:
- Stated goals that weren't completed ("I want to build X" where X wasn't done)
- Identified tasks that weren't actioned ("we need to fix Y" where Y wasn't touched)
- Open questions from prior sessions
- Deferred items that haven't been revisited

What it is NOT:
- NOT code markers (TODO:, FIXME:) — use detect_unfinished_business for those
- NOT task list items — user explicitly excluded those
- NOT file-level gaps — those come from other detectors

The key distinction: this detector looks at WHAT WAS SAID in conversation,
cross-referenced against WHAT WAS DONE, to surface unmet commitments.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .transcript import read_turns


@dataclass
class SessionOutcomeItem:
    """A single outcome item found in session history."""

    category: Literal["uncompleted_goal", "identified_task", "open_question", "deferred_item"]
    content: str
    turn_number: int
    session_age: int  # 0 = current session, 1+ = prior sessions
    confidence: float  # 0.0 to 1.0
    source: str = "transcript"  # "transcript" or "tldr"
    recurrence_count: int = 1  # How many times this item appeared across transcript turns
    acknowledged: bool = False  # True if this gap was seen in a prior session but not resolved


@dataclass
class SessionOutcomeResult:
    """Result of session outcome detection."""

    items: list[SessionOutcomeItem]
    total_count: int
    current_session_items: list[SessionOutcomeItem] = field(default_factory=list)
    prior_session_items: list[SessionOutcomeItem] = field(default_factory=list)

    def to_gaps(self) -> list[dict]:
        """Convert items to GTO gap format for RSN integration."""
        gaps = []
        for idx, item in enumerate(self.items):
            gap_id = f"SESSION-{item.category[:4].upper()}-{idx + 1:03d}"
            # Recurrence-aware severity: items appearing multiple times are higher priority
            base_severity_map = {
                "uncompleted_goal": "medium",
                "identified_task": "medium",
                "open_question": "low",
                "deferred_item": "low",
            }
            base_severity = base_severity_map.get(item.category, "low")
            # Bump severity to high if item recurred across multiple turns
            severity = "high" if item.recurrence_count >= 2 else base_severity
            category_display = {
                "uncompleted_goal": "Uncompleted Goal",
                "identified_task": "Identified Task",
                "open_question": "Open Question",
                "deferred_item": "Deferred Item",
            }
            gaps.append(
                {
                    "id": gap_id,
                    "type": f"session_outcome_{item.category}",
                    "severity": severity,
                    "message": f"[{category_display.get(item.category, item.category)}] {item.content}",
                    "file_path": None,
                    "line_number": None,
                    "confidence": item.confidence,
                    "effort_estimate_minutes": 15,  # Default estimate for session items
                    "theme": "session_outcomes",
                    "metadata": {
                        "category": item.category,
                        "session_age": item.session_age,
                        "source": item.source,
                        "recurrence_count": item.recurrence_count,
                        "acknowledged": item.acknowledged,
                    },
                }
            )
        return gaps


class SessionOutcomeDetector:
    """
    Detect incomplete items from conversation history.

    Cross-references what was stated (goals, tasks, questions) against
    what was actually done to surface unmet commitments.
    """

    # Task-intent patterns: phrases that signal user stated an intention
    TASK_INTENT_PATTERNS = [
        # Direct goal statements
        (r"I want to\s+([^\.]{10,80})", 0.8),
        (r"I need to\s+([^\.]{10,80})", 0.8),
        (r"I'd like to\s+([^\.]{10,80})", 0.8),
        # Collaborative task statements
        (r"let's\s+(?:add|build|fix|create|implement|update)\s+([^\.]{10,80})", 0.85),
        (r"we should\s+(?:add|build|fix|create|implement|update)\s+([^\.]{10,80})", 0.8),
        (r"we need to\s+([^\.]{10,80})", 0.8),
        # Future-oriented task markers
        (
            r"(?:next|tomorrow|later)\s+(?:we'll|I'll|I'll)\s+(?:add|build|fix)\s+([^\.]{10,80})",
            0.7,
        ),
        # Open question patterns (questions that may indicate unresolved issues)
        (
            r"(?:how|what|why|when|where|should|could)\s+(?:do\s+)?(?:we|I|you)\s+([^\?]{10,60})\?",
            0.6,
        ),
    ]

    # Question patterns that signal open issues
    QUESTION_PATTERNS = [
        (r"(?:not sure|could be|maybe|probably)\s+(.{10,50})", 0.6),
        (r"(?:need to|should)\s+(?:check|verify|look at|investigate)\s+([^\.]{10,60})", 0.75),
    ]

    # Deferred patterns (high confidence — kept as deterministic findings)
    DEFERRED_PATTERNS = [
        (r"(?:for now|for the moment|temporarily)\s+([^\.]{10,60})", 0.6),
        (r"(?:come back to|defer|postpone)\s+([^\.]{10,60})", 0.65),
        (r"skip(?:ping|ped)?\s+(?:this|that|it)\s+([^\.]{10,50})", 0.5),
    ]

    # Candidate patterns (low confidence — flagged for LLM session reviewer)
    # Intentionally over-sensitive; the subagent filters noise.
    CANDIDATE_PATTERNS = [
        (r"\bcan\s+(?:be\s+)?(?:deleted|removed|cleaned?\s*up?)\s+later\b", 0.4),
        (r"\bnot\s+in\s+scope\b", 0.4),
        (r"\b(?:shelve|park|table|put\s+on\s+hold)\b", 0.45),
        (r"\b(?:can|could)\s+(?:wait|stay)\s+[^\.]{0,20}(?:later|after|until)\b", 0.4),
        (r"\b(?:revisit|come\s+back)\s+[^\.]{0,30}?(?:after|later|next)\b", 0.45),
        (r"\b(?:after|once)\s+[^\.]{5,30}\s+(?:is|are)\s+(?:done|complete|finished)\b", 0.4),
        (r"\b(?:skip|leave)\s+(?:for\s+now|it\s+for\s+now)\b", 0.4),
        (r"\bcan\s+(?:stay|remain)\s*[^\.]*\b(?:deleted|removed|cleaned)\s+later\b", 0.4),
        (r"\bout\s+of\s+scope\b", 0.35),
        (r"\b(?:will|we'll)\s+(?:deal\s+with|handle|address)\s+[^\.]{5,30}\s+later\b", 0.4),
    ]

    # Patterns that indicate the item was LIKELY completed (to filter out)
    COMPLETION_SIGNALS = [
        r"(?:done|finished|completed|implemented|fixed|added|created)",
        r"(?:let's start|now let's|next let's)",
        r"(?:moving on|on to|turning to)",
    ]

    def __init__(self, project_root: Path | None = None):
        """Initialize detector.

        Args:
            project_root: Project root directory (defaults to cwd)
        """
        self.project_root = project_root or Path.cwd()

    # ── Prior outcomes persistence ─────────────────────────────────────────────

    def _get_prior_outcomes_path(self, terminal_id: str | None) -> Path:
        """Return the path for prior session outcome state.

        Stored in ~/.claude/.evidence/gto-outcomes-{terminal_id}.json
        """
        evidence_base = Path.home() / ".claude" / ".evidence"
        tid_suffix = f"-{terminal_id}" if terminal_id else ""
        return evidence_base / f"gto-outcomes{tid_suffix}.json"

    def _load_prior_outcomes(self, terminal_id: str | None) -> dict[str, bool]:
        """Load prior session outcome items as {normalized_content: acknowledged}.

        Items in the prior outcomes file that are NOT in the current session's
        detected items are "acknowledged but unresolved" — they persisted across
        sessions without being resolved.

        Items that ARE in the current session are re-marked as acknowledged=True
        (they appeared again, meaning they weren't resolved).
        """
        path = self._get_prior_outcomes_path(terminal_id)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # data: {"items": [{"content": "...", "acknowledged": bool}, ...]}
            items = data.get("items", []) if isinstance(data, dict) else data
            return {
                self._normalize_content(item["content"]): bool(item.get("acknowledged", False))
                for item in items
            }
        except (OSError, json.JSONDecodeError, PermissionError):
            return {}

    def _save_current_outcomes(
        self,
        items: list[SessionOutcomeItem],
        terminal_id: str | None,
    ) -> None:
        """Save current session outcome items for next session's acknowledgment check."""
        path = self._get_prior_outcomes_path(terminal_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "items": [
                {
                    "content": item.content,
                    "acknowledged": item.acknowledged,
                    "category": item.category,
                }
                for item in items
            ]
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass  # Non-critical — evidence is still in transcript

    @staticmethod
    def _normalize_content(content: str) -> str:
        """Normalize content for cross-session comparison."""
        return re.sub(r"[^\w\s]", "", content.lower())[:80]

    def detect(
        self, transcript_path: Path | None, terminal_id: str | None = None
    ) -> SessionOutcomeResult:
        """
        Detect incomplete items from current and prior sessions.

        Args:
            transcript_path: Path to current session transcript JSONL
            terminal_id: Terminal identifier for finding prior session TLDRs

        Returns:
            SessionOutcomeResult with all detected items
        """
        items: list[SessionOutcomeItem] = []

        # 0. Load prior session outcomes for acknowledgment tracking
        prior_outcomes = self._load_prior_outcomes(terminal_id)

        # 1. Scan current transcript for stated intentions
        if transcript_path and transcript_path.exists():
            current_items = self._scan_transcript(transcript_path, session_age=0)
            items.extend(current_items)

        # 2. Follow handoff chain and scan prior session transcripts
        if transcript_path and terminal_id:
            prior_items = self._scan_prior_transcripts(transcript_path, terminal_id)
            items.extend(prior_items)

        # 3. Deduplicate items that appear in both current and prior
        items = self._deduplicate(items)

        # 4. Mark items as acknowledged if they appeared in a prior session
        # (i.e., they are still unresolved — user has seen them before)
        for item in items:
            key = self._normalize_content(item.content)
            if key in prior_outcomes:
                item.acknowledged = True

        # 5. Save current outcomes for next session's acknowledgment check
        self._save_current_outcomes(items, terminal_id)

        # 6. Categorize items
        current_session_items = [i for i in items if i.session_age == 0]
        prior_session_items = [i for i in items if i.session_age > 0]

        return SessionOutcomeResult(
            items=items,
            total_count=len(items),
            current_session_items=current_session_items,
            prior_session_items=prior_session_items,
        )

    def _scan_transcript(self, transcript_path: Path, session_age: int) -> list[SessionOutcomeItem]:
        """Scan a transcript file for outcome items.

        Args:
            transcript_path: Path to transcript JSONL
            session_age: 0 for current, 1+ for prior sessions

        Returns:
            List of detected SessionOutcomeItem
        """
        items: list[SessionOutcomeItem] = []

        turns = read_turns(transcript_path)

        completion_re = re.compile("|".join(self.COMPLETION_SIGNALS), re.IGNORECASE)

        # First pass: count occurrences of each normalized content
        content_counts: dict[str, int] = {}

        for turn in turns:
            # Only check user messages (they contain stated intentions)
            if turn.role != "user":
                continue

            content = turn.content

            # Skip very short messages (can't contain meaningful task intent)
            if len(content.strip()) < 20:
                continue

            # Detect candidate patterns FIRST — low-confidence, sent to LLM reviewer.
            # These run before the completion-signal skip because candidates like
            # "revisit X after Y is done" contain "done" but are genuine deferrals.
            for pattern, confidence in self.CANDIDATE_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    candidate_content = match.group(0).strip()
                    # Use surrounding sentence context when group(1) unavailable
                    if len(candidate_content) < 10:
                        start = max(0, match.start() - 40)
                        end = min(len(content), match.end() + 40)
                        candidate_content = content[start:end].strip()
                    items.append(
                        SessionOutcomeItem(
                            category="deferred_item",
                            content=candidate_content,
                            turn_number=turn.turn_number,
                            session_age=session_age,
                            confidence=confidence,
                            source="transcript",
                        )
                    )

            # Skip remaining high-confidence scans if the turn signals completion
            if completion_re.search(content):
                continue

            # Detect task intent patterns
            for pattern, confidence in self.TASK_INTENT_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    task_content = match.group(1).strip()
                    # Filter trivially short or generic content
                    if len(task_content) < 10:
                        continue
                    items.append(
                        SessionOutcomeItem(
                            category="uncompleted_goal",
                            content=task_content,
                            turn_number=turn.turn_number,
                            session_age=session_age,
                            confidence=confidence,
                            source="transcript",
                        )
                    )

            # Detect open question patterns
            for pattern, confidence in self.QUESTION_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    question_content = match.group(1).strip()
                    if len(question_content) < 10:
                        continue
                    items.append(
                        SessionOutcomeItem(
                            category="open_question",
                            content=question_content,
                            turn_number=turn.turn_number,
                            session_age=session_age,
                            confidence=confidence,
                            source="transcript",
                        )
                    )

            # Detect deferred patterns
            for pattern, confidence in self.DEFERRED_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    deferred_content = match.group(1).strip()
                    if len(deferred_content) < 10:
                        continue
                    items.append(
                        SessionOutcomeItem(
                            category="deferred_item",
                            content=deferred_content,
                            turn_number=turn.turn_number,
                            session_age=session_age,
                            confidence=confidence,
                            source="transcript",
                        )
                    )

        # Count occurrences of each normalized content
        def normalize(content: str) -> str:
            return re.sub(r"[^\w\s]", "", content.lower())[:80]

        for item in items:
            key = normalize(item.content)
            content_counts[key] = content_counts.get(key, 0) + 1

        # Attach recurrence counts to items
        for item in items:
            key = normalize(item.content)
            item.recurrence_count = content_counts.get(key, 1)

        return items

    def _get_current_handoff_path(self, terminal_id: str) -> Path | None:
        """Find the current session's handoff file.

        Handoff files are stored at ~/.claude/state/handoff/ using two possible
        naming conventions:
        - console_{terminal_id}_handoff.json (legacy/convention)
        - {hostname}-{pid}_handoff.json (StateManager format)

        The terminal_id parameter may be in either format.
        """
        state_base = Path.home() / ".claude" / "state" / "handoff"
        if not state_base.exists():
            return None

        # Normalize: strip console_ prefix if present to get the raw ID
        raw_id = terminal_id
        if terminal_id.startswith("console_"):
            raw_id = terminal_id[8:]

        # Try both naming patterns
        candidates = [
            state_base / f"console_{terminal_id}_handoff.json",
            state_base / f"{terminal_id}_handoff.json",
        ]
        # Also try with stripped console_ prefix
        if raw_id != terminal_id:
            candidates.extend([
                state_base / f"console_{raw_id}_handoff.json",
                state_base / f"{raw_id}_handoff.json",
            ])

        for handoff_path in candidates:
            if handoff_path.exists():
                return handoff_path

        # Try glob patterns as last resort
        for pattern in [f"console_{terminal_id}_*handoff*.json", f"{terminal_id}_*handoff*.json"]:
            for p in state_base.glob(pattern):
                return p
        return None

    def _get_prior_transcript_path(self, handoff_path: Path) -> Path | None:
        """Extract prior session transcript path from handoff file.

        The handoff file contains resume_snapshot.transcript_path which points
        to the prior session's transcript JSONL.
        """
        try:
            with open(handoff_path) as f:
                data = json.load(f)
            transcript_path_str = data.get("resume_snapshot", {}).get("transcript_path")
            if transcript_path_str:
                path = Path(transcript_path_str)
                if path.exists():
                    return path
        except (OSError, json.JSONDecodeError, PermissionError):
            pass
        return None

    def _scan_prior_transcripts(
        self, transcript_path: Path, terminal_id: str, max_chain_depth: int = 10
    ) -> list[SessionOutcomeItem]:
        """Scan prior session transcripts by following the handoff chain.

        Each session's handoff file (at ~/.claude/state/handoff/) contains
        resume_snapshot.transcript_path pointing to the prior session's transcript.
        This forms a linked list we can follow to scan all prior transcripts.

        Args:
            transcript_path: Current session's transcript path (start of chain)
            terminal_id: Terminal identifier for finding handoff files
            max_chain_depth: Maximum number of prior sessions to scan

        Returns:
            List of detected SessionOutcomeItem from prior sessions
        """
        items: list[SessionOutcomeItem] = []

        # Find the handoff file that references the current transcript.
        # This works for active sessions (no handoff yet for current terminal) because
        # it scans ALL handoff files looking for one whose transcript_path matches.
        # Falls back to terminal_id-based lookup if no matching handoff found.
        handoff_path = self._find_handoff_referencing(transcript_path)
        if not handoff_path and terminal_id:
            handoff_path = self._get_current_handoff_path(terminal_id)
        if not handoff_path:
            return items

        # Follow the chain
        session_age = 1
        visited: set[str] = set()

        while session_age <= max_chain_depth:
            prior_transcript = self._get_prior_transcript_path(handoff_path)
            if not prior_transcript or prior_transcript in visited:
                break
            visited.add(str(prior_transcript.resolve()))

            # Scan this prior transcript
            prior_items = self._scan_transcript(prior_transcript, session_age=session_age)
            items.extend(prior_items)

            # Move to next in chain - find the prior session's handoff file
            # The prior session's terminal_id is embedded in its handoff filename
            # We need to find any handoff file that references this transcript as its source
            handoff_path = self._find_handoff_referencing(prior_transcript)
            if not handoff_path:
                break

            session_age += 1

        return items

    def _find_handoff_referencing(self, transcript_path: Path) -> Path | None:
        """Find handoff file that has transcript_path as its source (prior session)."""
        state_base = Path.home() / ".claude" / "state" / "handoff"
        if not state_base.exists():
            return None
        transcript_str = str(transcript_path)
        for handoff_file in state_base.glob("console_*_handoff.json"):
            try:
                with open(handoff_file) as f:
                    data = json.load(f)
                if data.get("resume_snapshot", {}).get("transcript_path") == transcript_str:
                    return handoff_file
            except (OSError, json.JSONDecodeError, PermissionError):
                continue
        return None

    def _scan_prior_tldrs(self, terminal_id: str | None) -> list[SessionOutcomeItem]:
        """Scan prior session TLDR summaries for open items.

        Prior session summaries are written by SessionEnd_tldr.py hook and stored
        in terminal-scoped state directories with an 'open_items' field.

        NOTE: This method scans TLDR summaries which contain aggregated open_items.
        For full transcript scanning, use _scan_prior_transcripts() which follows
        the handoff chain to scan actual conversation content.

        Args:
            terminal_id: Terminal identifier for finding state files

        Returns:
            List of detected SessionOutcomeItem from prior sessions
        """
        items: list[SessionOutcomeItem] = []

        if not terminal_id:
            return items

        # Find prior TLDR/state files for this terminal
        state_base = Path.home() / ".claude" / "hooks" / "state"
        if not state_base.exists():
            return items

        # Find all tldr files for this terminal
        tldr_files = sorted(
            state_base.glob(f"SessionEnd_tldr_{terminal_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # Process up to 5 most recent prior sessions
        for tldr_file in tldr_files[:5]:
            try:
                with open(tldr_file) as f:
                    tldr_data = json.load(f)
            except (OSError, json.JSONDecodeError, PermissionError):
                continue

            # Extract open_items from TLDR
            open_items = tldr_data.get("open_items", [])
            if not open_items:
                continue

            # Session age: older files = higher age
            session_age = 1  # Default for prior sessions

            for item in open_items:
                if isinstance(item, str) and len(item.strip()) >= 10:
                    items.append(
                        SessionOutcomeItem(
                            category="identified_task",
                            content=item.strip(),
                            turn_number=0,  # No turn number for prior session items
                            session_age=session_age,
                            confidence=0.75,  # Prior session items have reasonable confidence
                            source="tldr",
                        )
                    )
                elif isinstance(item, dict):
                    content = item.get("content", "") or item.get("text", "")
                    if content and len(content) >= 10:
                        items.append(
                            SessionOutcomeItem(
                                category="identified_task",
                                content=content,
                                turn_number=0,
                                session_age=session_age,
                                confidence=item.get("confidence", 0.75),
                                source="tldr",
                            )
                        )

        return items

    def _deduplicate(self, items: list[SessionOutcomeItem]) -> list[SessionOutcomeItem]:
        """Remove duplicate items based on content similarity.

        Args:
            items: List of items to deduplicate

        Returns:
            Deduplicated list
        """
        if not items:
            return items

        # Normalize content for comparison
        def normalize(content: str) -> str:
            return re.sub(r"[^\w\s]", "", content.lower())[:80]

        seen: dict[str, SessionOutcomeItem] = {}
        result: list[SessionOutcomeItem] = []

        for item in items:
            key = normalize(item.content)
            if key not in seen:
                seen[key] = item
                result.append(item)
            else:
                # Keep the one with higher confidence, but preserve highest recurrence_count
                existing = seen[key]
                if item.confidence > existing.confidence:
                    existing.recurrence_count = max(
                        existing.recurrence_count, item.recurrence_count
                    )
                    seen[key] = item
                    # Update in result list
                    for i, r in enumerate(result):
                        if normalize(r.content) == key:
                            result[i] = item
                            break
                else:
                    # Keep existing but update recurrence if higher
                    existing.recurrence_count = max(
                        existing.recurrence_count, item.recurrence_count
                    )

        return result


# Convenience function
def detect_session_outcomes(
    transcript_path: Path | None,
    terminal_id: str | None = None,
    project_root: Path | None = None,
) -> SessionOutcomeResult:
    """
    Quick session outcome detection.

    Args:
        transcript_path: Path to current session transcript
        terminal_id: Terminal identifier for prior session lookup
        project_root: Project root directory

    Returns:
        SessionOutcomeResult with detected items
    """
    detector = SessionOutcomeDetector(project_root)
    return detector.detect(transcript_path, terminal_id)
