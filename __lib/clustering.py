"""Finding clustering — groups findings by directory or module prefix.

When multiple findings reference files in the same directory or module,
clusters them into a single recommendation for that area.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from pathlib import PurePosixPath

from ..models import Finding


def _extract_dir(file_path: str | None) -> str | None:
    """Extract directory prefix from a file path."""
    if not file_path:
        return None
    parts = PurePosixPath(file_path).parts
    if len(parts) <= 1:
        return None
    # Use first 2 path segments as cluster key
    return "/".join(parts[:2])


def cluster_findings(findings: list[Finding]) -> list[Finding]:
    """Cluster findings by directory and emit grouped recommendations.

    Findings without a file reference pass through unchanged.
    Findings with files in the same directory get merged into one
    clustered finding per directory per skill.

    Returns the original findings plus any cluster summary findings.
    """
    # Group by (directory, owner_skill)
    clusters: dict[tuple[str, str | None], list[Finding]] = defaultdict(list)
    unclustered: list[Finding] = []

    for f in findings:
        d = _extract_dir(f.file)
        if d:
            clusters[(d, f.owner_skill)].append(f)
        else:
            unclustered.append(f)

    # Only create cluster findings when 3+ findings share a directory+skill
    cluster_findings: list[Finding] = []
    for idx, ((directory, skill), group) in enumerate(
        sorted(clusters.items()), start=1
    ):
        if len(group) < 3:
            unclustered.extend(group)
            continue

        ids = [f.id for f in group]
        titles = list({f.title[:60] for f in group})
        severity = max(
            group,
            key=lambda f: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(f.severity, 0),
        ).severity

        cluster_findings.append(
            Finding(
                id=f"CLUSTER-{idx:03d}",
                title=f"{len(group)} findings cluster in {directory}/ — consider {skill or 'review'}",
                description=(
                    f"Clustered findings: {', '.join(ids[:5])}. "
                    f"Areas: {', '.join(titles[:3])}"
                ),
                source_type="detector",
                source_name="clustering",
                domain=group[0].domain,
                gap_type="clustered_findings",
                severity=severity,
                evidence_level="derived",
                action="realize",
                priority=severity,
                owner_skill=skill,
                file=directory,
                evidence=[],
                metadata={"clustered_ids": ids},
            )
        )

    return unclustered + cluster_findings
