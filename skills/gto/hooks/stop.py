#!/usr/bin/env python3
"""GTO Stop hook — state-driven completion verification.

Claude Code hook protocol: reads JSON from stdin, outputs JSON to stdout.

This hook runs on session stop and verifies GTO run completion by checking
artifacts against expected state. It does NOT parse prose output.

Verification checks:
1. State file exists and phase == "completed"
2. Artifact file exists and is valid JSON with required fields
3. Artifact machine_output has RNS format markers
4. All expected_artifacts are present
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import (
    is_gto_active,
    read_state,
    gto_state_dir,
    write_hook_output,
)


def run(data: dict) -> dict | None:
    """In-process hook entry point."""
    session_id = data.get("session_id")
    if not is_gto_active(session_id):
        return None

    state = read_state(session_id)
    if not state:
        return None

    verification_required = state.get("verification_required", False)
    if not verification_required:
        return None

    errors = _verify_completion(state)

    if errors:
        return {
            "decision": "block",
            "reason": f"GTO verification failed: {'; '.join(errors)}",
            "additionalContext": "\n\n💡 Problems with GTO state? Run /doctor to check identity and cache health."
        }

    return None


def _verify_completion(state: dict) -> list[str]:
    """Run verification checks against state and artifacts. Returns errors."""
    errors: list[str] = []

    # Check phase
    if state.get("phase") != "completed":
        errors.append(f"phase is '{state.get('phase')}', expected 'completed'")

    # Check artifact exists
    artifact_path = state.get("last_artifact")
    if not artifact_path:
        errors.append("no artifact path in state")
        return errors

    path = Path(artifact_path)
    if not path.exists():
        errors.append(f"artifact file missing: {artifact_path}")
        return errors

    # Validate artifact content
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"artifact not valid JSON: {exc}")
        return errors

    # Required fields
    for field in ("terminal_id", "session_id", "findings", "machine_output"):
        if field not in artifact:
            errors.append(f"artifact missing field: {field}")

    # Machine output format
    machine = artifact.get("machine_output", [])
    if isinstance(machine, list):
        if not any(isinstance(l, str) and l.startswith("RNS|D|") for l in machine):
            errors.append("machine_output missing RNS|D| header")
        if not any(isinstance(l, str) and l.startswith("RNS|Z|") for l in machine):
            errors.append("machine_output missing RNS|Z| terminator")

    # Expected artifacts
    for expected in state.get("expected_artifacts", []):
        exp_path = Path(expected)
        if not exp_path.exists():
            # Check relative to artifacts dir
            artifacts_dir = gto_state_dir().parent
            if not (artifacts_dir / expected).exists():
                errors.append(f"expected artifact missing: {expected}")

    return errors


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
