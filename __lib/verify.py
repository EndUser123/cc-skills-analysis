from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import GTOArtifact


def verify_artifact(artifact_path: Path) -> dict[str, Any]:
    """Verify a GTO artifact file has the required structure.

    Returns a dict with 'valid' (bool) and 'errors' (list of strings).
    """
    result: dict[str, Any] = {"valid": True, "errors": []}

    if not artifact_path.exists():
        result["valid"] = False
        result["errors"].append(f"Artifact file not found: {artifact_path}")
        return result

    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result["valid"] = False
        result["errors"].append(f"Cannot parse artifact JSON: {exc}")
        return result

    required_fields = [
        "artifact_version",
        "mode",
        "terminal_id",
        "session_id",
        "target",
        "findings",
        "machine_output",
        "human_output",
        "verification",
        "coverage",
    ]

    for field in required_fields:
        if field not in data:
            result["valid"] = False
            result["errors"].append(f"Missing required field: {field}")

    # Verify machine_output has RNS format lines
    machine = data.get("machine_output", [])
    if isinstance(machine, list):
        has_rns_d = any(isinstance(line, str) and line.startswith("RNS|D|") for line in machine)
        has_rns_z = any(isinstance(line, str) and line.startswith("RNS|Z|") for line in machine)
        has_findings = len(data.get("findings", [])) > 0
        if not has_rns_d and has_findings:
            result["valid"] = False
            result["errors"].append("machine_output missing RNS|D| domain header")
        if not has_rns_z:
            result["valid"] = False
            result["errors"].append("machine_output missing RNS|Z| terminator")

    return result


def verify_state(state_path: Path) -> dict[str, Any]:
    """Verify run state has completed all expected phases."""
    result: dict[str, Any] = {"valid": True, "errors": []}

    if not state_path.exists():
        result["valid"] = False
        result["errors"].append(f"State file not found: {state_path}")
        return result

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result["valid"] = False
        result["errors"].append(f"Cannot parse state JSON: {exc}")
        return result

    if data.get("phase") != "completed":
        result["valid"] = False
        result["errors"].append(f"State phase is '{data.get('phase')}', expected 'completed'")

    return result
