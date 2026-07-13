"""Structural analysis — pattern detection across GAP findings.

Reads findings and the evidence map to detect cross-cutting patterns that an LLM
(consuming the artifact) can use for context. Produces a machine-readable structural
summary, not a visual diagram.

Designed for LLM consumption: structured data with natural-language pattern names
and confidence indicators, not SVG/Mermaid output.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..models import Finding
from .evidence_map import build_evidence_map


def analyze_structure(findings: list[Finding]) -> dict[str, Any]:
    """Detect cross-cutting patterns across findings for LLM consumption.

    Returns a structural summary with:
    - root_cause_clusters: groups of findings sharing a root cause
    - domain_concentrations: domains with disproportionate finding counts
    - cross_domain_files: files referenced by findings across multiple domains
    - severity_distribution: finding count by severity level
    - carryover_patterns: escalated or recurring findings
    - detector_coverage: which detectors produced findings, which were silent
    """
    evidence_map = build_evidence_map(findings)

    # Root cause clusters (2+ findings sharing a root cause)
    root_cause_clusters: list[dict[str, Any]] = []
    for rc, ids in evidence_map["by_root_cause"].items():
        if rc == "unknown" or len(ids) < 2:
            continue
        rc_findings = [f for f in findings if f.id in ids]
        domains = sorted({f.domain for f in rc_findings})
        root_cause_clusters.append({
            "root_cause": rc,
            "count": len(ids),
            "finding_ids": ids,
            "domains": domains,
            "pattern": f"{len(ids)} findings share root_cause={rc} across {len(domains)} domain(s): {', '.join(domains)}",
        })

    # Domain concentrations
    domain_counts = Counter(f.domain for f in findings)
    total = len(findings) or 1
    domain_concentrations: list[dict[str, Any]] = []
    for domain, count in domain_counts.most_common():
        pct = count / total
        domain_concentrations.append({
            "domain": domain,
            "count": count,
            "percentage": round(pct * 100, 1),
        })

    # Cross-domain files (files referenced by findings in 2+ domains)
    file_domains: dict[str, set[str]] = {}
    for f in findings:
        if f.file:
            file_domains.setdefault(f.file, set()).add(f.domain)
    cross_domain_files = [
        {"file": fp, "domains": sorted(doms), "count": len(doms)}
        for fp, doms in sorted(file_domains.items())
        if len(doms) >= 2
    ]

    # Severity distribution
    severity_dist = dict(Counter(f.severity for f in findings))

    # Carryover patterns (findings from carryover that escalated)
    carryover_findings = [f for f in findings if f.source_type == "carryover"]
    carryover_patterns: list[dict[str, Any]] = []
    if carryover_findings:
        escalated = [f for f in carryover_findings if f.severity in ("critical", "high")]
        carryover_patterns.append({
            "total_carryover": len(carryover_findings),
            "escalated_to_high_or_critical": len(escalated),
            "escalated_ids": [f.id for f in escalated],
        })

    # Detector coverage
    detector_counts = Counter(f.source_name for f in findings if f.source_name)
    detector_coverage = [
        {"detector": det, "findings": count}
        for det, count in detector_counts.most_common()
    ]

    return {
        "root_cause_clusters": root_cause_clusters,
        "domain_concentrations": domain_concentrations,
        "cross_domain_files": cross_domain_files,
        "severity_distribution": severity_dist,
        "carryover_patterns": carryover_patterns,
        "detector_coverage": detector_coverage,
        "total_findings": len(findings),
    }


def write_structural_summary(output_path: Path, findings: list[Finding]) -> dict[str, Any]:
    """Compute structural analysis and write to disk. Returns the summary dict."""
    summary = analyze_structure(findings)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary
