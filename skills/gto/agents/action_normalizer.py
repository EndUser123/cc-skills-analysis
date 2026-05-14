"""Action Normalizer Agent — converts findings into canonical RNS action items.

Ensures each finding has valid domain, severity, action, priority, effort,
and evidence_level fields suitable for RNS rendering. Runs as a Claude Code subagent.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import parse_agent_result
from ..models import AgentResult, Finding


def write_handoff(
    path: Path,
    findings: list[Finding],
) -> None:
    """Write findings for the action normalizer agent."""
    handoff = {
        "role": "action_normalizer",
        "findings": [f.to_dict() for f in findings],
        "output_path": str(path.parent / "action_normalizer_result.json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")


def read_result(path: Path) -> AgentResult:
    """Read the action normalizer result."""
    return parse_agent_result(path, "action_normalizer")
