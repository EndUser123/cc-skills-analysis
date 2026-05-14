"""Finding resolution checker for GTO.

Determines which findings have been addressed by comparing against
session-scoped file changes and re-running detector checks.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..models import EvidenceRef, Finding


def resolve_findings(
    findings: list[Finding],
    changed: set[str],
    root: Path,
) -> list[Finding]:
    """Check findings against session changes and mark resolved.

    Returns a new list with status and evidence updated for resolved findings.
    Three resolution signals:
      1. File edit match — finding targets a file that was edited this session
      2. Already resolved — finding carried over with status="resolved"
      3. Detector re-check — known detector conditions no longer hold
    """
    result: list[Finding] = []
    for f in findings:
        resolved = _try_resolve(f, changed, root)
        result.append(resolved if resolved else f)
    return result


def _try_resolve(
    f: Finding, changed: set[str], root: Path
) -> Finding | None:
    """Attempt to resolve a single finding. Returns updated Finding or None."""
    # Signal 2: already resolved
    if f.status == "resolved":
        return f

    # Signal 1: file edit match
    if f.file:
        normalized = f.file.replace("\\", "/")
        if normalized in changed:
            return _mark_resolved(f, f"file_edited: {f.file}")

    # Signal 3: detector re-check
    detector_check = _detector_recheck(f, root)
    if detector_check:
        return _mark_resolved(f, detector_check)

    return None


def _mark_resolved(f: Finding, reason: str) -> Finding:
    """Return a copy of the finding with resolved status and evidence."""
    evidence = list(f.evidence) + [
        EvidenceRef(kind="auto_resolved", value=reason)
    ]
    return replace(f, status="resolved", evidence=evidence)


def _detector_recheck(f: Finding, root: Path) -> str | None:
    """Re-run specific detector checks. Returns reason if resolved, None otherwise."""
    if f.id == "DOC-001":
        # README missing — check if it exists now
        if (root / "README.md").exists():
            return "README.md now exists"
        return None

    if f.id == "GIT-001":
        # .git missing — check if it exists now
        if (root / ".git").exists():
            return ".git directory now exists"
        return None

    return None


def _evidence_count(f: Finding) -> int | None:
    """Extract the numeric count from a finding's count evidence, if any."""
    for e in f.evidence:
        if e.kind == "count":
            try:
                return int(e.value)
            except (ValueError, TypeError):
                return None
    return None
