"""Shared utilities for GTO hooks.

Scope guard: determines if GTO is active by checking for state artifacts,
NOT marker files. A state file in the terminal-scoped artifacts directory
means GTO is running.

Terminal ID resolution matches the canonical pattern from /id skill:
1. CLAUDE_TERMINAL_ID env var (highest priority)
2. WT_SESSION (Windows Terminal session UUID, normalized with console_ prefix)
3. PID+timestamp hash fallback
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_terminal_id() -> str:
    """Get the current terminal ID using canonical resolution.

    Priority matches /id skill and recap skill:
    1. CLAUDE_TERMINAL_ID (set by SessionStart hook)
    2. WT_SESSION (Windows Terminal UUID, normalized to console_ prefix)
    3. PID+timestamp hash fallback
    """
    # Priority 1: explicit env override
    value = os.environ.get("CLAUDE_TERMINAL_ID", "").strip()
    if value:
        return value

    # Priority 2: Windows Terminal session UUID
    wt_session = os.environ.get("WT_SESSION", "").strip()
    if wt_session:
        return f"console_{wt_session}"

    # Priority 3: PID+timestamp hash (stable within session)
    pid = os.getpid()
    ts = int(datetime.now(timezone.utc).timestamp())
    unique = f"{pid}_{ts}".encode()
    return hashlib.sha1(unique).hexdigest()[:12]


def get_project_root() -> Path:
    """Get the project root directory.

    Priority:
    1. CLAUDE_PROJECT_DIR env var (set by Claude Code)
    2. Walk up from cwd to find .git
    """
    # Priority 1: Claude Code sets this
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if project_dir:
        return Path(project_dir)

    # Priority 2: walk up from cwd to find .git
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists():
            return parent
    return cwd


def get_artifacts_root() -> Path:
    """Get the root for terminal-scoped GTO artifacts.

    Priority:
    1. CLAUDE_ARTIFACTS_ROOT env var (for testing)
    2. Drive-root .claude directory (e.g. P:\\\\\\.claude/.artifacts/)

    Uses drive-root rather than project-scoped so artifacts survive
    across projects within the same terminal session.
    """
    override = os.environ.get("CLAUDE_ARTIFACTS_ROOT", "").strip()
    if override:
        return Path(override)
    drive_root = Path(get_project_root().anchor)
    return drive_root / ".claude" / ".artifacts"


def get_verified_identity(session_id: str | None = None) -> dict | None:
    """Read and verify the global identity cache for the current terminal.

    This implements a 'Handshake' pattern: we only trust the cached identity
    if it matches our live session_id. This prevents using stale data from
    a previous session in the same terminal.
    """
    # 1. Start with the fastest heuristic-based ID (WT_SESSION)
    terminal_id = get_terminal_id()
    if not terminal_id:
        return None

    # 2. Locate the identity.json file
    safe_tid = terminal_id.replace("/", "-").replace("\\", "-").replace(":", "-")
    identity_file = get_artifacts_root() / safe_tid / "identity.json"

    if not identity_file.exists():
        return None

    # 3. THE HANDSHAKE: Verify against live session_id
    try:
        identity = json.loads(identity_file.read_text(encoding="utf-8"))
        if session_id:
            cached_sid = identity.get("claude", {}).get("session_id")
            if cached_sid and cached_sid != session_id:
                # Stale data: identity file belongs to a DIFFERENT session
                return None
        return identity
    except (json.JSONDecodeError, OSError):
        return None


def gto_state_dir(session_id: str | None = None) -> Path:
    """Get the GTO state directory for the current terminal."""
    # Opportunistic Handshake: use identity.json if verified
    identity = get_verified_identity(session_id)
    if identity:
        terminal_id = identity.get("terminal", {}).get("id")
    else:
        terminal_id = get_terminal_id()

    return get_artifacts_root() / terminal_id / "gto" / "state"


def is_gto_active(session_id: str | None = None) -> bool:
    """Check if GTO is currently active in this terminal.

    GTO is active if a state file exists in the terminal-scoped artifacts dir.
    """
    state_dir = gto_state_dir(session_id)
    state_file = state_dir / "run_state.json"
    return state_file.exists()


def read_state(session_id: str | None = None) -> dict:
    """Read the current GTO run state. Returns empty dict if not active."""
    state_file = gto_state_dir(session_id) / "run_state.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state: dict) -> None:
    """Write GTO run state."""
    state_dir = gto_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "run_state.json"
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def read_hook_input() -> dict:
    """Read hook input from stdin (Claude Code hook protocol)."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_hook_output(data: dict) -> None:
    """Write hook output to stdout (Claude Code hook protocol)."""
    json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()
