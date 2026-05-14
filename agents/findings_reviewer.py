"""Findings Reviewer Agent — validates findings for quality and accuracy.

Reviews findings for missing evidence, duplication, false positives,
and severity misclassification. Runs as a Claude Code subagent.
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
    """Write findings for the reviewer agent."""
    handoff = {
        "role": "findings_reviewer",
        "findings": [f.to_dict() for f in findings],
        "output_path": str(path.parent / "findings_reviewer_result.json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")


def read_result(path: Path) -> AgentResult:
    """Read the findings reviewer result."""
    return parse_agent_result(path, "findings_reviewer")
