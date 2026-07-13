"""Evidence map — invertible provenance index for GAP findings.

Builds a flat lookup from findings indexed by source, file, root_cause, and domain.
Written as evidence_map.json alongside artifact.json for downstream query.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Finding


def build_evidence_map(findings: list[Finding]) -> dict[str, dict[str, list[str]]]:
    """Build invertible index from findings for provenance queries."""
    by_source: dict[str, list[str]] = {}
    by_file: dict[str, list[str]] = {}
    by_root_cause: dict[str, list[str]] = {}
    by_domain: dict[str, list[str]] = {}

    for f in findings:
        if f.source_name:
            by_source.setdefault(f.source_name, []).append(f.id)
        if f.file:
            by_file.setdefault(f.file, []).append(f.id)
        if f.root_cause:
            by_root_cause.setdefault(f.root_cause, []).append(f.id)
        if f.domain:
            by_domain.setdefault(f.domain, []).append(f.id)

    return {
        "by_source": by_source,
        "by_file": by_file,
        "by_root_cause": by_root_cause,
        "by_domain": by_domain,
    }


def write_evidence_map(output_path: Path, findings: list[Finding]) -> None:
    """Build and write evidence map to disk."""
    evidence_map = build_evidence_map(findings)
    output_path.write_text(
        json.dumps(evidence_map, indent=2, ensure_ascii=False) + chr(10),
        encoding="utf-8",
    )
