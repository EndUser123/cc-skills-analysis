from __future__ import annotations

from dataclasses import replace

from ..models import Finding

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
VALID_SEVERITIES = set(SEVERITY_ORDER)
VALID_ACTIONS = {"recover", "prevent", "realize"}
VALID_PRIORITIES = {"critical", "high", "medium", "low"}

DOMAIN_ALIASES: dict[str, str] = {
    "code_quality": "quality",
    "testing": "tests",
    "documentation": "docs",
    "dependencies": "deps",
}


def normalize_finding(f: Finding) -> Finding:
    """Normalize a finding's domain, severity, action, and priority."""
    domain = DOMAIN_ALIASES.get(f.domain, f.domain)
    severity = f.severity if f.severity in VALID_SEVERITIES else "medium"
    action = f.action if f.action in VALID_ACTIONS else "recover"
    priority = f.priority if f.priority in VALID_PRIORITIES else "medium"
    return replace(f, domain=domain, severity=severity, action=action, priority=priority)


def normalize_findings(findings: list[Finding]) -> list[Finding]:
    return [normalize_finding(f) for f in findings]
