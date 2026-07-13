from __future__ import annotations

import json
from pathlib import Path

from ..models import Finding, EvidenceRef, AgentResult


def parse_agent_result(path: Path, agent_name: str) -> AgentResult:
    """Read and parse an agent result file into an AgentResult.

    Handles both bare JSON arrays ``[{...}, ...]`` and wrapped
    ``{"findings": [...], "notes": "..."}`` formats.
    """
    if not path.exists():
        return AgentResult(agent=agent_name, findings=[], success=False)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AgentResult(agent=agent_name, findings=[], success=False)

    if isinstance(data, list):
        items, notes = data, ""
    elif isinstance(data, dict):
        items, notes = data.get("findings", []), data.get("notes", "")
    else:
        return AgentResult(agent=agent_name, findings=[], success=False)

    findings: list[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "rejected":
            continue
        evidence = [
            EvidenceRef(kind=e.get("kind", ""), value=e.get("value", ""))
            for e in item.get("evidence", [])
            if isinstance(e, dict)
        ]
        findings.append(
            Finding(
                id=item.get("id", f"{agent_name[:4].upper()}-???"),
                title=item.get("title", "Agent finding"),
                description=item.get("description", ""),
                source_type="agent",
                source_name=agent_name,
                domain=item.get("domain", "other"),
                gap_type=item.get("gap_type", "unknown"),
                severity=item.get("severity", "medium"),
                evidence_level=item.get("evidence_level", "unverified"),
                action=item.get("action", "recover"),
                priority=item.get("priority", "medium"),
                file=item.get("file"),
                line=item.get("line"),
                effort=item.get("effort"),
                unverified=item.get("unverified", True),
                evidence=evidence,
            )
        )

    return AgentResult(
        agent=agent_name,
        findings=findings,
        raw_notes=notes if isinstance(data, dict) else "",
        success=True,
    )
