#!/usr/bin/env python3
"""GTO-v2 PostToolUse hook — failure capture and file-change logging.

Artifact validation (JSON validity, RNS markers) is owned by hooks/stop.py.
This hook handles local logging only.

# Operating Contract (for LLM and hooks)
# - GTO/GTO_v2 orchestrators and artifacts define the canonical contract
#   for gap analysis and verification. This hook must not change JSON
#   shapes or state semantics unless explicitly requested.
# - When you modify hooks, keep them focused on: checking run state,
#   validating artifacts (verifyartifact, RNS markers), capturing
#   failures or hygiene signals via detectors.
#   Do NOT introduce new ad‑hoc formats or bypass the orchestrator.
# - Do not assume stripscaffoldingblocks, mode schemas, or other
#   hidden sanitization layers exist. If you need them, implement
#   them explicitly in a shared module instead of referencing them.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .common import gto_state_dir, write_hook_output


def run(data: dict) -> dict | None:
    """In-process hook entry point."""
    session_id = data.get("session_id")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_output = data.get("tool_output", "")

    # Capture failures during GTO-v2 runs
    if _is_failure(tool_output):
        _capture_failure(tool_name, tool_input, tool_output, session_id)

    # Record file changes for session-scoped tracking
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            _record_file_change(file_path, session_id)

    return None


def _is_failure(output: str) -> bool:
    """Check if tool output indicates a failure."""
    if not output:
        return False
    failure_signals = ["Error:", "error:", "FAILED", "Traceback", "Exception"]
    return any(s in output for s in failure_signals)


def _capture_failure(tool_name: str, tool_input: dict, output: str, session_id: str | None = None) -> None:
    """Append a failure capture entry to the GTO-v2 logs."""
    logs_dir = gto_state_dir(session_id).parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "failures.jsonl"

    entry = {
        "tool": tool_name,
        "input_summary": str(tool_input.get("command", tool_input.get("file_path", "")))[:200],
        "output_snippet": output[:500],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _record_file_change(file_path: str, session_id: str | None = None) -> None:
    """Append a file change record to the session changes log."""
    artifacts_dir = gto_state_dir(session_id).parent
    log_path = artifacts_dir / "session_changes.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": "file-edit",
        "file": file_path,
        "session_id": session_id or os.environ.get("CLAUDE_SESSION_ID", ""),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
    else:
        write_hook_output({"decision": "allow"})
    sys.exit(0)


if __name__ == "__main__":
    main()
