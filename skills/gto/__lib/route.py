from __future__ import annotations

from dataclasses import replace

from ..models import Finding

# Maps gap_type prefixes to owning skills.
# Findings not matching any route remain unrouted (owner_skill=None).
GAP_TYPE_ROUTES: dict[str, str] = {
    "missingdocs": "/docs",
    "techdebt": "/code",
    "runtime_error": "/diagnose",
    "bug": "/diagnose",
    "security": "/security",
    "perf": "/perf",
    "invalidrepo": "/git",
    "staledeps": "/deps",
}


def route_finding(f: Finding) -> Finding:
    """Route a single finding to an owning skill based on gap_type."""
    owner = GAP_TYPE_ROUTES.get(f.gap_type)
    if owner:
        return replace(
            f,
            owner_skill=owner,
            owner_reason=f"routed by gap_type '{f.gap_type}'",
        )
    return f


def route_findings(findings: list[Finding]) -> list[Finding]:
    return [route_finding(f) for f in findings]
