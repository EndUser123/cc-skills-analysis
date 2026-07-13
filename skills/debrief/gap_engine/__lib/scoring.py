"""Leverage scoring for findings — ICE-style value-per-effort ranking.

The orchestrator previously ordered findings by severity alone, which buries a
cheap high-impact fix beneath an expensive critical one and ignores the effort
and confidence GAP already collects. This module computes a single composite
`score` per finding so ordering and triage reflect *leverage* (value ÷ effort),
not just severity.

Score = (severity_w × action_w × confidence_w × impact_factor) / effort_cost

Every weight is justified inline — no bare constants. The score is written to
`finding.metadata["score"]` (and a `score_components` breakdown) so it is
additive to the existing schema and never mutates a typed field.
"""
from __future__ import annotations

import re
from dataclasses import replace

from ..models import Finding

# Severity weight: linear, one step apart. Mirrors the inverse of
# dependency_order.SEVERITY_RANK so a critical is 4x a low.
SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}
DEFAULT_SEVERITY_WEIGHT = 2.0  # unknown severity treated as medium

# Action weight: recover (active breakage / regression — fix now) outranks
# prevent (stop future breakage) outranks realize (opportunity). Matches the
# existing ACTION_ORDER in machine_render.
ACTION_WEIGHT: dict[str, float] = {
    "recover": 3.0,
    "prevent": 2.0,
    "realize": 1.0,
}
DEFAULT_ACTION_WEIGHT = 1.0

# Confidence weight: discount unproven claims so a verified medium can outrank
# an unverified high. derived = produced by a deterministic transform of
# evidence (e.g. clustering), trusted more than a raw LLM inference.
CONFIDENCE_WEIGHT: dict[str, float] = {
    "verified": 1.0,
    "derived": 0.7,
    "unverified": 0.4,
}
DEFAULT_CONFIDENCE_WEIGHT = 0.4  # unknown evidence level = treat as unverified

# Impact factor band: a finding's blast radius matters but must not swamp
# severity. We map radius 0..CAP onto a 1.0..2.0 multiplier — a maximally
# referenced file doubles the score, no more.
IMPACT_RADIUS_CAP = 20

# Effort floor: a 5-minute task should rank high but not divide the score to
# infinity. Hours below this are clamped.
MIN_EFFORT_HOURS = 0.1
DEFAULT_EFFORT_HOURS = 1.0  # missing/"unknown" effort = one hour (neutral)

# Maps an effort unit token to hours. A working day = 8h.
_UNIT_HOURS: dict[str, float] = {
    "min": 1.0 / 60.0,
    "m": 1.0 / 60.0,
    "h": 1.0,
    "hr": 1.0,
    "hrs": 1.0,
    "hour": 1.0,
    "hours": 1.0,
    "d": 8.0,
    "day": 8.0,
    "days": 8.0,
}
_EFFORT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([a-z]+)")


def parse_effort_hours(effort: str | None) -> float:
    """Parse a freeform effort string ('~5min', '2h', '1 day') into hours.

    Returns DEFAULT_EFFORT_HOURS for empty/'unknown'/unparseable input, and
    never returns less than MIN_EFFORT_HOURS.
    """
    if not effort:
        return DEFAULT_EFFORT_HOURS
    text = effort.strip().lower()
    if not text or text == "unknown":
        return DEFAULT_EFFORT_HOURS
    match = _EFFORT_RE.search(text)
    if not match:
        return DEFAULT_EFFORT_HOURS
    value = float(match.group(1))
    unit = match.group(2)
    hours = value * _UNIT_HOURS.get(unit, 1.0)
    return max(hours, MIN_EFFORT_HOURS)


def _impact_factor(finding: Finding) -> float:
    """Map impact_radius (from impact_radius enrichment) to a 1.0..2.0 band."""
    radius = finding.metadata.get("impact_radius", 0)
    try:
        radius = int(radius)
    except (TypeError, ValueError):
        radius = 0
    if radius <= 0:
        return 1.0
    return 1.0 + min(radius, IMPACT_RADIUS_CAP) / IMPACT_RADIUS_CAP


def compute_score(finding: Finding) -> tuple[float, dict[str, float]]:
    """Compute the leverage score and its component breakdown for a finding."""
    severity_w = SEVERITY_WEIGHT.get(finding.severity, DEFAULT_SEVERITY_WEIGHT)
    action_w = ACTION_WEIGHT.get(finding.action, DEFAULT_ACTION_WEIGHT)
    confidence_w = CONFIDENCE_WEIGHT.get(finding.evidence_level, DEFAULT_CONFIDENCE_WEIGHT)
    impact_f = _impact_factor(finding)
    effort_cost = parse_effort_hours(finding.effort)

    value = severity_w * action_w * confidence_w * impact_f
    score = value / effort_cost

    components = {
        "severity_w": severity_w,
        "action_w": action_w,
        "confidence_w": confidence_w,
        "impact_factor": round(impact_f, 3),
        "effort_hours": round(effort_cost, 3),
        "value": round(value, 3),
    }
    return round(score, 4), components


def score_findings(findings: list[Finding]) -> list[Finding]:
    """Annotate each finding with metadata['score'] and ['score_components'].

    Returns new Finding instances (metadata replaced); input is not mutated.
    Resolved findings are scored too so trend math stays consistent, but their
    score is irrelevant to ordering (they are filtered before display).
    """
    scored: list[Finding] = []
    for f in findings:
        score, components = compute_score(f)
        new_meta = {**f.metadata, "score": score, "score_components": components}
        scored.append(replace(f, metadata=new_meta))
    return scored


def get_score(finding: Finding) -> float:
    """Read a finding's computed score, or 0.0 if it was never scored."""
    raw = finding.metadata.get("score", 0.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
