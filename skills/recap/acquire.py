"""Stage 1: evidence acquisition.

Responsibilities:
- resolve terminal identity, project root
- sessions-index lookup
- registry loading  (primary when sessions-index absent/stale)
- fresh handoff loading
- handoff-chain walking
- transcript fallback discovery
- subagent filtering
- deduplication

All functions here return raw source records. Parsing into SessionSpan
happens in parse.py.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Shared canonical terminal_id algorithm (byte-identical copy in package __lib).
_RECAP_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_RECAP_PKG_ROOT / "__lib") not in sys.path:
    sys.path.insert(0, str(_RECAP_PKG_ROOT / "__lib"))
from terminal_id import canonical_terminal_id  # noqa: E402

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────────

FRESH_HANDOFF_THRESHOLD_SECONDS = 300
_TRANSCRIPT_SCAN_LINES = 200
_WINDOWS_SHORT_PATH_PREFIX = "cts\\"


# ── Identity cache (authoritative, written by SessionStart hook) ─────────────────


def _read_identity_json() -> dict | None:
    """Read authoritative session identity from SessionStart hook's cache.

    Uses WT_SESSION env var to find identity.json under:
    P:\\\\\\.claude/.artifacts/console_{WT_SESSION}/identity.json

    This is the primary source for session_id and transcript_path.
    It is written fresh at session start and is immune to compaction chain rewrites.

    Returns None if not available (SessionStart hook may not have fired).
    """
    wt = os.environ.get("WT_SESSION")
    if not wt:
        return None
    identity_path = Path("P:\\\\\\.claude/.artifacts") / f"console_{wt}" / "identity.json"
    if not identity_path.exists():
        return None
    try:
        data = json.loads(identity_path.read_text(encoding="utf-8"))
        return {
            "terminal_id": data.get("terminal", {}).get("id", ""),
            "session_id": data.get("claude", {}).get("session_id"),
            "transcript_path": data.get("claude", {}).get("transcript_path"),
            "cwd": data.get("claude", {}).get("cwd"),
            "captured_at": data.get("captured_at"),
        }
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


# ── Terminal / project resolution ─────────────────────────────────────────────


def resolve_terminal_key(terminal_id: str | None = None) -> str:
    """Resolve terminal ID from parameter or the shared canonical algorithm.

    Priority:
    1. Explicit terminal_id parameter (caller-supplied override)
    2. canonical_terminal_id() — CLAUDE_TERMINAL_ID, WT_SESSION, ..., sha1(ppid).
       Never returns "" (derived fallback guarantees a stable unique console_<id>).
    """
    if terminal_id:
        return terminal_id
    return canonical_terminal_id()


def get_project_root(cwd: Path | None = None) -> Path:
    """Detect project root from current working directory."""
    if cwd is None:
        cwd = Path.cwd()
    if (cwd / ".claude").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".claude").exists():
            return parent
    return cwd


def _get_project_hash(project_path: Path) -> str:
    """Derive the Claude Code project hash for a project path."""
    path_str = str(project_path.resolve())
    path_str = path_str.replace("/", "-").replace("\\", "-").replace(":", "-")
    return path_str


# ── Subagent filtering ─────────────────────────────────────────────────────────


def _is_subagent_transcript(path: Path) -> bool:
    """Check if a transcript path belongs to a subagent.

    Uses exact component-level matching, not substring matching.
    """
    if not path.parts:
        return False
    for part in path.parts:
        if part == "subagents":
            return True
    if path.name.startswith("agent-"):
        return True
    return False


# ── Transcript scanning ─────────────────────────────────────────────────────────


def _is_transcript_file(path: Path) -> bool:
    """Check if a .jsonl file is a real transcript (has user/assistant entries)."""
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _TRANSCRIPT_SCAN_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    t = entry.get("type", "")
                    if t in ("user", "assistant"):
                        return True
                except json.JSONDecodeError:
                    continue
        return False
    except OSError:
        return False


def _scan_transcript_dir(transcript_dir: Path) -> list[tuple[float, Path]]:
    """Scan a directory for .jsonl files with real transcript content."""
    candidates: list[tuple[float, Path]] = []
    for jsonl_file in transcript_dir.glob("*.jsonl"):
        try:
            mtime = jsonl_file.stat().st_mtime
            if _is_transcript_file(jsonl_file):
                candidates.append((mtime, jsonl_file))
        except OSError:
            continue
    return candidates


def _find_project_transcript_dir(project_root: Path | None) -> Path | None:
    """Find the directory containing transcript files for this project."""
    if project_root is None:
        project_root = get_project_root()

    project_hash = _get_project_hash(project_root)
    project_transcripts = Path.home() / ".claude" / "projects" / project_hash
    if project_transcripts.exists() and list(project_transcripts.glob("*.jsonl")):
        return project_transcripts

    home_transcripts = Path.home() / ".claude" / "projects"
    if home_transcripts.exists():
        jsonl_files = list(home_transcripts.glob("*.jsonl"))
        if jsonl_files:
            return home_transcripts
    return None


def _get_most_recent_transcript(transcript_dir: Path) -> Path | None:
    """Get the most recent transcript file from a directory."""
    candidates = _scan_transcript_dir(transcript_dir)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_transcript_file(terminal_id: str) -> Path | None:
    """Find the transcript file for this terminal."""
    cwd = Path.cwd()
    candidates = [
        cwd / ".claude" / "transcripts" / f"{terminal_id}.jsonl",
        Path.home() / ".claude" / "transcripts" / f"{terminal_id}.jsonl",
        cwd / f"{terminal_id}.jsonl",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Fallback: scan project transcript directory
    transcript_dir = _find_project_transcript_dir(cwd)
    if transcript_dir:
        return _get_most_recent_transcript(transcript_dir)
    return None


# ── Sessions index ───────────────────────────────────────────────────────────────


def _get_sessions_index_path(project_path: Path) -> Path | None:
    """Find the sessions-index.json for a given project."""
    project_hash = _get_project_hash(project_path)
    index_path = Path.home() / ".claude" / "projects" / project_hash / "sessions-index.json"
    if index_path.exists():
        return index_path
    return None


def load_sessions_index(index_path: Path) -> list[dict[str, Any]]:
    """Load and parse a sessions-index.json file."""
    try:
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load sessions index %s: %s", index_path, exc)
        return []

    raw_entries: list[dict[str, Any]]
    if isinstance(data, dict) and "entries" not in data:
        raw_entries = []
        for session_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            created_val = entry.get("createdAt", "")
            if isinstance(created_val, (int, float)):
                created_str = datetime.fromtimestamp(
                    created_val / 1000, tz=timezone.utc
                ).isoformat()
            else:
                created_str = str(created_val)
            goal = entry.get("summary") or entry.get("lastPrompt") or ""
            if isinstance(goal, str):
                goal = goal.strip()
            raw_entries.append({
                "sessionId": session_id,
                "created": created_str,
                "transcript_path": entry.get("fullPath", ""),
                "last_goal": goal[:200],
                "summary": goal,
            })
    else:
        raw_entries = data.get("entries", [])

    raw_entries.sort(key=lambda e: e.get("created", ""))
    return raw_entries


# ── Registry (primary fallback) ───────────────────────────────────────────────────


def _load_sessions_from_registry(
    terminal_id: str,
    limit: int | None = None,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load session entries from snapshot's session_registry.jsonl via query_registry.

    When session_id is provided, queries by session_id for cross-terminal chain
    discovery. Falls back to terminal_id when session_id is absent.
    """
    try:
        snapshot_root = Path("P:\\\\\\packages/snapshot")
        lib_path = snapshot_root / "scripts" / "hooks" / "__lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))
        from session_registry import query_registry
        if session_id:
            entries = query_registry(session_id=session_id, limit=limit or 10_000)
        else:
            entries = query_registry(terminal_id=terminal_id, limit=limit)
    except Exception as exc:
        logger.warning("Failed to load from session_registry: %s", exc)
        return []

    if limit is None:
        limit = 30

    result: list[dict[str, Any]] = []
    for entry in entries:
        transcript_path = entry.get("transcript_path", "")
        session_id = entry.get("session_id", "")
        goal = (entry.get("goal") or "")[:200]
        ts = entry.get("ts", "")
        if not session_id:
            continue
        result.append({
            "sessionId": session_id,
            "created": ts,
            "transcript_path": transcript_path,
            "last_goal": goal,
            "summary": goal,
        })
    result.sort(key=lambda e: e.get("created", ""))
    return result


# ── Handoff loading ──────────────────────────────────────────────────────────────


def _validate_handoff_identity(
    handoff_path: Path,
    expected_session_id: str,
    expected_terminal_id: str | None,
) -> bool:
    """Validate handoff file belongs to this session and terminal."""
    if expected_terminal_id:
        hf_stem = handoff_path.stem
        parts = hf_stem.split("_")
        if len(parts) >= 3:
            hf_terminal_id = parts[1]
            if hf_terminal_id != expected_terminal_id:
                return False
    try:
        with open(handoff_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    handoff_session_id = data.get("resume_snapshot", {}).get("session_id")
    if handoff_session_id and handoff_session_id != expected_session_id:
        return False
    return True


def _get_fresh_handoff(
    session_id: str,
    terminal_id: str | None = None,
) -> Path | None:
    """Check for a fresh handoff file (< 5 minutes old)."""
    if terminal_id is None:
        terminal_id = os.environ.get("CLAUDE_TERMINAL_ID")

    handoff_dirs = [
        Path("P:\\\\\\") / ".claude" / "state" / "handoff",
        Path.home() / ".claude" / "state" / "handoff",
    ]
    for handoff_dir in handoff_dirs:
        if not handoff_dir.exists():
            continue
        for hf in handoff_dir.glob("console_*_handoff.json"):
            if not _validate_handoff_identity(hf, session_id, terminal_id):
                continue
            try:
                with open(hf, encoding="utf-8") as f:
                    data = json.load(f)
                created_str = data.get("resume_snapshot", {}).get("created_at", "")
                if not created_str:
                    continue
                if created_str.endswith("Z"):
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                elif "+" in created_str or "-" in created_str[-6:]:
                    created = datetime.fromisoformat(created_str)
                else:
                    created = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - created).total_seconds()
                if age < FRESH_HANDOFF_THRESHOLD_SECONDS:
                    return hf
            except (OSError, json.JSONDecodeError, ValueError):
                continue
    return None


def _load_from_handoff(handoff_path: Path) -> dict[str, Any]:
    """Load session summary from a handoff file."""
    with open(handoff_path, encoding="utf-8") as f:
        data = json.load(f)
    resume_snapshot = data.get("resume_snapshot", {})
    return {
        "session_id": resume_snapshot.get("session_id", ""),
        "goal": resume_snapshot.get("goal", ""),
        "current_task": resume_snapshot.get("current_task", ""),
        "active_files": resume_snapshot.get("active_files", []),
        "created_at": resume_snapshot.get("created_at", ""),
        "transcript_path": resume_snapshot.get("transcript_path", ""),
    }


# ── Session chain (session_chain module) ──────────────────────────────────────


def _get_current_session_id(project_root: Path | None) -> str | None:
    """Find the current session ID from the most recent transcript file."""
    if project_root is None:
        project_root = get_project_root()
    transcript_dir = _find_project_transcript_dir(project_root)
    if not transcript_dir or not transcript_dir.exists():
        return None
    most_recent = _get_most_recent_transcript(transcript_dir)
    if not most_recent:
        return None
    try:
        with open(most_recent, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    sid = entry.get("sessionId")
                    if sid:
                        return str(sid)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return None


def _walk_session_chain(
    session_id: str,
) -> list[dict[str, Any]]:
    """Walk session chain and return entries as dicts."""
    try:
        search_research_root = Path("P:\\\\\\packages/search-research")
        if str(search_research_root) not in sys.path:
            sys.path.insert(0, str(search_research_root))
        from core.session_chain import walk_session_chain
        chain_result = walk_session_chain(session_id)
        if chain_result.entries:
            return [
                {
                    "session_id": e.session_id,
                    "transcript_path": str(e.transcript_path),
                    "parent_transcript_path": str(e.parent_transcript_path) if e.parent_transcript_path else "",
                    "created": e.created.isoformat() if e.created else "",
                }
                for e in chain_result.entries
            ]
    except Exception as exc:
        logger.warning("Session chain walk failed: %s", exc)
    return []


# ── Evidence discovery ─────────────────────────────────────────────────────────


@dataclass
class EvidenceSources:
    """Container for all discovered evidence sources."""
    mode: str = "empty"
    paths_scanned: list[str] = field(default_factory=list)
    current_transcript: str = ""
    handoff_path: str = ""
    registry_entries: list[dict[str, Any]] = field(default_factory=list)
    chain_entries: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)


def discover_evidence(
    project_root: Path | None = None,
    terminal_id: str = "",
    session_id: str = "",
) -> EvidenceSources:
    """Discover all evidence sources for the current terminal/project.

    Discovery order:
    1. session_registry.jsonl (primary when sessions-index absent/stale)
    2. fresh handoff (< 5 min)
    3. session chain walk
    4. direct transcript fallback

    Returns an EvidenceSources container — never raises.
    """
    if project_root is None:
        project_root = get_project_root()
    if not terminal_id:
        terminal_id = resolve_terminal_key(None)

    result = EvidenceSources()

    # Strategy -1: identity.json (authoritative, written fresh at session start)
    identity = _read_identity_json()
    if identity:
        sid = identity.get("session_id")
        tp = identity.get("transcript_path")
        if sid:
            session_id = sid
        if tp:
            result.current_transcript = tp
            result.paths_scanned.append(tp)

    if not session_id:
        session_id = _get_current_session_id(project_root) or ""

    # Strategy 0: registry (primary when sessions-index is stale)
    if terminal_id:
        registry_entries = _load_sessions_from_registry(terminal_id, limit=30, session_id=session_id)
        if registry_entries:
            result.mode = "registry"
            result.registry_entries = registry_entries
            result.paths_scanned.append(f"registry://{terminal_id}")
            return result

    # Strategy 1: fresh handoff
    if session_id:
        hf = _get_fresh_handoff(session_id, terminal_id)
        if hf:
            result.mode = "handoff"
            result.handoff_path = str(hf)
            result.paths_scanned.append(str(hf))
            return result

    # Strategy 2: session chain walk
    if session_id:
        chain_entries = _walk_session_chain(session_id)
        if chain_entries:
            # Filter out subagent transcripts
            filtered = [
                e for e in chain_entries
                if not _is_subagent_transcript(Path(e.get("transcript_path", "")))
            ]
            if filtered:
                result.mode = "chain"
                result.chain_entries = filtered
                result.paths_scanned.extend(e["transcript_path"] for e in filtered)
                return result

    # Strategy 3: direct transcript fallback
    tp = find_transcript_file(terminal_id)
    if tp and _is_transcript_file(tp):
        result.mode = "direct_transcript"
        result.current_transcript = str(tp)
        result.paths_scanned.append(str(tp))
        result.degraded = True
        result.degradation_reasons.append(
            "No registry or handoff found — using direct transcript only"
        )
        return result

    result.mode = "empty"
    result.degraded = True
    result.degradation_reasons.append("No evidence sources available")
    return result
