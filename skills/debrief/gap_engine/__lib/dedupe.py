from __future__ import annotations

from ..models import Finding


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Deduplicate findings by (domain, title, file).

    Keeps the first occurrence when duplicates are found.
    """
    seen: set[str] = set()
    result: list[Finding] = []
    for f in findings:
        key = f"{f.domain}|{f.title}|{f.file or ''}"
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result
