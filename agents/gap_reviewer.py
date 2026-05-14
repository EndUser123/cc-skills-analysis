"""Gap Reviewer Agent — structured gap-to-opportunity review with context injection.

Receives pre-populated detector evidence (findings, changed files, session outcomes,
absence signals) and produces a structured FACT/INFERENCE/UNKNOWN/RECOMMENDATION review
plus any new gaps discovered during the review.

This is the "adaptive" layer: one stable prompt lens + deterministic context injection,
so the review is automatically tailored to each session's actual state without N
domain-specific prompt variants.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import parse_agent_result
from ..models import AgentResult, EvidenceRef, Finding


def write_handoff(
    path: Path,
    findings: list[Finding],
    session_outcomes: list[dict] | None = None,
    changed_files: list[str] | None = None,
    session_context: dict | None = None,
    detectors_ran: list[str] | None = None,
    detectors_empty: list[str] | None = None,
) -> None:
    """Write context-enriched handoff for the gap reviewer agent.

    Args:
        path: Handoff file path (result path derived from sibling).
        findings: Current findings from the deterministic pipeline.
        session_outcomes: Session outcome items (from session_outcome_detector).
        changed_files: Files changed since last GTO run.
        session_context: Terminal/session/git metadata.
        detectors_ran: Names of detectors that produced findings.
        detectors_empty: Names of detectors that ran but found nothing (absence signals).
    """
    detected_facts: list[dict[str, str]] = []

    for f in findings:
        fact = {"claim": f.title, "source": f.source_name or "detector"}
        if f.file:
            fact["source"] += f" @ {f.file}"
            if f.line:
                fact["source"] += f":{f.line}"
        detected_facts.append(fact)

    if session_outcomes:
        for item in session_outcomes:
            detected_facts.append({
                "claim": f"Session outcome: {item.get('content', '')}",
                "source": f"session_outcome_detector ({item.get('category', 'unknown')})",
            })

    if changed_files:
        for cf in changed_files[:20]:
            detected_facts.append({"claim": f"File changed: {cf}", "source": "changelog_detector"})

    signals_absent: list[dict[str, str]] = []
    for det in (detectors_empty or []):
        signals_absent.append({
            "detector": det,
            "result": "no findings produced",
        })

    handoff = {
        "role": "gap_reviewer",
        "detected_facts": detected_facts,
        "signals_absent": signals_absent,
        "session_context": session_context or {},
        "findings": [f.to_dict() for f in findings],
        "detectors_ran": detectors_ran or [],
        "output_path": str(path.parent / "gap_reviewer_result.json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")


def read_result(path: Path) -> AgentResult:
    """Read the gap reviewer result.

    The reviewer outputs both a structured review and optional new findings.
    We extract findings from the "findings" array; the review text is preserved
    in raw_notes for display.
    """
    if not path.exists():
        return AgentResult(agent="gap_reviewer", findings=[], success=False)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AgentResult(agent="gap_reviewer", findings=[], success=False)

    if not isinstance(data, dict):
        return parse_agent_result(path, "gap_reviewer")

    review = data.get("review", {})
    notes_parts: list[str] = []
    for section in ("facts", "inferences", "unknowns", "recommendations"):
        items = review.get(section, [])
        if items:
            notes_parts.append(f"[{section.upper()}]")
            for item in items:
                if isinstance(item, dict):
                    notes_parts.append(f"- {item}")
                else:
                    notes_parts.append(f"- {item}")

    raw_notes = "\n".join(notes_parts)

    raw_findings = data.get("findings", [])
    if isinstance(raw_findings, list):
        findings: list[Finding] = []
        for item in raw_findings:
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
                    id=item.get("id", "GAPR-???"),
                    title=item.get("title", "Gap reviewer finding"),
                    description=item.get("description", ""),
                    source_type="agent",
                    source_name="gap_reviewer",
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
        return AgentResult(agent="gap_reviewer", findings=findings, success=True, raw_notes=raw_notes)

    return AgentResult(agent="gap_reviewer", findings=[], success=False, raw_notes=raw_notes)
