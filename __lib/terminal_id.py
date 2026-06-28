"""Canonical terminal_id for multi-terminal isolation.

Single authoritative algorithm. Identical copies must live in every package
that needs a terminal_id (cross-package sharing without coupling plugins).
The invariant test ``tests/test_terminal_id_invariants.py`` globs the monorepo
for every file defining ``canonical_terminal_id`` and fails if their source
hashes diverge — so drift is caught at CI, and the failure lists every copy.

KNOWN COPIES (update all in one commit, or the invariant test fails):
  - search-research/core/terminal_id.py                 (CANONICAL)
  - cc-skills-analysis/__lib/terminal_id.py

Algorithm priority:
    1. CLAUDE_TERMINAL_ID env var (explicit override)
    2. Per-terminal session env vars:
       WT_SESSION (Windows Terminal), ITERM_SESSION_ID (iTerm2),
       WEZTERM_SESSION_ID (WezTerm), TMUX (tmux)
    3. ConEmuServerPID (Windows ConEmu)
    4. Derived fallback: sha1(os.getppid()) — unique per Claude Code process
       (= per terminal) and stable across hook invocations within the session.

INVARIANT: this function NEVER returns a static/constant id. Every terminal,
window, or app instance gets a unique id. The fallback is derived, not default.
"""

from __future__ import annotations

import hashlib
import os

# Per-terminal session env vars, checked in priority order. Each is a UUID (or
# unique token) set by the terminal emulator and scoped to one terminal window.
_SESSION_ENV_VARS: tuple[str, ...] = (
    "WT_SESSION",        # Windows Terminal
    "ITERM_SESSION_ID",  # iTerm2
    "WEZTERM_SESSION_ID",  # WezTerm
    "TMUX",              # tmux (format: <socket>,<pid>,<session_id>)
)


def canonical_terminal_id() -> str:
    """Return the canonical terminal identifier for this process.

    Never returns a static constant. The fallback is a hash of the parent PID,
    which is unique per terminal session and stable for its lifetime.

    Returns:
        Identifier prefixed with ``console_`` for artifact-path compatibility.
        Example: ``console_081c35fc-2c20-42d8-90ee-fc271a305b8c``
    """
    # Priority 1: explicit env override (also used for testing)
    if env_id := os.environ.get("CLAUDE_TERMINAL_ID", "").strip():
        return env_id if env_id.startswith("console_") else f"console_{env_id}"

    # Priority 2: per-terminal session env var (each unique to one terminal)
    for var in _SESSION_ENV_VARS:
        if value := os.environ.get(var, "").strip():
            return f"console_{value}"

    # Priority 3: ConEmu (Windows) — unique per console window
    if conemu_pid := os.environ.get("ConEmuServerPID", "").strip():
        return f"console_conemu_{conemu_pid}"

    # Priority 4: derived fallback — NEVER static.
    # os.getppid() is the parent process (Claude Code itself for hooks), stable
    # across every invocation in one session and unique per terminal window.
    return f"console_{hashlib.sha1(str(os.getppid()).encode()).hexdigest()[:16]}"
