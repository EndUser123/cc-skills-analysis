from __future__ import annotations

from ..models import Finding


def merge_findings(deterministic: list[Finding], agent: list[Finding]) -> list[Finding]:
    """Merge deterministic detector findings with agent findings.

    Agent findings that duplicate a deterministic finding (same domain+gap_type+title)
    are dropped in favor of the deterministic version, which has higher evidence level.
    Agent findings with the same domain+gap_type but different titles are kept —
    they describe distinct gaps.
    """
    deterministic_keys = {(f.domain, f.gap_type, f.title) for f in deterministic}
    merged = list(deterministic)
    for f in agent:
        if (f.domain, f.gap_type, f.title) not in deterministic_keys:
            merged.append(f)
    return merged
