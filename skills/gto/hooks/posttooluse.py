#!/usr/bin/env python3
"""GTO PostToolUse hook — failure capture and format validation.

Claude Code hook protocol: reads JSON from stdin, outputs JSON to stdout.

During GTO runs, captures tool failures as findings and validates
artifact format after Write operations to the artifacts directory.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .common import is_gto_active, read_state, gto_state_dir, write_hook_output


def run(data: dict) -> dict | None:
    """In-process hook entry point."""
    session_id = data.get("session_id")
    if not is_gto_active(session_id):
        return None

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_output = data.get("tool_output", "")

    # Capture failures during GTO runs
    if _is_failure(tool_output):
        _capture_failure(tool_name, tool_input, tool_output, session_id)

    # Record file changes for session-scoped tracking
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            _record_file_change(file_path, session_id)

    # Validate artifact writes
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        artifacts_dir = gto_state_dir(session_id).parent
        if artifacts_dir in Path(file_path).resolve().parents or str(artifacts_dir) in file_path:
            validation = _validate_artifact_write(file_path)
            if validation:
                return validation

    return None


def _is_failure(output: str) -> bool:
    """Check if tool output indicates a failure."""
    if not output:
        return False
    failure_signals = ["Error:", "error:", "FAILED", "Traceback", "Exception"]
    return any(s in output for s in failure_signals)


def _capture_failure(tool_name: str, tool_input: dict, output: str, session_id: str | None = None) -> None:
    """Append a failure capture entry to the GTO logs."""
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


def _validate_artifact_write(file_path: str) -> dict | None:
    """Validate that a written artifact file is valid JSON."""
    path = Path(file_path)
    if not path.exists():
        return None
    if path.suffix != ".json":
        return None

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "decision": "warn",
            "reason": f"GTO: artifact file has invalid JSON: {exc}",
        }

    # Check machine_output format if present
    machine = data.get("machine_output", [])
    if isinstance(machine, list) and len(machine) > 0:
        has_d = any(isinstance(l, str) and l.startswith("RNS|D|") for l in machine)
        has_z = any(isinstance(l, str) and l.startswith("RNS|Z|") for l in machine)
        if not has_d or not has_z:
            return {
                "decision": "warn",
                "reason": "GTO: artifact machine_output missing RNS|D| or RNS|Z| markers",
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
    else:
        write_hook_output({"decision": "allow"})
    sys.exit(0)


if __name__ == "__main__":
    main()
