#!/usr/bin/env python3
"""GTO PreToolUse hook — optional gates during GTO runs.

Claude Code hook protocol: reads JSON from stdin, outputs JSON to stdout.

During GTO runs, this hook can:
- Warn if tool usage might conflict with artifact generation
- Block destructive operations during active analysis
"""
from __future__ import annotations

import json
import sys

from .common import is_gto_active, read_state, write_hook_output

# Tools that should be warned about during active GTO runs
WARN_TOOLS = {"Bash"}

# Token sequences that indicate destructive commands.
# Matched as ordered token subsequences to avoid false positives
# (e.g., "echo 'rm -rf'" in a string should not trigger).
BLOCK_PATTERNS: list[list[str]] = [
    ["rm", "-rf"],
    ["rm", "-r", "-f"],
    ["git", "reset", "--hard"],
    ["git", "checkout", "--"],
    ["git", "clean", "-f"],
]


def _matches_pattern(tokens: list[str], pattern: list[str]) -> bool:
    """Check if pattern tokens appear as an ordered subsequence in tokens."""
    if len(pattern) > len(tokens):
        return False
    for i in range(len(tokens) - len(pattern) + 1):
        if tokens[i:i + len(pattern)] == pattern:
            return True
    return False


def run(data: dict) -> dict | None:
    """In-process hook entry point."""
    session_id = data.get("session_id")
    if not is_gto_active(session_id):
        return None

    state = read_state(session_id)
    if state.get("phase") != "running":
        return None

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in WARN_TOOLS:
        return None

    # Check for destructive commands using tokenized matching
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        tokens = command.split()
        for pattern in BLOCK_PATTERNS:
            if _matches_pattern(tokens, pattern):
                return {
                    "decision": "block",
                    "reason": f"GTO: blocking destructive command during active run: '{' '.join(pattern)}'",
                }

    return None


def main() -> None:
    """CLI entry point."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        data = {}

    result = run(data)
    if result is not None:
        write_hook_output(result)
        if result.get("decision") == "block":
            sys.exit(2)
    else:
        write_hook_output({"decision": "allow"})
    sys.exit(0)


if __name__ == "__main__":
    main()
