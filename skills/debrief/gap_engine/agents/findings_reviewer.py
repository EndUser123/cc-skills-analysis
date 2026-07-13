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


def read_verdicts(path: Path) -> tuple[set[str], dict[str, str]]:
    """Read verdict-format reviewer results. Returns (rejected_ids, reasons)."""
    if not path.exists():
        return set(), {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set(), {}

    verdicts = data.get("verdicts", []) if isinstance(data, dict) else []
    rejected: set[str] = set()
    reasons: dict[str, str] = {}
    for v in verdicts:
        if isinstance(v, dict) and v.get("action") == "reject":
            fid = v.get("finding_id", "")
            if fid:
                rejected.add(fid)
                reasons[fid] = v.get("reason", "")
    return rejected, reasons


def read_result(path: Path) -> AgentResult:
    """Read the findings reviewer result."""
    return parse_agent_result(path, "findings_reviewer")
