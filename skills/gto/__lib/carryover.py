from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ..models import Finding, EvidenceRef
from .util import atomic_write_json

# Severity escalation ladder — each step bumps one level
SEVERITY_LADDER: dict[str, str] = {
    "low": "medium",
    "medium": "high",
    "high": "critical",
    "critical": "critical",
}


def load_carryover(artifacts_dir: Path) -> list[Finding]:
    """Load carryover findings from prior GTO runs in this terminal scope.

    Looks for `carryover.json` in the artifacts directory.
    Returns empty list if file doesn't exist or is unparseable.
    """
    path = artifacts_dir / "carryover.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    findings: list[Finding] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        evidence = [
            EvidenceRef(
                kind=e.get("kind", ""),
                value=e.get("value", ""),
                detail=e.get("detail"),
            )
            for e in item.get("evidence", [])
            if isinstance(e, dict)
        ]
        findings.append(
            Finding(
                id=item.get("id", "CARRY-???"),
                title=item.get("title", "Carryover finding"),
                description=item.get("description", ""),
                source_type="carryover",
                source_name="carryover",
                domain=item.get("domain", "other"),
                gap_type=item.get("gap_type", "carryover"),
                severity=item.get("severity", "medium"),
                evidence_level=item.get("evidence_level", "unverified"),
                action=item.get("action", "recover"),
                priority=item.get("priority", "medium"),
                status=item.get("status", "open"),
                scope=item.get("scope", "local"),
                owner_skill=item.get("owner_skill"),
                owner_reason=item.get("owner_reason"),
                file=item.get("file"),
                line=item.get("line"),
                symbol=item.get("symbol"),
                reversibility=item.get("reversibility"),
                effort=item.get("effort"),
                target=item.get("target"),
                depends_on=item.get("depends_on", []),
                evidence=evidence,
                tags=item.get("tags", []),
                terminal_id=item.get("terminal_id"),
                session_id=item.get("session_id"),
                git_sha=item.get("git_sha"),
                freshness=item.get("freshness"),
                unverified=item.get("unverified", True),
                metadata=item.get("metadata", {}),
            )
        )
    return findings


def save_carryover(artifacts_dir: Path, findings: list[Finding]) -> None:
    """Save findings as carryover for future runs.

    Persists open findings (to re-surface) and resolved findings (to suppress).
    Rejected findings are discarded. Increments _carry_count on open findings.
    """
    carryover: list[Finding] = []
    for f in findings:
        if f.status == "rejected":
            continue
        # Increment carry count on open findings so future runs can escalate/decay
        if f.status == "open":
            count = f.metadata.get("_carry_count", 0) + 1
            first_seen = f.metadata.get("_first_seen")
            if first_seen is None:
                from datetime import datetime, timezone
                first_seen = datetime.now(timezone.utc).isoformat()
            new_meta = {**f.metadata, "_carry_count": count, "_first_seen": first_seen}
            f = replace(f, metadata=new_meta)
        carryover.append(f)

    path = artifacts_dir / "carryover.json"
    data = [f.to_dict() for f in carryover]
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)


def load_carryover_open_only(artifacts_dir: Path) -> list[Finding]:
    """Load only open (unresolved) carryover findings."""
    return [f for f in load_carryover(artifacts_dir) if f.status == "open"]


def apply_carryover_enrichment(
    findings: list[Finding],
    changed_files: list[str] | None = None,
) -> list[Finding]:
    """Apply escalation and decay to carryover findings.

    Escalation: systemic/architectural findings carried 2+ times get severity bump
    and "RECURRING" prefix on title.

    Decay: local-scoped findings whose referenced file was changed get a staleness
    note — the context that produced the finding may no longer exist.
    """
    enriched: list[Finding] = []
    for f in findings:
        count: int = f.metadata.get("_carry_count", 0)

        if count >= 2 and f.scope in ("systemic", "architectural"):
            new_sev = SEVERITY_LADDER.get(f.severity, f.severity)
            title = f.title
            if not title.startswith("RECURRING"):
                title = f"RECURRING ({count}x): {title}"
            f = replace(f, severity=new_sev, priority=new_sev, title=title)

        elif count >= 3 and f.scope == "local" and f.file:
            if changed_files and f.file in changed_files:
                desc = f.description
                tag = "[context may have changed]"
                if tag not in desc:
                    desc = f"{desc} {tag} — file modified since finding created"
                f = replace(f, description=desc, evidence_level="unverified")

        enriched.append(f)
    return enriched


def prune_carryover(artifacts_dir: Path, max_resolved: int = 50) -> None:
    """Remove old resolved findings to prevent unbounded growth."""
    findings = load_carryover(artifacts_dir)
    open_findings = [f for f in findings if f.status != "resolved"]
    resolved_findings = [f for f in findings if f.status == "resolved"]
    if len(resolved_findings) <= max_resolved:
        return
    kept = resolved_findings[-max_resolved:]
    all_findings = open_findings + kept
    path = artifacts_dir / "carryover.json"
    data = [f.to_dict() for f in all_findings]
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)
