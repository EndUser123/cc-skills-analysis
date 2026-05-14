#!/usr/bin/env python3
"""GTO-v2 Stop hook — mechanical artifact verification only.

This hook performs ONLY mechanical checks. The skill-guard execution runtime
evaluates the contract (phase, required_artifacts completion) separately.

Checks:
1. Artifact file exists at expected path
2. Artifact is valid JSON
3. Machine output has RNS|D| and RNS|Z| markers

Returns None (allow) on pass, {"decision": "warn"} with reason on failure.
Does NOT block — skill-guard Stop is the contract authority.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import gto_state_dir, write_hook_output


def run(data: dict) -> dict | None:
    """In-process hook entry point."""
    session_id = data.get("session_id")
    state_dir = gto_state_dir(session_id)
    artifact_path = state_dir.parent / "outputs" / "artifact.json"

    if not artifact_path.exists():
        return {
            "decision": "warn",
            "reason": f"gto-v2: artifact not found at {artifact_path}",
        }

    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "decision": "warn",
            "reason": f"gto-v2: artifact not valid JSON: {exc}",
        }

    machine = artifact.get("machine_output", [])
    if isinstance(machine, list):
        has_d = any(isinstance(l, str) and l.startswith("RNS|D|") for l in machine)
        has_z = any(isinstance(l, str) and l.startswith("RNS|Z|") for l in machine)
        if not has_d or not has_z:
            return {
                "decision": "warn",
                "reason": "gto-v2: artifact machine_output missing RNS|D| or RNS|Z| markers",
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
