"""Domain Analyzer Agent — enriches findings with project domain context.

Reads initial findings from deterministic detectors and session analysis,
then enriches them with domain-specific health assessments. The agent runs
as a Claude Code subagent (spawned by the LLM following SKILL.md instructions)
and writes structured JSON to the artifact directory.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import parse_agent_result
from ..models import AgentResult, Finding


def write_handoff(
    path: Path,
    findings: list[Finding],
    project_context: dict,
) -> None:
    """Write findings + project context for the domain analyzer agent."""
    handoff = {
        "role": "domain_analyzer",
        "project": project_context,
        "findings": [f.to_dict() for f in findings],
        "output_path": str(path.parent / "domain_analyzer_result.json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")


def read_result(path: Path) -> AgentResult:
    """Read the domain analyzer result."""
    return parse_agent_result(path, "domain_analyzer")
