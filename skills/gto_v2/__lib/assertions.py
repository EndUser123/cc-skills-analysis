#!/usr/bin/env python3
"""CLI-runnable assertions for GTO artifact verification.

Usage:
    python -m skills.gto.__lib.assertions <artifact_path> [--state <state_path>]

Exit codes:
    0 — all assertions pass
    1 — one or more assertions failed (details on stderr)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: assertions.py <artifact_path> [--state <state_path>]", file=sys.stderr)
        sys.exit(1)

    artifact_path = Path(args[0])
    state_path: Path | None = None

    if "--state" in args:
        idx = args.index("--state")
        if idx + 1 < len(args):
            state_path = Path(args[idx + 1])

    errors: list[str] = []

    # Verify artifact exists and is valid JSON
    if not artifact_path.exists():
        print(f"FAIL: artifact not found: {artifact_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"FAIL: cannot parse artifact: {exc}", file=sys.stderr)
        sys.exit(1)

    # Required fields
    required = ["artifact_version", "terminal_id", "session_id", "findings",
                "machine_output", "human_output"]
    for field in required:
        if field not in data:
            errors.append(f"missing field: {field}")

    # Machine output must have RNS format
    machine = data.get("machine_output", [])
    if isinstance(machine, list):
        if not any(isinstance(l, str) and l.startswith("RNS|D|") for l in machine):
            errors.append("machine_output missing RNS|D| header")
        if not any(isinstance(l, str) and l.startswith("RNS|Z|") for l in machine):
            errors.append("machine_output missing RNS|Z| terminator")

    # Findings must be a list
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings is not a list")

    # State verification if provided
    if state_path:
        if not state_path.exists():
            errors.append(f"state file not found: {state_path}")
        else:
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("phase") != "completed":
                    errors.append(f"state phase is '{state.get('phase')}', expected 'completed'")
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"cannot parse state: {exc}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"PASS: {artifact_path} ({len(findings or [])} findings)")
    sys.exit(0)


if __name__ == "__main__":
    main()
