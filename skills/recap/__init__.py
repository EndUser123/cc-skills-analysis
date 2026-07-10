#!/usr/bin/env python
"""Terminal-wide session recap via direct transcript analysis."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

# Pre-mortem fix 3b: SessionSummary TypedDict
class SessionSummary(TypedDict):
    """Type definition for session summary dictionaries."""
    session_id: str
    goal: str
    current_task: str
    active_files: list[str]
    created_at: str
    transcript_path: str

from recap.acquire import (
    _get_current_session_id,
    _get_fresh_handoff,
    _get_most_recent_transcript,
    _get_project_hash,
    _get_sessions_index_path,
    _is_subagent_transcript,
    _is_transcript_file,
    _load_from_handoff,
    _scan_transcript_dir,
    _validate_handoff_identity,
    find_transcript_file,
    get_project_root,
    load_sessions_index,
    resolve_terminal_key,
)

logger = logging.getLogger(__name__)

# AIR Gap state file path
_AIR_GAPS_KEY = "air_gap_context"
_STATE_DIR = Path.home() / ".claude" / "state"


def _get_session_id_from_env() -> str:
    """Get session ID, preferring identity.json over env vars.

    identity.json is written fresh at session start and survives compaction.
    CLAUDE_SESSION_ID may be empty or stale.
    """
    wt = os.environ.get("WT_SESSION")
    if wt:
        identity_path = Path.home() / ".claude" / ".artifacts" / f"console_{wt}" / "identity.json"
        if identity_path.exists():
            try:
                data = json.loads(identity_path.read_text(encoding="utf-8"))
                sid = data.get("claude", {}).get("session_id")
                if sid:
                    return sid
            except (OSError, json.JSONDecodeError):
                pass
    return os.environ.get("CLAUDE_SESSION_ID", "default")


def load_air_gaps() -> list[dict[str, Any]]:
    """Load AIR gap classifications from state file.

    Returns:
        List of gap classifications for this session, or empty list if none.
    """
    session_id = _get_session_id_from_env()
    state_file = _STATE_DIR / f"air_gaps_{session_id}.json"
    if not state_file.exists():
        return []
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


# Regex patterns compiled at module level for performance (PERF-001)
# Require full markdown section headers to avoid garbage matches on casual text
#
# FIX for Python 3.14: \Z in lookahead (?=\Z) is broken — \Z only works as $ anchor.
# Use (?=\n\n|\n\*\*|\Z) lookahead to stop before another header or end-of-string.
# Pattern structure: **...header...** then optional space then content captured.
# Use [^*]* (zero-or-more) in a non-greedy match between ** delimiters.
_RE_PROBLEM = re.compile(
    r"\*\*(?:what was the )?[^*]*problem[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_RE_USER_PROBLEM = re.compile(
    r"\*\*[^*]*problem[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_RE_FIX = re.compile(
    r"\*\*(?:what was the )?[^*]*fix[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)"
    r"|\*\*root cause[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)"
    r"|\*\*fix applied[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_RE_ACTION = re.compile(
    r"\*\*(?:what did we )?[^*]*do[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)"
    r"|\*\*action[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)"
    r"|## Files Changed\s*\n\s*[-*]\s*(.+)",
    re.DOTALL | re.IGNORECASE,
)
_RE_TOOL = re.compile(
    r"(?:Edit|Write)[^\n]+\n[^\n]*\s*([^\n]+\.py[^\n]*)",
    re.IGNORECASE,
)
_RE_DECISION = re.compile(
    r"\*\*(?:[^*]*decision)[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)"
    r"|\[DECISION\]\s*(.+?)(?=\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_RE_OUTCOME = re.compile(
    r"\*\*(?:[^*]*outcome)[^*]*\*\*(?:\s+)?(.+?)(?=\n\n|\n\*\*|\Z)"
    r"|(?:completed|verified|done|succeeded)(?:\s+(?:task|fix|implementation)\s+(?:of\s+)?(.+?))?"
    r"|(?:Task|Fix) #?\d+: ([^\n]+)",
    re.DOTALL | re.IGNORECASE,
)


# Constants for session chain building
_MAX_RECENT_SESSIONS = 30  # 30 sessions balances coverage vs parse time (~5 min for typical session)
# Windows short-path prefix normalization (e.g., cts\ -> C:\Users\brsth\)
_WINDOWS_SHORT_PATH_PREFIX = "cts\\"
# Max lines to scan in a transcript file to detect if it's a real transcript
# 200 lines catches real sessions (metadata + content) while skipping noise files
_TRANSCRIPT_SCAN_LINES = 200

# Constants for priority scoring (_calculate_priority_score)
_PRIORITY_ENTRY_COUNT_MAX = 25  # Max points for entry count
_PRIORITY_ENTRY_DIVISOR = 4  # Entry count divisor (entry_count/4 yields max at 100 entries)
_PRIORITY_TOKEN_USAGE_MAX = 30  # Max points for token usage
_PRIORITY_TOKEN_SCALE = 100000  # Token count denominator for log-scale scoring
_PRIORITY_SEMANTIC_MULTIPLIER = 3  # Points per semantic item
_PRIORITY_SEMANTIC_MAX = 30  # Max points for semantic richness
_PRIORITY_DURATION_HOURS = 15  # Points for multi-hour session
_PRIORITY_DURATION_MAX = 12  # Max points for minutes-based duration
_PRIORITY_DURATION_DIVISOR = 4  # Duration divisor (minutes/4 for per-minute points)

# Constants for semantic extraction quality filtering
_MIN_EXTRACT_LEN = 15  # Minimum character length for extracted strings
_MIN_MULTILINE_LEN = 30  # Minimum length for multi-line strings
_MIN_USER_PROBLEM_LEN = 20  # Minimum length for user problem matches

# Constants for narrative extraction (Domain 3: Magic numbers)
_MIN_REQUEST_LENGTH = 30  # Minimum length for user request to be considered
_MAX_REQUEST_LENGTH = 500  # Maximum length for truncated original requests
_MAX_ITEM_LENGTH = 200  # Maximum length for decision/step/question items
_MIN_STEP_LENGTH = 10   # Minimum length for handoff steps
_MIN_QUESTION_LENGTH = 15  # Minimum length for open questions
_MAX_TEXT_WINDOW = 1000  # Text window for handoff pattern search
_MAX_ITEMS_PER_FIELD = 5  # Maximum items per narrative field
_MAX_ACTION_COUNT = 10  # Maximum actions to scan for modified files
_MAX_PATH_LENGTH = 100  # Maximum length for file path/state item truncation
_MAX_DEDUP_LENGTH = 300  # Maximum length for deduplication
_MAX_BLOCKED_ITEMS = 3  # Maximum blocked state items


def _filter(items: list[str]) -> list[str]:
    """Filter out low-quality extractions: too short, backticks, or ASCII art."""
    result = []
    for s in items:
        s = s.strip()
        # Discard: short strings, backtick noise, ASCII art chars, control sequences
        if len(s) < _MIN_EXTRACT_LEN:
            continue
        if s.startswith("`") or s.startswith("-" * 40):
            continue
        if "\n" in s and len(s) < _MIN_MULTILINE_LEN:  # Multi-line but very short
            continue
        result.append(s)
    return result


def _parse_last_session_summary(entries: list[dict[str, Any]]) -> str | None:
    """Parse ## Last Session Summary block from first 10 entries.

    Args:
        entries: Transcript entries

    Returns:
        Parsed last_goal string, or None if no valid summary found
    """
    if len(entries) < 3:
        return None

    raw_text = ""
    for e in entries[:10]:
        raw_text += e.get("text", "") or e.get("content", "") + "\n"

    summary_regex = re.compile(
        r"##\s*Last\s*Session\s*Summary\s*\n(?:.*?\n)*?(?=\n##|\Z)",
        re.DOTALL
    )
    match = summary_regex.search(raw_text)
    if not match:
        return None

    summary_block = match.group(0)
    when_m = re.search(r"\*\*When:\*\*\s*(.+)", summary_block)
    dur_m = re.search(r"\*\*Duration:\*\*\s*~?(\d+)h\s*(\d+)m", summary_block)
    if not when_m or not dur_m:
        return None

    h = int(dur_m.group(1) or 0)
    m = int(dur_m.group(2) or 0)
    body_start = summary_block.find("**When:**")
    body = summary_block[body_start:] if body_start >= 0 else summary_block
    body_stripped = re.sub(r'\n\s*\n\s*$', '', body.strip())
    if (h * 60 + m) > 0 and len(body_stripped) > 50 and not body_stripped.startswith("#"):
        return f"[Prior session: {when_m.group(1).strip()}, ~{h}h {m}m] {body_stripped[:200]}"
    return None


def build_session_chain(cwd: Path | None = None) -> list[dict[str, Any]]:
    """Build a chronological chain of recent sessions for the current project.

    Loads sessions from sessions-index.json, filters to those with existing transcript
    files, takes the N most recent, parses each transcript, and returns the parsed data
    in the format expected by format_recap().

    Args:
        cwd: Optional working directory override (defaults to Path.cwd())

    Returns:
        List of parsed session summaries sorted by created timestamp (oldest first)
    """
    if cwd is None:
        cwd = Path.cwd()

    # Derive project root from cwd traversal
    project_root = get_project_root()

    index_path = _get_sessions_index_path(project_root)
    if not index_path:
        return []

    entries = load_sessions_index(index_path)
    if not entries:
        return []

    # Filter to entries with existing transcript files, newest first
    recent_with_transcript = []
    for entry in reversed(entries):  # newest first
        transcript_path_str = entry.get("transcript_path", "")
        if not transcript_path_str:
            continue
        tp = Path(transcript_path_str)
        # Normalize Windows short-path prefix (e.g., cts\ -> C:\Users\...)
        if str(tp).startswith(_WINDOWS_SHORT_PATH_PREFIX):
            tp = Path(str(tp).replace("cts\\", str(Path.home()).replace("\\", "/") + "/"))
        if tp.exists() and _is_transcript_file(tp):
            recent_with_transcript.append(entry)
            if len(recent_with_transcript) >= _MAX_RECENT_SESSIONS:
                break

    # Reverse to oldest-first for chronological display
    recent_with_transcript.reverse()

    # Parse each transcript and return summaries in format_recap format
    result: list[dict[str, Any]] = []
    for entry in recent_with_transcript:
        transcript_path_str = entry.get("transcript_path", "")
        if not transcript_path_str:
            continue
        tp = Path(transcript_path_str)
        if str(tp).startswith("cts" + "\\"):
            tp = Path(str(tp).replace("cts\\", str(Path.home()).replace("\\", "/") + "/"))
        if not tp.exists():
            continue
        entries_list = load_transcript_entries(str(tp))
        summaries = extract_sessions_from_transcript(entries_list)
        if summaries:
            # Use the first (and typically only) summary from this file
            summary = summaries[0]
            # Attach the index goal if the parsed one is empty
            if not summary.get("last_goal"):
                idx_goal = entry.get("summary") or entry.get("last_goal", "")
                if idx_goal:
                    summary["last_goal"] = idx_goal[:200]
            result.append(summary)

    return result


def _find_project_transcript() -> Path | None:
    """Find the most recent project transcript file with actual user/assistant content.

    Searches in ~/.claude/projects/{project}/ for .jsonl files and returns the most
    recently modified one that contains real transcript entries (user or assistant types).

    Returns:
        Path to the most recent transcript file, or None
    """
    # Find project root to locate transcript directory
    project_root = _find_project_root_for_transcripts()
    if not project_root:
        return None

    transcript_dir = project_root
    if not transcript_dir.exists():
        return None

    # Find .jsonl files with real transcript content
    candidates = _scan_transcript_dir(transcript_dir)

    if not candidates:
        # Fallback: try home directory transcript storage
        # This handles the case where cwd-based project root has no transcripts
        # but user's home directory (~/.claude/projects) contains transcript files
        home_transcripts = Path.home() / ".claude" / "projects"
        if home_transcripts.exists() and home_transcripts != transcript_dir:
            # Check both flat .jsonl files and nested project/*.jsonl files
            # (transcripts live in project subdirs like ~/.claude/projects/P--/*.jsonl)
            for glob_pattern in ["*.jsonl", "*/*.jsonl"]:
                for jsonl_file in home_transcripts.glob(glob_pattern):
                    try:
                        mtime = jsonl_file.stat().st_mtime
                        if _is_transcript_file(jsonl_file):
                            candidates.append((mtime, jsonl_file))
                    except OSError:
                        continue

    if not candidates:
        return None

    # Return most recently modified
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _find_project_root_for_transcripts() -> Path | None:
    """Find the project root that contains transcript .jsonl files."""
    cwd = Path.cwd()

    # Look for .claude/projects/{project}/ pattern
    for parent in cwd.parents:
        projects_dir = parent / ".claude" / "projects"
        if projects_dir.is_dir():
            # Find the most recent project directory with transcripts
            try:
                for project in sorted(
                    projects_dir.iterdir(),
                    key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
                    reverse=True,
                ):
                    if project.is_dir():
                        # Projects that ARE the root (e.g. P--) store .jsonl at project level
                        # Projects that are subdirs (e.g. packages/*) have .claude subdir
                        # Check both patterns: project has .jsonl directly OR has .claude subdir with .jsonl
                        if any(project.glob("*.jsonl")):
                            return project
                        if (project / ".claude").exists() and any(
                            (project / ".claude").glob("**/*.jsonl")
                        ):
                            return project
            except OSError:
                continue
        claude_dir = parent / ".claude"
        if claude_dir.is_dir():
            # Maybe transcripts are directly under ~/.claude/projects/P--/
            for jsonl_file in parent.glob("*.jsonl"):
                return parent

    # Fallback: check cwd directly
    if any(cwd.glob("*.jsonl")):
        return cwd

    # Check home directory
    home_transcripts = Path.home() / ".claude" / "projects"
    if home_transcripts.is_dir():
        try:
            for project in sorted(
                home_transcripts.iterdir(),
                key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
                reverse=True,
            ):
                if project.is_dir() and any(project.glob("*.jsonl")):
                    return project
        except OSError:
            pass

    return None


def load_transcript_entries(transcript_path: str | None) -> list[dict[str, Any]]:
    """Load and parse transcript JSONL file.

    Args:
        transcript_path: Path to transcript file

    Returns:
        List of transcript entries
    """
    if not transcript_path:
        return []

    path = Path(transcript_path)
    if not path.exists():
        return []

    try:
        entries = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    entries.append(entry)
        return entries
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load transcript %s: %s", path, exc)
        return []


def extract_sessions_from_transcript(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract session summaries from transcript entries.

    Args:
        entries: Transcript entries

    Returns:
        List of session summaries with goals, timestamps, message counts
    """
    if not entries:
        return []

    # Filter out file-history-snapshot entries (metadata, not real transcript content)
    # and skip entries with empty type
    # Note: entries WITHOUT sessionId are NOT filtered - they belong to the current session
    real_entries = [
        e
        for e in entries
        if e.get("type") not in ("file-history-snapshot", None, "")
    ]

    sessions = []
    current_session_id = None
    current_session_entries = []

    for entry in real_entries:
        session_id = entry.get("sessionId")  # Transcripts use "sessionId" not "session_chain_id"
        # None sessionId means metadata/tool_result — append to current session, don't split
        if session_id is None:
            current_session_entries.append(entry)
            continue
        if session_id != current_session_id:
            # Session boundary - save current session
            if current_session_entries:
                sessions.append(_summarize_session(current_session_entries, current_session_id))
            current_session_id = session_id
            current_session_entries = []
        current_session_entries.append(entry)

    # Don't forget the last session
    if current_session_entries:
        sessions.append(_summarize_session(current_session_entries, current_session_id))

    return sessions


def _extract_content(entry: dict[str, Any]) -> str:
    """Extract text content from a transcript entry, skipping tool_result blocks.

    Args:
        entry: A transcript entry dict with optional 'content' or 'message.content' fields

    Returns:
        The text content, or '' if no meaningful content found
    """
    content = entry.get("content")
    if content is None:
        message = entry.get("message", {})
        content = message.get("content")
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            # Skip tool_result blocks — they contain command output, not user intent
            if block.get("type") == "tool_result":
                continue
            text = block.get("text", "")
            if text:
                return text
        # All blocks were skipped (e.g., all tool_result) — return empty
        return ""


def _condense_transcript(
    entries: list[dict[str, Any]],
    max_chars: int = 2000,
) -> str:
    """Extract meaningful text from entries within a character budget.

    Skips tool_result blocks (command output noise). Accumulates user/assistant
    message text until max_chars is reached, then stops.

    The LLM (this agent) uses this raw text as evidence for synthesis —
    this replaces both regex extraction and external LLM calls.

    Args:
        entries: Transcript entries for a session
        max_chars: Maximum characters to return

    Returns:
        Condensed transcript text for LLM reasoning
    """
    result_parts: list[str] = []
    total = 0

    for entry in entries:
        text = _extract_content(entry)
        if not text:
            continue

        # Strip <local-command-*> and <command-*> XML blocks — transcript infrastructure, not evidence
        text = re.sub(r"<(?:local-)?command-\w+>.*?</(?:local-)?command-\w+>", "", text, flags=re.DOTALL)
        text = text.strip()
        if not text:
            continue

        estimate = len(text)

        if total + estimate > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                result_parts.append(text[:remaining] + "[…]")
            break

        result_parts.append(text)
        total += estimate

    return "\n---\n".join(result_parts)


def _regex_extract_semantic(
    entries: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Fallback regex-based semantic extraction (for when LM Studio is unavailable).

    Pattern-matches against structured output sections that appear in Claude Code responses.
    Each returned list contains unique, truncated entries.

    Args:
        entries: Transcript entries for a session

    Returns:
        Dict with keys: problems, fixes, actions, decisions, outcomes
    """
    all_text: list[str] = []
    for entry in entries:
        content = entry.get("content")
        if content is None:
            message = entry.get("message", {})
            content = message.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            all_text.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if text:
                        all_text.append(text)

    combined = "\n".join(all_text)

    # Quality thresholds moved to module level (_MIN_EXTRACT_LEN, _MIN_MULTILINE_LEN, _MIN_USER_PROBLEM_LEN)
    # _filter moved to module level

    problems: list[str] = []
    for match in _RE_PROBLEM.finditer(combined):
        problems.append(match.group(1).lstrip("* "))
    user_texts = [e.get("content", "") for e in entries if e.get("type") == "user"]
    for text in user_texts[:3]:
        for match in _RE_USER_PROBLEM.finditer(str(text)[:500]):
            if len(match.group(1)) > _MIN_USER_PROBLEM_LEN:
                problems.append(match.group(1).strip())

    fixes: list[str] = []
    for match in _RE_FIX.finditer(combined):
        fixes.append((match.group(1) or match.group(2) or match.group(3) or "").lstrip("* "))

    actions: list[str] = []
    for match in _RE_ACTION.finditer(combined):
        actions.append((match.group(1) or match.group(2) or match.group(3) or "").lstrip("* "))
    for match in _RE_TOOL.finditer(combined):
        if match.group(1) and len(match.group(1)) > 10:
            actions.append(match.group(1).strip())

    decisions: list[str] = []
    for match in _RE_DECISION.finditer(combined):
        decisions.append((match.group(1) or match.group(2) or "").lstrip("* "))

    outcomes: list[str] = []
    for match in _RE_OUTCOME.finditer(combined):
        outcomes.append((match.group(1) or match.group(2) or match.group(3) or "").lstrip("* "))

    # Apply quality filter before returning
    problems = _filter(problems)
    fixes = _filter(fixes)
    actions = _filter(actions)
    decisions = _filter(decisions)
    outcomes = _filter(outcomes)

    return {
        "problems": _unique_truncate(problems),
        "fixes": _unique_truncate(fixes),
        "actions": _unique_truncate(actions),
        "decisions": _unique_truncate(decisions),
        "outcomes": _unique_truncate(outcomes),
    }


def _unique_truncate(items: list[str], max_len: int = 150) -> list[str]:
    """Deduplicate while preserving order, then truncate."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            if len(normalized) > max_len:
                normalized = normalized[: max_len - 3] + "..."
            result.append(normalized)
    return result


def _extract_semantic_content(
    entries: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Extract semantic content (problems, fixes, actions, decisions, outcomes) from transcript entries.

    Uses strict regex patterns that require full markdown section headers to avoid garbage matches.
    Results are filtered for minimum quality (length >= 15 chars, no backtick noise, no ASCII art).

    Args:
        entries: Transcript entries for a session

    Returns:
        Dict with keys: problems, fixes, actions, decisions, outcomes
    """
    return _regex_extract_semantic(entries)


def _calculate_session_duration(entries: list[dict[str, Any]]) -> str | None:
    """Calculate session duration from first and last entry timestamps.

    Args:
        entries: Transcript entries for a session

    Returns:
        Human-readable duration string (e.g., "8h 45m", "14m") or None if timestamps unavailable
    """
    if not entries:
        return None

    # Extract timestamps from entries
    timestamps = []
    for entry in entries:
        # Try multiple timestamp fields that may exist in transcript entries
        for ts_field in ("timestamp", "time", "created", "createdAt"):
            ts_val = entry.get(ts_field)
            if ts_val is not None:
                try:
                    # Handle both Unix millis (int) and ISO strings
                    if isinstance(ts_val, (int, float)):
                        timestamps.append(float(ts_val))
                    elif isinstance(ts_val, str):
                        # Parse ISO format
                        dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                        timestamps.append(dt.timestamp())
                except (ValueError, TypeError):
                    pass
                break  # Found a timestamp, don't check other fields for this entry

    if len(timestamps) < 2:
        return None

    first_ts = min(timestamps)
    last_ts = max(timestamps)
    duration_seconds = (last_ts - first_ts) / 1000  # Convert millis to seconds

    # Format duration
    if duration_seconds < 60:
        return f"{int(duration_seconds)}s"
    elif duration_seconds < 3600:
        minutes = int(duration_seconds / 60)
        return f"{minutes}m"
    else:
        hours = int(duration_seconds / 3600)
        minutes = int((duration_seconds % 3600) / 60)
        if minutes > 0:
            return f"{hours}h {minutes}m"
        return f"{hours}h"


def _calculate_token_usage(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Extract token usage from transcript entries.

    Args:
        entries: Transcript entries for a session

    Returns:
        Dict with input_tokens, output_tokens, total_tokens
    """
    total_input = 0
    total_output = 0

    for entry in entries:
        # Check for usage metadata in various locations
        usage = entry.get("usage")
        if usage is None:
            message = entry.get("message", {})
            usage = message.get("usage")

        if isinstance(usage, dict):
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_input + total_output,
    }


def _calculate_priority_score(
    entry_count: int,
    duration_str: str | None,
    semantic_content: dict[str, list[str]],
    token_usage: dict[str, int],
) -> float:
    """Calculate session importance score for prioritization.

    Higher scores indicate more important sessions (more context-dense).

    Args:
        entry_count: Number of transcript entries
        duration_str: Human-readable duration string or None
        semantic_content: Dict with problems, fixes, actions, decisions, outcomes
        token_usage: Token usage dict

    Returns:
        Priority score (0-100)
    """
    score = 0.0

    # Factor 1: Entry count
    # More entries = more substantial interaction
    score += min(entry_count / _PRIORITY_ENTRY_DIVISOR, _PRIORITY_ENTRY_COUNT_MAX)

    # Factor 2: Token usage
    # High token count = deep technical work
    total_tokens = token_usage.get("total_tokens", 0)
    if total_tokens > 0:
        # Log-scale to avoid extreme dominance
        score += min(
            _PRIORITY_TOKEN_USAGE_MAX * (total_tokens / _PRIORITY_TOKEN_SCALE),
            _PRIORITY_TOKEN_USAGE_MAX,
        )

    # Factor 3: Semantic richness
    # Problems, fixes, actions = real work done
    semantic_items = (
        len(semantic_content.get("problems", []))
        + len(semantic_content.get("fixes", []))
        + len(semantic_content.get("actions", []))
        + len(semantic_content.get("decisions", []))
        + len(semantic_content.get("outcomes", []))
    )
    score += min(semantic_items * _PRIORITY_SEMANTIC_MULTIPLIER, _PRIORITY_SEMANTIC_MAX)

    # Factor 4: Duration
    # Longer sessions = more sustained work
    if duration_str:
        if "h" in duration_str:
            score += _PRIORITY_DURATION_HOURS
        elif "m" in duration_str:
            minutes = int(duration_str.replace("m", "").replace("h", "").strip())
            score += min(minutes / _PRIORITY_DURATION_DIVISOR, _PRIORITY_DURATION_MAX)

    return min(score, 100.0)


def truncate(s: str, max_len: int = 100) -> str:
    """Truncate string to max_len, appending ellipsis if truncated."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


_SKIP_SUFFIXES = frozenset({".json", ".lock", ".pyc", ".pyo"})
_SKIP_SEGMENTS = frozenset({"__pycache__", "node_modules", ".git"})


def _extract_modified_files(entries: list[dict[str, Any]]) -> list[str]:
    """Scan transcript entries for Edit/Write tool_use blocks and extract file paths.

    Skips noise files (.json, .lock, __pycache__/, node_modules/).

    Args:
        entries: Transcript entries for a session

    Returns:
        Deduplicated list of file paths
    """
    import os

    seen: set[str] = set()
    result: list[str] = []

    for entry in entries:
        content = entry.get("content")
        if content is None:
            content = entry.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Edit", "Write"):
                continue
            inp = block.get("input", {})
            if not isinstance(inp, dict):
                continue
            path = inp.get("file_path", "")
            if not path or path in seen:
                continue
            _, ext = os.path.splitext(path)
            if ext.lower() in _SKIP_SUFFIXES:
                continue
            if any(seg in path for seg in _SKIP_SEGMENTS):
                continue
            seen.add(path)
            result.append(path)

    return result


def _extract_first_user_request(entries: list[dict[str, Any]]) -> str | None:
    """Extract the first meaningful user request from transcript entries.

    Args:
        entries: Transcript entries for a session

    Returns:
        First user request string, or None if not found
    """
    for entry in entries:
        if entry.get("type") != "user":
            continue
        text = _extract_content(entry)
        if not text:
            continue
        # Skip system prompts, skill loads, permission requests
        skip_patterns = [
            "Base directory",
            "Base directory for this skill",
            "You are",
            "## System",
            "You have been invoked",
            "is available at",
            "Skill:",
            "/cc-skills",
        ]
        if any(pattern in text for pattern in skip_patterns):
            continue
        # Skip very short entries (likely acknowledgments)
        if len(text.strip()) < _MIN_REQUEST_LENGTH:
            continue
        return text[:_MAX_REQUEST_LENGTH]  # Truncate long requests
    return None


def _safe_finditer(pattern: str | re.Pattern[str], text: str, flags: int = 0) -> list[re.Match[str]]:
    """Safely execute re.finditer with error handling for invalid patterns.

    Args:
        pattern: Regex pattern (string or compiled)
        text: Text to search
        flags: Optional regex flags (only used if pattern is string)

    Returns:
        List of match objects, or empty list on error
    """
    try:
        return list(re.finditer(pattern, text, flags))
    except (re.error, TypeError):
        return []


def _safe_search(pattern: str | re.Pattern[str], text: str, flags: int = 0) -> re.Match[str] | None:
    """Safely execute re.search with error handling for invalid patterns.

    Args:
        pattern: Regex pattern (string or compiled)
        text: Text to search
        flags: Optional regex flags (only used if pattern is string)

    Returns:
        Match object or None on error/no match
    """
    try:
        return re.search(pattern, text, flags)
    except (re.error, TypeError):
        return None


def _extract_session_narrative(
    entries: list[dict[str, Any]],
    semantic: dict[str, list[str]],
) -> dict[str, Any]:
    """Build a handoff-quality narrative from transcript entries.

    Extracts:
    - original_request: first meaningful user message
    - what_was_done: synthesized summary of actions taken
    - decisions_made: explicit decisions from transcript
    - current_state: what's modified and working
    - next_steps: pending work from handoff blocks

    Args:
        entries: Transcript entries for a session
        semantic: Dict from _extract_semantic_content

    Returns:
        Narrative dict with keys: original_request, what_was_done, decisions_made,
        current_state, next_steps, open_questions
    """
    narrative: dict[str, Any] = {
        "original_request": _extract_first_user_request(entries),
        "what_was_done": [],
        "decisions_made": [],
        "current_state": {"modified": [], "working": [], "blocked": []},
        "next_steps": [],
        "open_questions": [],
    }

    # Compile what was done from semantic extraction
    actions = semantic.get("actions", [])
    fixes = semantic.get("fixes", [])
    outcomes = semantic.get("outcomes", [])

    for fix in fixes[:3]:
        narrative["what_was_done"].append(f"Fixed: {fix}")
    for action in actions[:5]:
        if action not in narrative["what_was_done"]:
            narrative["what_was_done"].append(f"Action: {action}")
    for outcome in outcomes[:3]:
        if outcome not in narrative["what_was_done"]:
            narrative["what_was_done"].append(f"Outcome: {outcome}")

    # Extract decisions
    for decision in semantic.get("decisions", [])[:5]:
        if decision.strip():
            narrative["decisions_made"].append(decision.strip())

    # Parse explicit decisions from transcript text
    decision_patterns = [
        r"(?:[Ww]e )?[dD]ecided[:\s]+(.+)",
        r"[Dd]ecision[:\s]+(.+)",
        r"Choice[:\s]+(.+)",
        r"(?:[Gg]oing with|[Ss]elected)[:\s]+(.+)",
    ]
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        text = _extract_content(entry)
        if not text:
            continue
        for pattern in decision_patterns:
            matches = _safe_finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                decision_text = match.group(1).strip()
                if decision_text and decision_text not in narrative["decisions_made"]:
                    narrative["decisions_made"].append(decision_text[:_MAX_ITEM_LENGTH])

    # Parse handoff blocks for next steps
    handoff_pattern = r"(?:next step|pending|remaining|todo|to do|action item)[:\s]+(.+?)(?:\n\n|\n\*\*|\Z)"
    for entry in entries:
        text = _extract_content(entry)
        if not text:
            continue
        for match in _safe_finditer(handoff_pattern, text[:_MAX_TEXT_WINDOW], re.IGNORECASE | re.DOTALL):
            step = match.group(1).strip()
            if step and len(step) > _MIN_STEP_LENGTH:
                narrative["next_steps"].append(step[:_MAX_ITEM_LENGTH])
        # Also check for "## Last Session Summary" blocks
        if "## Last Session Summary" in text or "Next Immediate Action" in text:
            next_action_match = _safe_search(
                r"(?:next immediate action|remaining|nxt step)[:\s]*\n(?:[0-9]+\.\s*(.+?)(?:\n|$))+",
                text,
                re.IGNORECASE,
            )
            if next_action_match:
                for line in next_action_match.group(0).split("\n"):
                    line = line.strip()
                    if line and not line.lower().startswith("next"):
                        narrative["next_steps"].append(line[:_MAX_ITEM_LENGTH])

    # Extract open questions (explicit uncertainty markers)
    question_patterns = [
        r"(?:open question|unresolved|uncertain|not sure|don't know)[:\s]+(.+)",
        r"(?:blocked by|depends on|waiting for)[:\s]+(.+)",
        r"(?:^|[\n\r]\s*|\. )(?:what if|how to)[:\s]+(.+?)(?:\?|$)",
    ]
    for entry in entries:
        text = _extract_content(entry)
        if not text:
            continue
        for pattern in question_patterns:
            matches = _safe_finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                question = match.group(1).strip()
                if question and len(question) > _MIN_QUESTION_LENGTH:
                    narrative["open_questions"].append(question[:_MAX_ITEM_LENGTH])

    # Extract current state: modified, working, blocked
    # Modified files from semantic extraction
    for action in actions[:_MAX_ACTION_COUNT]:
        if "edit" in action.lower() or "modify" in action.lower() or "fix" in action.lower():
            # Extract file path from action text if possible
            file_match = _safe_search(r'([A-Za-z]:\\\\[^"\'\s]+|["\']?[\w.-]+\.[a-z]{2,4}["\']?)', action, re.IGNORECASE)
            if file_match:
                file_path = file_match.group(1)
                narrative["current_state"]["modified"].append(file_path[:_MAX_PATH_LENGTH])

    # Working state from transcript patterns
    working_patterns = [
        r"(?:now\s+)?working\s+as\s+expected",
        r"(?:is\s+)?(?:fully\s+)?(?:operational|functional)",
        r"(?:test|verification|check)\s+succee[ds]",
        r"(?:ready|deployed|launched|complete)",
    ]
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        text = _extract_content(entry)
        if not text:
            continue
        for pattern in working_patterns:
            if _safe_search(pattern, text, re.IGNORECASE):
                # Extract what's working from context
                working_match = _safe_search(r'(?:working|operational|functional|success)(?:\s+(?:for|with|on)?\s+([^.!\n]+))?', text, re.IGNORECASE)
                if working_match:
                    working_item = working_match.group(1).strip() if working_match.group(1) else "system"
                else:
                    working_item = "system"
                if working_item and working_item not in narrative["current_state"]["working"]:
                    narrative["current_state"]["working"].append(working_item[:_MAX_PATH_LENGTH])
                break

    # Blocked state from transcript patterns
    blocked_patterns = [
        r"(?:blocked|stuck|waiting\s+(?:on|for)|blocked\s+by)",
        r"(?:cannot|unable to|fail(?:ed|s?\s+to))",
        r"(?:error|issue|bug)(?:\s+(?:in|at|on))?",
    ]
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        text = _extract_content(entry)
        if not text:
            continue
        for pattern in blocked_patterns:
            if _safe_search(pattern, text, re.IGNORECASE):
                # Extract what's blocked from context
                blocked_match = _safe_search(r'(?:blocked|waiting|stuck)(?:\s+(?:on|for|by)\s+)?([^.!\n]+)', text, re.IGNORECASE)
                if blocked_match:
                    blocked_item = blocked_match.group(1).strip() if blocked_match.group(1) else "progress"
                else:
                    blocked_item = "progress"
                if blocked_item and blocked_item not in narrative["current_state"]["blocked"]:
                    narrative["current_state"]["blocked"].append(blocked_item[:_MAX_PATH_LENGTH])
                break

    # Deduplicate and limit
    narrative["what_was_done"] = _unique_truncate(narrative["what_was_done"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_ITEMS_PER_FIELD]
    narrative["decisions_made"] = _unique_truncate(narrative["decisions_made"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_ITEMS_PER_FIELD]
    narrative["next_steps"] = _unique_truncate(narrative["next_steps"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_ITEMS_PER_FIELD]
    narrative["open_questions"] = _unique_truncate(narrative["open_questions"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_ITEMS_PER_FIELD]
    narrative["current_state"]["modified"] = _unique_truncate(narrative["current_state"]["modified"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_ITEMS_PER_FIELD]
    narrative["current_state"]["working"] = _unique_truncate(narrative["current_state"]["working"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_ITEMS_PER_FIELD]
    narrative["current_state"]["blocked"] = _unique_truncate(narrative["current_state"]["blocked"], max_len=_MAX_DEDUP_LENGTH)[:_MAX_BLOCKED_ITEMS]

    return narrative


def _summarize_session(entries: list[dict[str, Any]], session_id: str | None) -> dict[str, Any]:
    """Summarize a session from its entries.

    Args:
        entries: Transcript entries for this session
        session_id: Session chain ID

    Returns:
        Session summary dict with semantic content
    """
    user_entries = [e for e in entries if e.get("type") == "user"]
    assistant_entries = [e for e in entries if e.get("type") == "assistant"]

    # CHANGE-004: Parse ## Last Session Summary block from first 10 entries
    last_goal_from_summary = _parse_last_session_summary(entries)

    # Calculate session stats
    duration = _calculate_session_duration(entries)
    token_usage = _calculate_token_usage(entries)

    # last_goal: find the last user entry that contains meaningful user intent
    # Skip entries whose content is ONLY tool_result blocks (transcript stores tool output as type=="user")
    # CHANGE-004: Prior session summary takes precedence over reverse-chronological entry scan
    if last_goal_from_summary:
        last_goal = last_goal_from_summary
    else:
        last_goal = ""
        for entry in reversed(user_entries):
            content = entry.get("content")
            if content is None:
                message = entry.get("message", {})
                content = message.get("content")
            # Skip entries that are entirely tool_result blocks (no user intent)
            if isinstance(content, list):
                blocks = [b for b in content if isinstance(b, dict)]
                if blocks and all(b.get("type") == "tool_result" for b in blocks):
                    continue  # Entire entry is tool result output — not a goal
                # Mixed content: extract from the first text block
                last_goal = _extract_content(entry)
                break
            elif isinstance(content, str) and content.strip():
                last_goal = content.strip()
                break

    # Extract semantic content
    semantic = _extract_semantic_content(entries)

    # Extract handoff-quality narrative
    narrative = _extract_session_narrative(entries, semantic)

    # Calculate priority score
    priority = _calculate_priority_score(
        entry_count=len(entries),
        duration_str=duration,
        semantic_content=semantic,
        token_usage=token_usage,
    )

    return {
        "session_id": session_id or "unknown",
        "entry_count": len(entries),
        "user_message_count": len(user_entries),
        "assistant_message_count": len(assistant_entries),
        "duration": duration,
        "token_usage": token_usage,
        "priority_score": priority,
        "last_goal": truncate(str(last_goal)),
        "problem": semantic["problems"][0] if semantic["problems"] else None,
        "fix": semantic["fixes"][0] if semantic["fixes"] else None,
        "action": semantic["actions"][0] if semantic["actions"] else None,
        "problems": semantic["problems"],
        "fixes": semantic["fixes"],
        "actions": semantic["actions"],
        "decisions": semantic["decisions"],
        "outcomes": semantic["outcomes"],
        "modified_files": _extract_modified_files(entries),
        # Raw transcript text for LLM reasoning — replaces garbled regex extraction
        "transcript": _condense_transcript(entries),
        # Handoff-quality narrative sections
        "original_request": narrative.get("original_request"),
        "what_was_done": narrative.get("what_was_done", []),
        "decisions_made": narrative.get("decisions_made", []),
        "current_state": narrative.get("current_state", {}),
        "next_steps": narrative.get("next_steps", []),
        "open_questions": narrative.get("open_questions", []),
    }


def format_brief(sessions: list[dict[str, Any]]) -> str:
    """Format a brief catch-up summary from sessions.

    Args:
        sessions: List of session summaries

    Returns:
        Brief catch-up string
    """
    if not sessions:
        return "No session history found."

    # Get the most recent session
    latest = sessions[-1]

    parts = []
    parts.append("Last session in this terminal:")
    parts.append(f"- Goal: {latest['last_goal']}")

    if latest.get("last_goal"):
        parts.append(f"- Current goal: {latest['last_goal']}")

    parts.append(
        f"- Messages: {latest['user_message_count']} user, {latest['assistant_message_count']} assistant"
    )

    # Add duration if available
    if latest.get("duration"):
        parts.append(f"- Duration: {latest['duration']}")

    # Add priority score if available
    priority = latest.get("priority_score", 0)
    if priority > 0:
        parts.append(f"- Priority Score: {priority:.1f}/100")

    return "\n".join(parts)


def _handoff_text(value: Any) -> str:
    """Turn extracted narrative values into concise, deterministic text."""
    if isinstance(value, dict):
        for key in ("description", "text", "title", "issue", "question", "statement"):
            if value.get(key):
                return str(value[key])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _handoff_items(session: dict[str, Any], *fields: str, limit: int = 5) -> list[str]:
    """Collect and deduplicate narrative items from a session summary."""
    items: list[str] = []
    for field in fields:
        value = session.get(field, [])
        if isinstance(value, (str, dict)):
            value = [value]
        for item in value or []:
            text = _handoff_text(item)
            if text and text not in items:
                items.append(text)
            if len(items) >= limit:
                return items
    return items


def _handoff_status(session: dict[str, Any]) -> str:
    state = session.get("current_state") or {}
    active = session.get("active_work") or {}
    if state.get("blocked") or str(active.get("status", "")).lower() == "blocked":
        return "blocked"
    if state.get("working") or active.get("description"):
        return "partial"
    if session.get("outcomes") or session.get("what_was_done"):
        return "complete"
    return "partial"


def format_handoff(sessions: list[dict[str, Any]], terminal_id: str) -> str:
    """Render the default recap as a resume-oriented handoff.

    The existing ``format_recap`` renderer remains the detailed/full view. This
    renderer deliberately keeps evidence bounded; ``/recap full`` retains the
    unabridged session history and raw context.
    """
    latest = sessions[-1] if sessions else {}
    status = _handoff_status(latest) if latest else "partial"
    outcome_items = _handoff_items(latest, "outcomes", "what_was_done", limit=3)
    outcome = outcome_items[0] if outcome_items else "No verified outcome was extracted."
    active = latest.get("active_work") or {}
    next_items = _handoff_items(latest, "next_actions", "next_steps", limit=5)
    immediate = active.get("next") or (next_items[0] if next_items else "none — session is closed")
    blocked = _handoff_items(latest, "known_issues", limit=5)
    state = latest.get("current_state") or {}
    blocked.extend(item for item in state.get("blocked", []) if item not in blocked)
    risks = _handoff_items(latest, "known_issues", "open_questions", limit=8)
    decisions = _handoff_items(latest, "decisions_made", "decisions", limit=8)

    artifacts: list[str] = []
    for session in sessions:
        for path in session.get("modified_files", []) or []:
            path = str(path)
            if path and path not in artifacts:
                artifacts.append(path)
            if len(artifacts) >= 10:
                break
        if len(artifacts) >= 10:
            break

    lines = [
        "# Session Recap",
        "",
        "## Resume Here",
        f"- **Status**: {status}",
        f"- **Outcome**: {outcome}",
        f"- **Immediate next action**: {immediate}",
        "- **Do not**: Read unbounded raw transcript content into the main context; use `/recap full` when complete history is required.",
        f"- **Handoff confidence**: {'high' if outcome_items else 'low'}",
        "",
        "## Completed",
    ]
    completed = []
    for session in sessions:
        completed.extend(_handoff_items(session, "outcomes", "what_was_done", limit=5))
    completed = list(dict.fromkeys(completed))[:10]
    if completed:
        lines.extend(f"- {item}" for item in completed)
    else:
        lines.append("- No verified completed work was extracted.")

    lines.extend(["", "## Remaining Work", "### Urgent"])
    urgent = _handoff_items(latest, "current_tasks", limit=5)
    if urgent:
        lines.extend(f"- {item}" for item in urgent)
    else:
        lines.append("- None recorded.")
    lines.extend(["### Blocked"])
    if blocked:
        lines.extend(f"- {item}" for item in blocked)
    else:
        lines.append("- None recorded.")
    lines.extend(["### Optional"])
    optional = next_items[1:]
    if optional:
        lines.extend(f"- {item}" for item in optional)
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Risks and Constraints"])
    if risks:
        lines.extend(f"- {item}" for item in risks)
    else:
        lines.append("- None material recorded.")
    lines.extend(["", "## Decisions"])
    if decisions:
        lines.extend(f"- {item}" for item in decisions)
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Artifacts"])
    if artifacts:
        lines.extend(f"- `{path}`" for path in artifacts)
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Evidence Appendix", f"- **Terminal**: {terminal_id}", f"- **Sessions**: {len(sessions)}"])
    if sessions:
        lines.append("### Detailed Session Evidence")
        for index, session in enumerate(sessions, 1):
            lines.append(f"#### Session {index}: {session.get('session_id', 'unknown')[:16]}")
            lines.append(f"- Entries: {session.get('entry_count', 0)}")
            if session.get("goal") or session.get("last_goal"):
                lines.append(f"- Goal: {session.get('goal') or session.get('last_goal')}")
            transcript = str(session.get("transcript", "") or "")
            if transcript:
                preview = transcript[:4000]
                suffix = "\n[Evidence preview truncated; use /recap full for complete raw context.]" if len(transcript) > len(preview) else ""
                lines.extend(["", "```text", preview + suffix, "```"])
    else:
        lines.append("- No session history found.")

    lines.extend(["", "## Next Session Checklist"])
    checklist = next_items or ([immediate] if immediate != "none — session is closed" else [])
    if checklist:
        lines.extend(f"- [ ] {item}" for item in checklist)
    else:
        lines.append("- [ ] No pending action recorded.")
    return "\n".join(lines)


def format_recap(
    sessions: list[dict[str, Any]],
    terminal_id: str,
    brief: bool = False,
) -> str:
    """Format session data into a terminal recap (aligned with /handoff template).

    Args:
        sessions: List of session summaries
        terminal_id: Terminal identifier
        brief: If True, show brief catch-up format only

    Returns:
        Formatted recap string
    """
    if brief:
        return format_brief(sessions)

    lines = []
    lines.append(f"# Terminal Recap: {terminal_id}")
    lines.append("")

    # Session Metadata
    lines.append("## Session Metadata")
    lines.append("")
    lines.append(f"- **Total Sessions**: {len(sessions)}")
    lines.append(f"- **Terminal ID**: {terminal_id}")
    if sessions:
        current_session = sessions[-1]['session_id'] if sessions else "unknown"
        lines.append(f"- **Current Session**: {current_session[:16]}...")
        # Try to get project path
        try:
            project_root = get_project_root()
            if project_root:
                lines.append(f"- **Project**: {project_root}")
        except Exception:
            pass
    lines.append("")

    # Session history from transcript
    if sessions:
        lines.append("## Session History")
        lines.append("")

        for i, session in enumerate(sessions, 1):
            lines.append(f"**[Session {i}]** {session['session_id'][:12]}...")
            lines.append(f"- **Entries**: {session['entry_count']}")
            lines.append(f"- **User messages**: {session['user_message_count']}")
            lines.append(f"- **Assistant messages**: {session['assistant_message_count']}")

            # Duration if available (from session timestamp calculation)
            if session.get("duration"):
                lines.append(f"- **Duration**: {session['duration']}")

            # Token usage if available
            token_usage = session.get("token_usage", {})
            if token_usage.get("total_tokens", 0) > 0:
                total_k = token_usage["total_tokens"] // 1000
                lines.append(f"- **Tokens**: ~{total_k}K ({token_usage['input_tokens']//1000}K in, {token_usage['output_tokens']//1000}K out)")

            # Priority score (session importance)
            priority = session.get("priority_score", 0)
            if priority > 0:
                lines.append(f"- **Priority Score**: {priority:.1f}/100")

            if session.get("last_goal"):
                lines.append(f"- **Goal**: {session['last_goal']}")
            lines.append("")

            # Modified Files (from Edit/Write tool_use blocks)
            modified = session.get("modified_files", [])
            if modified:
                lines.append("### Modified Files")
                for path in modified[:10]:
                    lines.append(f"- `{path}`")
                lines.append("")

            # Original Request / Trigger (extracted from early session content)
            if session.get("original_request"):
                lines.append("### Original Request")
                lines.append(f"- **User Request**: \"{session['original_request']}\"")
                if session.get("trigger"):
                    lines.append(f"- **Trigger**: {session['trigger']}")
                lines.append("")

            # Session Objectives
            if session.get("objectives"):
                lines.append("### Session Objectives")
                for obj in session.get("objectives", [])[:5]:
                    status = obj.get("status", "unknown")
                    description = obj.get("description", "")
                    lines.append(f"- **{description}** ({status})")
                lines.append("")

            # Final Actions Taken
            if session.get("actions"):
                lines.append("### Final Actions Taken")
                for action in session.get("actions", [])[:5]:
                    if isinstance(action, str):
                        priority = "medium"
                        description = action
                    else:
                        priority = action.get("priority", "medium") if isinstance(action, dict) else "medium"
                        description = action.get("description", "") if isinstance(action, dict) else str(action)
                    lines.append(f"- **{description}** ({priority})")
                lines.append("")

            # Outcomes
            if session.get("outcomes"):
                lines.append("### Outcomes")
                for outcome in session["outcomes"][:5]:
                    if isinstance(outcome, str):
                        lines.append(f"- **{outcome}** (success)")
                    else:
                        status = outcome.get("status", "success")
                        description = outcome.get("description", outcome.get("text", ""))
                        lines.append(f"- **{description}** ({status})")
                lines.append("")

            # Handoff-quality: What Was Done
            if session.get("what_was_done"):
                lines.append("### What Was Done")
                for item in session["what_was_done"][:5]:
                    lines.append(f"- {item}")
                lines.append("")

            # Handoff-quality: Decisions Made
            if session.get("decisions_made"):
                lines.append("### Decisions Made")
                for decision in session["decisions_made"][:5]:
                    lines.append(f"- {decision}")
                lines.append("")

            # Handoff-quality: Current State
            current_state = session.get("current_state", {})
            if current_state.get("modified") or current_state.get("working") or current_state.get("blocked"):
                lines.append("### Current State")
                if current_state.get("modified"):
                    lines.append("**Modified:**")
                    for item in current_state["modified"][:5]:
                        lines.append(f"- {item}")
                if current_state.get("working"):
                    lines.append("**Working:**")
                    for item in current_state["working"][:5]:
                        lines.append(f"- {item}")
                if current_state.get("blocked"):
                    lines.append("**Blocked:**")
                    for item in current_state["blocked"][:5]:
                        lines.append(f"- {item}")
                lines.append("")

            # Active Work At Handoff
            if session.get("active_work"):
                lines.append("### Active Work At Handoff")
                work = session["active_work"]
                lines.append(f"- **Currently Working On**: {work.get('description', 'Unknown')}")
                lines.append(f"  - Status: {work.get('status', 'unknown')}")
                if work.get("files_modified"):
                    lines.append(f"  - Files Modified: {work['files_modified']}")
                if work.get("next"):
                    lines.append(f"  - Next: {work['next']}")
                lines.append("")

            # Handoff-quality: Next Steps
            if session.get("next_steps"):
                lines.append("### Next Steps")
                for step in session["next_steps"][:5]:
                    lines.append(f"- {step}")
                lines.append("")

            # Working Decisions (Critical for Continuity)
            if session.get("decisions"):
                lines.append("### Working Decisions (Critical for Continuity)")
                for decision in session["decisions"][:5]:
                    if isinstance(decision, str):
                        lines.append(f"- **Decision**: {decision}")
                    else:
                        lines.append(f"- **Decision**: {decision.get('text', decision.get('description', ''))}")
                        if decision.get("rationale"):
                            lines.append(f"  - **Rationale**: {decision['rationale']}")
                        if decision.get("impact"):
                            lines.append(f"  - **Impact**: {decision['impact']}")
                lines.append("")

            # Current Tasks
            if session.get("current_tasks"):
                lines.append("### Current Tasks")
                for task in session["current_tasks"][:5]:
                    if isinstance(task, str):
                        lines.append(f"- **#?**: {task}")
                    else:
                        task_id = task.get("id", task.get("number", "?"))
                        description = task.get("description", "")
                        status = task.get("status", "pending")
                        priority = task.get("priority", "medium")
                        lines.append(f"- **#{task_id}**: {description} ({status}, {priority})")
                lines.append("")

            # Known Issues
            if session.get("known_issues"):
                lines.append("### Known Issues")
                for issue in session["known_issues"][:5]:
                    if isinstance(issue, str):
                        lines.append(f"- **ISSUE**: {issue}")
                    else:
                        issue_id = issue.get("id", "ISSUE")
                        description = issue.get("description", "")
                        status = issue.get("status", "open")
                        priority = issue.get("priority", "medium")
                        lines.append(f"- **{issue_id}**: {description} ({status}, {priority})")
                lines.append("")

            # Open Questions
            if session.get("open_questions"):
                lines.append("### Open Questions")
                for question in session["open_questions"][:5]:
                    if isinstance(question, str):
                        lines.append(f"- **Question**: {question}")
                    else:
                        q_text = question.get("text", question.get("question", ""))
                        priority = question.get("priority", "medium")
                        q_type = question.get("type", "technical")
                        lines.append(f"- **Question**: {q_text}? ({priority}, {q_type})")
                lines.append("")

            # Knowledge Contributions
            if session.get("knowledge_contributions"):
                lines.append("### Knowledge Contributions")
                for contribution in session["knowledge_contributions"][:5]:
                    lines.append(f"- **Insight**: {contribution}")
                lines.append("")

            # Next Immediate Action
            if session.get("next_actions"):
                lines.append("### Next Immediate Action")
                for idx, action in enumerate(session["next_actions"][:5], 1):
                    lines.append(f"{idx}. {action}")
                lines.append("")

            # Condensed transcript — raw context for LLM synthesis
            # This provides the full context for the LLM to reason over
            if session.get("transcript"):
                transcript_preview = session["transcript"]
                lines.append("### Raw Context")
                lines.append(transcript_preview)

            lines.append("")
    else:
        lines.append("## Session History")
        lines.append("")
        lines.append("No session history found in transcript.")
        lines.append("")

    # Add Quick Argument section if AIR gaps exist
    quick_arg = format_quick_argument_section()
    if quick_arg:
        lines.append(quick_arg)

    return "\n".join(lines)


def format_quick_argument_section() -> str:
    """Format AIR gap classifications into Quick Argument section.

    Returns:
        Formatted Quick Argument section, or empty string if no gaps.
    """
    gaps = load_air_gaps()
    if not gaps:
        return ""

    lines = []
    lines.append("")
    lines.append("## Quick Argument")

    for i, gap in enumerate(gaps[:5], 1):  # Limit to 5 most recent
        gap_type = gap.get("type", "unknown")
        directive = gap.get("directive", "none")
        action = gap.get("action", "unknown")
        evidence = gap.get("evidence", "")
        timestamp = gap.get("timestamp", "")

        # Determine rationale based on gap type
        if gap_type == "hallucinated":
            rationale = "Action claimed but no verifiable diff produced"
        elif gap_type == "silent_pivot":
            rationale = "Action taken without explicit user directive in window"
        elif gap_type == "unjustified_revert":
            rationale = "Revert lacks technical justification in commit message"
        else:
            rationale = "Gap classification complete"

        # Format type label
        if gap_type == "hallucinated":
            type_label = "Heuristic"
        elif gap_type == "silent_pivot":
            type_label = "Silent Pivot"
        elif gap_type == "unjustified_revert":
            type_label = "Directed"
        else:
            type_label = gap_type

        lines.append("")
        lines.append(f"### Gap {i}: {gap_type.replace('_', ' ').title()}")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Type** | {type_label} |")
        lines.append(
            f"| **Action** | {action[:100]} |"
            if len(action) > 100
            else f"| **Action** | {action} |"
        )
        lines.append(
            f"| **Evidence** | {evidence[:150]} |"
            if len(evidence) > 150
            else f"| **Evidence** | {evidence} |"
        )
        lines.append(f"| **Rationale** | {rationale} |")

    return "\n".join(lines)


# Constants for handoff-first resolution (TASK-002, R-020)
# 5 minutes: handoffs newer than this are preferred over transcript parsing
# This covers terminal restarts and short interruptions without losing context
FRESH_HANDOFF_THRESHOLD_SECONDS = 300

# Pre-mortem fix 3a: Extract shared file discovery helper
def _load_from_chain_result(
    chain_result,
    project_root: Path,
    seen_session_ids: set[str] | None = None,  # R-007: deduplication
) -> list[SessionSummary]:
    """Load sessions from chain result, filtering subagents.

    Args:
        chain_result: SessionChainResult from walk_session_chain
        project_root: Project root path for validation (R-004)
        seen_session_ids: Track seen sessions for deduplication (R-007)

    Returns:
        List of session summaries
    """
    if seen_session_ids is None:
        seen_session_ids = set()

    sessions = []
    for entry in chain_result.entries:
        transcript_path = entry.transcript_path

        # Filter subagent transcripts (TASK-003, R-012)
        if _is_subagent_transcript(transcript_path):
            logger.debug("Skipping subagent transcript: %s", transcript_path)
            continue

        # R-007: Deduplication by (session_id, transcript_path) tuple
        session_key = (entry.session_id, str(transcript_path))
        if session_key in seen_session_ids:
            logger.debug("Skipping duplicate session: %s", entry.session_id)
            continue
        seen_session_ids.add(session_key)

        # R-004: Validate transcript exists before loading (referential integrity)
        # R-005: TOCTOU fix - open file directly to avoid race between exists() and load
        if transcript_path:
            try:
                entries = load_transcript_entries(str(transcript_path))
                session_summaries = extract_sessions_from_transcript(entries)
                sessions.extend(session_summaries)
            except FileNotFoundError:
                logger.warning(
                    "Some session history could not be loaded. "
                    "The transcript file at %s was not found. "
                    "You may see fewer sessions than actually exist.",
                    transcript_path,
                )
            except (OSError, ValueError) as e:
                logger.warning("Failed to load transcript %s: %s", transcript_path, e)

    return sessions


def _load_from_direct_transcript(project_root: Path) -> list[SessionSummary]:
    """Load sessions from the current transcript file (final fallback).

    Args:
        project_root: Project root path

    Returns:
        List of session summaries
    """
    transcript_dir = _find_transcript_dir(project_root)
    if not transcript_dir:
        return []

    # Pre-mortem fix 3a: Use shared helper
    most_recent = _get_most_recent_transcript(transcript_dir)
    if not most_recent:
        return []

    entries = load_transcript_entries(str(most_recent))

    # CHANGE-003: Try parsing session summary block first (D5: Fallback Ordering)
    # Parse first 50 entries for ## Last Session Summary
    sample_entries = []
    for i, line in enumerate(entries[:200] if isinstance(entries, list) else entries):
        if i >= 50:
            break
        # entries are already dicts from load_transcript_entries, not JSONL strings
        if isinstance(line, dict):
            sample_entries.append(line)
        else:
            try:
                entry_data = json.loads(line)
                sample_entries.append(entry_data)
            except json.JSONDecodeError:
                continue

    # Build raw_text from sample_entries
    raw_text = ""
    for e in sample_entries:
        text = e.get("text", "") or e.get("content", "") if isinstance(e, dict) else str(e)
        raw_text += text + "\n"

    # Extract session summary block using regex
    summary_regex = re.compile(
        r"##\s*Last\s*Session\s*Summary\s*\n(?:.*?\n)*?(?=\n##|\Z)",
        re.DOTALL
    )
    summary_match = summary_regex.search(raw_text)

    fallback_sessions: list[SessionSummary] = []
    if summary_match:
        summary_text = summary_match.group(0)
        when_match = re.search(r"\*\*When:\*\*\s*(.+)", summary_text)
        dur_match = re.search(r"\*\*Duration:\*\*\s*~?(\d+)h\s*(\d+)m", summary_text)
        content_start = summary_text.find("**When:**")
        content_body = summary_text[content_start:] if content_start >= 0 else summary_text
        # Strip trailing blank lines before measuring content length (LOGIC-002)
        content_body_stripped = re.sub(r'\n\s*\n\s*$', '', content_body.strip())
        content_len = len(content_body_stripped)

        if when_match and dur_match and content_len > 50:
            hours = int(dur_match.group(1)) if dur_match.group(1) else 0
            mins = int(dur_match.group(2)) if dur_match.group(2) else 0
            duration_mins = hours * 60 + mins
            if duration_mins > 0 and not content_body_stripped.startswith("#"):
                # Valid summary — extract prior session data
                prior_when = when_match.group(1).strip()
                prior_goal = content_body_stripped[:200]
                session_summary: SessionSummary = {
                    "session_id": f"prior@{prior_when}",
                    "goal": f"[Prior session: {prior_when}, ~{hours}h {mins}m] {prior_goal}",
                    "current_task": "",
                    "active_files": [],
                    "created_at": prior_when,
                    "transcript_path": str(most_recent),
                }
                fallback_sessions.insert(0, session_summary)

    # Extract sessions from transcript entries
    sessions = extract_sessions_from_transcript(entries)
    # If we found a valid session summary, prepend it to the sessions list (D4: Dual-Content Precedence)
    if fallback_sessions:
        sessions = fallback_sessions + sessions
    return sessions


def _load_all_sessions_via_history_index(
    project_root: Path | None = None,
) -> list[SessionSummary]:
    """Load sessions using handoff-first resolution strategy.

    TASK-002: Resolution order:
    1. Fresh handoff (< 5 min) - primary resume context
    2. Handoff chain walk - session history
    3. Unified chain walk - missing link fallback
    4. Direct transcript - final fallback
    """
    if project_root is None:
        project_root = get_project_root()

    current_session_id = _get_current_session_id(project_root)
    if not current_session_id:
        return []

    # TASK-001, R-013: Import from core.session_chain (correct path)
    # Pre-mortem fix 1a: Changed from search_research to core.session_chain
    # Add search-research package to path if needed
    import sys
    from pathlib import Path
    _search_research_root = Path("P:\\\\\\packages/search-research")
    if str(_search_research_root) not in sys.path:
        sys.path.insert(0, str(_search_research_root))

    try:
        from core.session_chain import (
            SessionChainEntry,
            walk_session_chain,
        )
        # 1c: Verify API
        assert hasattr(walk_session_chain, '__call__'), "walk_session_chain not callable"
    except (ImportError, ValueError, OSError, AssertionError) as exc:
        logger.warning("Failed to import session_chain: %s", exc)
        return _load_from_direct_transcript(project_root)

    # Strategy 1: Check for fresh handoff (highest priority)
    # R-010: Wrap in try/except for fallback
    try:
        fresh_handoff = _get_fresh_handoff(current_session_id)
        if fresh_handoff:
            logger.info("Using fresh handoff for resume context: %s", fresh_handoff)
            return _load_from_handoff(fresh_handoff)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Fresh handoff load failed: %s", exc)
        # Fall through to Strategy 2

    # Strategy 2: Walk handoff chain
    try:
        handoff_result = walk_session_chain(current_session_id)
        # R-008, R-011: Check chain length and session_id presence
        if handoff_result.entries:
            # R-011: Validate current session_id is in chain
            session_ids_in_chain = {entry.session_id for entry in handoff_result.entries}
            if current_session_id not in session_ids_in_chain:
                logger.warning(
                    "Current session %s not found in recent handoff history. "
                    "Trying alternative method to load your sessions...",
                    current_session_id,
                )
            elif len(handoff_result.entries) > 0:  # R-008: Changed from >1 to >0
                sessions = _load_from_chain_result(handoff_result, project_root)
                # CHANGE-002: Three-case handling — ALL-invalid (subagent-only chain)
                # returns []. Fall through to next strategy instead of returning empty.
                if sessions:
                    return sessions
    except (ImportError, OSError) as exc:
        logger.warning("Handoff chain walk failed: %s", exc)

    # Strategy 3: Unified chain walk
    try:
        chain_result = walk_session_chain(session_id=current_session_id)
        if chain_result.entries:
            sessions = _load_from_chain_result(chain_result, project_root)
            # CHANGE-002: Three-case handling — ALL-invalid returns [],
            # MIXED returns valid-only, ALL-valid returns full chain.
            # If _load_from_chain_result filtered ALL entries (subagent-only),
            # fall through to next strategy instead of returning empty.
            if sessions:
                return sessions
    except (ValueError, OSError) as exc:
        logger.warning("Unified chain walk failed: %s", exc)

    # Strategy 4: Direct transcript fallback
    return _load_from_direct_transcript(project_root)


def _find_transcript_dir(project_root: Path | None) -> Path | None:
    """Find the directory containing transcript files for this project.

    Search order:
    1. Project-specific ~/.claude/projects/{project_hash}/ (priority)
    2. Legacy ~/.claude/projects/ (fallback, may contain stale cross-project files)

    Args:
        project_root: Root directory of the project to search transcripts for

    Returns:
        Path to transcript directory, or None if not found
    """
    if project_root:
        # Priority 1: project-specific directory ~/.claude/projects/{project_hash}/
        # This is where P:--specific session transcripts live (not the root ~/.claude/projects/)
        project_hash = _get_project_hash(project_root)
        project_transcripts = Path.home() / ".claude" / "projects" / project_hash
        if project_transcripts.exists():
            jsonl_files = list(project_transcripts.glob("*.jsonl"))
            if jsonl_files:
                return project_transcripts

    # Priority 2: home directory root ~/.claude/projects/ (legacy fallback)
    # NOTE: This contains cross-project blobs + agent files — can return stale
    # November 2025 files when actual project transcripts are in project subdir.
    # Only used as fallback when project_root is None or project subdir is empty.
    home_transcripts = Path.home() / ".claude" / "projects"
    if home_transcripts.exists():
        jsonl_files = list(home_transcripts.glob("*.jsonl"))
        if jsonl_files:
            return home_transcripts

    return None


def main() -> None:
    """Generate terminal-wide recap via direct transcript analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="Terminal-wide session catch-up")
    parser.add_argument(
        "command",
        nargs="?",
        default="recap",
        choices=["recap", "brief", "full"],
        help="Command: recap (handoff), brief (catch-up), or full (detailed history)",
    )
    args = parser.parse_args()

    terminal_id = resolve_terminal_key(None)
    project_root = get_project_root()

    # Primary: load sessions via handoff-chain (session-scoped, not all-terminals)
    sessions = _load_all_sessions_via_history_index(project_root)

    # Fallback: if no sessions found, try single-file approach (current terminal transcript only)
    if not sessions:
        transcript_path = find_transcript_file(terminal_id)
        if transcript_path and transcript_path.exists():
            entries = load_transcript_entries(str(transcript_path))
            sessions = extract_sessions_from_transcript(entries)

    # The default is a bounded resume handoff. The legacy detailed renderer is
    # retained behind `full` so no extracted session evidence is lost.
    is_brief = args.command == "brief"
    if is_brief:
        recap = format_recap(sessions, terminal_id, brief=True)
    elif args.command == "full":
        recap = format_recap(sessions, terminal_id)
    else:
        recap = format_handoff(sessions, terminal_id)
    print(recap)


if __name__ == "__main__":
    main()
