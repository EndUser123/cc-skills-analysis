"""Impact radius estimation — count import references for changed files.

When a file changes, count how many other files import or reference it.
A finding with impact radius 20 is more urgent than one with radius 1.
"""
from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from ..models import Finding


def count_references(root: Path, file_path: str) -> int:
    """Count how many files import or reference the given file.

    Uses git grep to count references. Returns 0 on error.
    """
    # Extract module name from path (e.g., "skills/gto/__lib/changelog.py" → "changelog")
    stem = Path(file_path).stem
    if stem.startswith("__"):
        return 0

    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "grep", "-r", "--count", "-w", stem, "--", "*.py"],
            text=True,
        )
        # git grep --count outputs "file:count" lines
        total = 0
        for line in out.strip().splitlines():
            if ":" in line:
                parts = line.rsplit(":", 1)
                if parts[-1].isdigit() and parts[0] != file_path:
                    total += int(parts[-1])
        return total
    except subprocess.CalledProcessError:
        return 0


def enrich_with_impact_radius(
    root: Path,
    findings: list[Finding],
) -> list[Finding]:
    """Add impact radius metadata to findings that have file references.

    For each finding with a file reference, counts how many other files
    reference it and stores the count in metadata. Findings with high
    impact radius get elevated severity.
    """
    enriched: list[Finding] = []
    for f in findings:
        if not f.file:
            enriched.append(f)
            continue

        radius = count_references(root, f.file)
        if radius == 0:
            enriched.append(f)
            continue

        new_meta = {**f.metadata, "impact_radius": radius}

        # High impact radius elevates severity one step
        severity = f.severity
        priority = f.priority
        if radius >= 10 and f.severity == "medium":
            severity = "high"
            priority = "high"

        enriched.append(replace(
            f,
            severity=severity,
            priority=priority,
            metadata=new_meta,
            description=f"{f.description} [impact radius: {radius}]",
        ))

    return enriched
