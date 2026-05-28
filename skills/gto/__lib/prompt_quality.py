"""Prompt quality validator — structural checks on LLM agent output.

Validates that agent-produced findings conform to their expected schema.
Violations are logged as warnings, not errors (don't fail the pipeline).
"""
from __future__ import annotations

from typing import Any

AGENT_SCHEMAS: dict[str, dict[str, Any]] = {
    "domain_analyzer": {
        "required_fields": ["id", "title", "domain", "severity", "evidence"],
        "min_evidence": 1,
    },
    "findings_reviewer": {
        "required_fields": ["id", "review_notes", "status"],
        "max_findings": 15,
    },
    "action_normalizer": {
        "required_fields": ["id", "domain", "severity", "action", "priority"],
    },
    "gap_reviewer": {
        "required_fields": ["id", "root_cause", "evidence"],
        "min_evidence": 1,
    },
    "session_reviewer": {
        "required_fields": ["original_content", "classification", "reason"],
    },
}


def validate_prompt_output(
    agent_name: str,
    findings: list[dict[str, Any]],
) -> list[str]:
    """Validate agent output against structural schema. Returns violation strings."""
    violations: list[str] = []
    schema = AGENT_SCHEMAS.get(agent_name)
    if not schema:
        return [f"unknown agent schema: {agent_name}"]

    required = schema.get("required_fields", [])
    min_evidence = schema.get("min_evidence", 0)
    max_findings = schema.get("max_findings")

    if max_findings and len(findings) > max_findings:
        violations.append(f"{agent_name}: {len(findings)} findings exceeds max {max_findings}")

    seen_ids: set[str] = set()
    for f in findings:
        fid = f.get("id", "")
        if fid in seen_ids:
            violations.append(f"{agent_name}: duplicate id {fid}")
        seen_ids.add(fid)

        for field in required:
            if field not in f or f[field] is None:
                violations.append(f"{agent_name}: missing {field} in {fid or 'unknown'}")

        if min_evidence:
            evidence = f.get("evidence", [])
            if not evidence or len(evidence) < min_evidence:
                violations.append(f"{agent_name}: {fid} has <{min_evidence} evidence items")

    return violations
