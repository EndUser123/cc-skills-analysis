from __future__ import annotations

from ..models import Finding

SEVERITY_ICONS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
}

DOMAIN_ICONS: dict[str, str] = {
    "quality": "🔧",
    "tests": "🧪",
    "docs": "📄",
    "security": "🔒",
    "performance": "⚡",
    "git": "🐙",
    "deps": "📦",
    "other": "📌",
}


def render_finding(f: Finding, index: int) -> str:
    """Render a single finding as a human-readable line."""
    icon = SEVERITY_ICONS.get(f.severity, "⚪")
    domain_icon = DOMAIN_ICONS.get(f.domain, "📌")
    parts = [f"{index}. {icon} [{f.severity.upper()}] {f.title}"]
    parts.append(f"   Domain: {domain_icon} {f.domain} | Gap: {f.gap_type}")
    parts.append(f"   {f.description}")
    if f.file:
        line_ref = f":{f.line}" if f.line else ""
        parts.append(f"   @ {f.file}{line_ref}")
    if f.owner_skill:
        parts.append(f"   → {f.owner_skill}")
    if f.unverified:
        parts.append("   [UNVERIFIED]")
    return "\n".join(parts)


def render_findings(findings: list[Finding], header: str = "GTO Findings") -> str:
    """Render all findings as a human-readable report."""
    if not findings:
        return f"{header}\nNo findings."

    lines = [f"{header} ({len(findings)} items)", ""]
    for i, f in enumerate(findings, 1):
        lines.append(render_finding(f, i))
        lines.append("")

    # Summary
    by_severity: dict[str, int] = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    summary_parts = [f"{SEVERITY_ICONS.get(s, '⚪')} {s}: {c}" for s, c in sorted(by_severity.items())]
    lines.append(f"Summary: {' | '.join(summary_parts)}")
    return "\n".join(lines)
