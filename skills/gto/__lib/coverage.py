from __future__ import annotations

from typing import Any

from ..models import Finding


def compute_coverage(findings: list[Finding]) -> dict[str, Any]:
    """Compute coverage summary for a list of findings.

    Returns a dict with domain coverage, severity breakdown, and routing stats.
    """
    by_domain: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_action: dict[str, int] = {}
    routed = 0
    unrouted = 0
    verified = 0
    unverified_count = 0

    for f in findings:
        by_domain[f.domain] = by_domain.get(f.domain, 0) + 1
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_action[f.action] = by_action.get(f.action, 0) + 1
        if f.owner_skill:
            routed += 1
        else:
            unrouted += 1
        if f.unverified:
            unverified_count += 1
        else:
            verified += 1

    return {
        "total": len(findings),
        "by_domain": by_domain,
        "by_severity": by_severity,
        "by_action": by_action,
        "routed": routed,
        "unrouted": unrouted,
        "verified": verified,
        "unverified": unverified_count,
    }


def compute_health_score(findings: list[Finding], freshness: str = "fresh") -> dict[str, Any]:
    """Compute a session health score from findings and freshness.

    Score: 0-100 where 100 = no open findings, fresh artifact.
    Tracks resolved vs open to show improvement trajectory.
    """
    total = len(findings)
    if total == 0:
        return {"score": 100, "grade": "A", "freshness": freshness, "total": 0}

    resolved = sum(1 for f in findings if f.status == "resolved")
    open_count = sum(1 for f in findings if f.status == "open")
    critical = sum(1 for f in findings if f.severity == "critical" and f.status != "resolved")

    # Base score from resolution rate
    resolution_rate = resolved / total if total > 0 else 1.0
    base_score = resolution_rate * 80  # Max 80 from resolution

    # Bonus for freshness
    freshness_bonus = {"fresh": 20, "unknown": 10, "stale-git": 0, "stale-target": 0}
    bonus = freshness_bonus.get(freshness, 10)

    # Penalty for critical open findings
    critical_penalty = min(critical * 10, 30)

    score = max(0, min(100, int(base_score + bonus - critical_penalty)))

    grades = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]
    grade = next(g for threshold, g in grades if score >= threshold)

    return {
        "score": score,
        "grade": grade,
        "freshness": freshness,
        "total": total,
        "resolved": resolved,
        "open": open_count,
        "critical_open": critical,
        "resolution_rate": round(resolution_rate, 2),
    }
