from __future__ import annotations

from ..models import Finding

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
DOMAIN_RANK = {
    "security": 0,
    "quality": 1,
    "tests": 2,
    "performance": 3,
    "docs": 4,
    "deps": 5,
    "git": 6,
    "other": 7,
}

# Skill dependency ordering — run prerequisites first
# Maps skill → list of skills that should run before it
SKILL_PREREQUISITES: dict[str, list[str]] = {
    "/docs": ["/code", "/sqa"],
    "/deps": ["/sqa"],
    "/sqa --layer=L7": ["/sqa"],
}


def _skill_order_rank(skill: str | None) -> int:
    """Return ordering rank for a skill based on dependency graph.

    Lower = should run first. Skills not in the graph get rank 5.
    """
    if not skill:
        return 5
    # Base skills that others depend on come first
    base_skills = {"/code", "/diagnose", "/perf", "pytest", "/sqa"}
    if skill in base_skills:
        return 1
    if skill in SKILL_PREREQUISITES:
        return 3
    return 5


def order_findings(findings: list[Finding]) -> list[Finding]:
    """Order findings by severity, domain, and skill dependency."""
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_RANK.get(f.severity, 99),
            DOMAIN_RANK.get(f.domain, 99),
            _skill_order_rank(f.owner_skill),
            f.id,
        ),
    )
