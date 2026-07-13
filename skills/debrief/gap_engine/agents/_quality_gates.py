"""Quality gates for gap reviewer findings — deterministic enforcement of reasoning patterns.

These gates run inside read_result() after findings are parsed but before they are
returned to the orchestrator for merging. Each gate is surgical: it annotates or
filters findings without changing the orchestrator's merge logic.
"""
from __future__ import annotations

import re
from typing import Any

from ..models import Finding


# ---- Gate A: No soft escape hatches ----

SOFT_ESCAPE_PATTERNS = [
    re.compile(r"\boptionally\b", re.IGNORECASE),
    re.compile(r"\bif\s+low\s+risk\b", re.IGNORECASE),
    re.compile(r"\bif\s+feasible\b", re.IGNORECASE),
    re.compile(r"\bmaybe\b", re.IGNORECASE),
    re.compile(r"\bperhaps\b", re.IGNORECASE),
    re.compile(r"\bdefer\b", re.IGNORECASE),
    re.compile(r"\bpostpone\b", re.IGNORECASE),
    re.compile(r"\bwe\s+can\s+(add|do)\s+later\b", re.IGNORECASE),
    re.compile(r"\boptional\b", re.IGNORECASE),
    re.compile(r"\buntil\s+necessary\b", re.IGNORECASE),
]

EFFORT_UNSPECIFIED = {"unspecified", "unknown", "tbd", "none", ""}


def validate_escape_hatches(findings: list[Finding]) -> list[Finding]:
    """Reject or down-rank findings with soft escape hatches.

    Escape hatch = action is effectively defer/none, OR effort is missing/unspecified
    on non-trivial severity without a concrete follow-up condition in metadata.

    Rule: reject findings where:
      - action is "defer" or "none" and no followup_condition in metadata
      - effort is missing/unspecified AND severity is high/critical

    Annotate (down-rank, don't reject) when:
      - effort is missing/unspecified AND severity is medium, AND description
        contains soft escape language (optionally, if low risk, etc.)
    """
    validated = []
    for f in findings:
        action = (f.action or "").lower().strip()
        effort = (f.effort or "").lower().strip()
        severity = (f.severity or "").lower().strip()
        has_followup = bool(f.metadata.get("followup_condition"))
        has_soft_language = any(p.search(f.description or "") for p in SOFT_ESCAPE_PATTERNS)

        # Reject: defer action without concrete follow-up condition
        if action in ("defer", "none", "skip", "later"):
            if not has_followup:
                # Down-grade to low-priority, mark as escape hatch
                f.severity = "low"
                f.priority = "low"
                f.metadata["escape_hatch"] = True
                f.metadata["escape_hatch_reason"] = f"action='{action}' without followup_condition"
                validated.append(f)
                continue
            # defer WITH followup_condition is justified — skip remaining checks
            validated.append(f)
            continue

        # Reject: high/critical severity with missing effort
        if severity in ("critical", "high") and effort in EFFORT_UNSPECIFIED:
            f.metadata["escape_hatch"] = True
            f.metadata["escape_hatch_reason"] = f"severity={severity} with missing effort"
            validated.append(f)
            continue

        # Down-rank: medium severity, missing effort, soft language present
        if severity == "medium" and effort in EFFORT_UNSPECIFIED and has_soft_language:
            f.priority = "low"
            f.metadata["escape_hatch"] = True
            f.metadata["escape_hatch_reason"] = "medium severity, unspecified effort, soft language"
            validated.append(f)
            continue

        validated.append(f)

    return validated


# ---- Gate B: Structured evidence requirements ----

CONCRETE_DETECTOR_KINDS = {"path", "pattern", "behavior", "artifact", "file", "line", "detector"}
HOOK_TELEMETRY_KEYWORDS = {"hook", "telemetry", "stop", "pretooluse", "posttooluse", "sessionstart"}


def validate_evidence_structure(findings: list[Finding]) -> list[Finding]:
    """Enforce structured evidence on gap reviewer findings.

    Rules:
    - Each EvidenceRef must have kind and value (non-empty strings).
    - If finding has unverified=True, metadata must contain verification_gap
      describing the missing verification step.
    - If description references hook/telemetry mechanism without evidence
      pointing at a file path or detector, mark as unverified_implementation_claim.
    """
    validated = []
    for f in findings:
        # Check each evidence ref has structure
        needs_verification_gap = f.unverified

        # Check for hook/telemetry references in description without concrete evidence
        desc_lower = (f.description or "").lower()
        refs_hooks = any(kw in desc_lower for kw in HOOK_TELEMETRY_KEYWORDS)

        if refs_hooks:
            # Check if any evidence points at a concrete path/file
            has_concrete_evidence = any(
                ev.kind in CONCRETE_DETECTOR_KINDS and ev.value
                for ev in f.evidence
            )
            if not has_concrete_evidence:
                # This is an unverified implementation claim
                f.unverified = True
                f.metadata["unverified_implementation_claim"] = True
                f.metadata["unverified_implementation_claim_reason"] = (
                    "description references hook/telemetry but no evidence points at concrete path"
                )
                needs_verification_gap = True

        # Enforce verification_gap on unverified findings
        if needs_verification_gap and not f.metadata.get("verification_gap"):
            # Down-rank severity if missing verification_gap on unverified
            if f.severity in ("critical", "high"):
                f.severity = "medium"
                f.priority = "medium"
            f.metadata["verification_gap_missing"] = True

        validated.append(f)

    return validated


# ---- Gate C: Respect absence signals ----

# Map absent detector -> what it would have found if the gap existed
ABSENCE_GAP_RULES: dict[str, tuple[str, list[str], str]] = {
    # (domain, conflicting_gap_types, downrank_to)
    "verification_debt_detector": ("quality", ["missingtests", "test_coverage"], "low"),
    "workflow_hygiene_detector": ("quality", ["uncommitted_changes", "hygiene"], "low"),
    "hook_health_detector": ("quality", ["hook_error", "hook_failure"], "medium"),
    "stuckness_detector": ("session", ["stuckness", "loop"], "low"),
    "context_boundary_detector": ("session", ["context_switch", "boundary"], "low"),
    "session_goal_detector": ("session", ["uncompleted_goal", "deferred_goal"], "low"),
}


def validate_absence_signal_respect(
    findings: list[Finding],
    signals_absent: list[str],
    detectors_ran: list[str],
) -> list[Finding]:
    """Prevent gap reviewer from confidently asserting gaps that contradict absent detectors.

    If a detector ran (detectors_ran) and appears in signals_absent, the gap reviewer
    should not produce a high-confidence finding in a conflicting domain without
    explicitly acknowledging the absence and explaining why it doesn't apply.

    Rule: For each finding, if its domain/gap_type conflicts with an absent detector,
    the finding must:
      - Have confidence lower than "high" in metadata (explicit acknowledgment)
      - OR have metadata.absent_signal_explained = True explaining why the gap still applies

    Otherwise: down-rank to the severity specified in ABSENCE_GAP_RULES.
    """
    if not signals_absent:
        return findings

    validated = []
    for f in findings:
        domain = (f.domain or "").lower().strip()
        gap_type = (f.gap_type or "").lower().strip()
        severity = (f.severity or "").lower().strip()

        conflicting_detector = None
        for det, (dom, conflict_types, default_severity) in ABSENCE_GAP_RULES.items():
            if det in signals_absent and domain == dom and any(ct in gap_type for ct in conflict_types):
                conflicting_detector = det
                break

        if conflicting_detector is None:
            validated.append(f)
            continue

        # Detector was absent — check if the finding acknowledges it
        if f.metadata.get("absent_signal_explained") is True:
            # LLM explicitly explained why the gap still applies despite absence
            validated.append(f)
            continue

        # Otherwise: down-rank if severity is high/critical without explanation
        if severity in ("critical", "high"):
            downrank_severity = ABSENCE_GAP_RULES[conflicting_detector][2]
            f.priority = downrank_severity
            f.metadata["downgraded_absent_signal"] = True
            f.metadata["conflicting_absent_detector"] = conflicting_detector
            f.metadata["downgrade_reason"] = (
                f"gap_type={gap_type} contradicts absent detector={conflicting_detector} "
                f"without explicit acknowledgment"
            )

        validated.append(f)

    return validated


# ---- Gate D: Mixed-substance detection for unverified findings ----

CONCRETE_MARKERS = [
    re.compile(r"\bfile[:\s/\\]"),
    re.compile(r"\bline\s+\d+", re.IGNORECASE),
    re.compile(r"\bfunction\s+\w+"),
    re.compile(r"\bclass\s+\w+"),
    re.compile(r"\bmodule\s+\w+"),
    re.compile(r"\bat\s+\w+[:\d]+"),
    re.compile(r"\bpath[:\s/\\]"),
]

HEDGING_TERMS = [
    re.compile(r"\bmight\b", re.IGNORECASE),
    re.compile(r"\bcould\b", re.IGNORECASE),
    re.compile(r"\bpossibly\b", re.IGNORECASE),
    re.compile(r"\bmay\b", re.IGNORECASE),
    re.compile(r"\bprobably\b", re.IGNORECASE),
    re.compile(r"\bseems?\b", re.IGNORECASE),
    re.compile(r"\bappears?\b", re.IGNORECASE),
    re.compile(r"\blooks?\s+like\b", re.IGNORECASE),
    re.compile(r"\bunclear\b", re.IGNORECASE),
    re.compile(r"\buncertain\b", re.IGNORECASE),
    re.compile(r"\bambiguous\b", re.IGNORECASE),
]


def validate_mixed_substance_unverified(findings: list[Finding]) -> list[Finding]:
    """Detect "mixed substance" unverified findings.

    Mixed substance = description mixes concrete markers (file:, line 42, function X)
    with hedging terms (might, could, unclear) without a clear verification_gap.

    Such findings are prone to over-trust: they look concrete but are logically
    speculative. They must either:
      - Include a clear verification_gap in metadata, OR
      - Be marked with metadata.mixed_substance=True and down-ranked

    Rule: if finding.unverified AND has_concrete_markers AND has_hedging_terms
    AND no verification_gap -> annotate mixed_substance=True and down-rank priority.
    """
    validated = []
    for f in findings:
        if not f.unverified:
            validated.append(f)
            continue

        desc = f.description or ""
        has_concrete = any(p.search(desc) for p in CONCRETE_MARKERS)
        has_hedging = any(p.search(desc) for p in HEDGING_TERMS)
        has_verification_gap = bool(f.metadata.get("verification_gap"))

        if has_concrete and has_hedging and not has_verification_gap:
            f.metadata["mixed_substance"] = True
            f.metadata["mixed_substance_reason"] = (
                "unverified finding with concrete markers AND hedging terms "
                "without explicit verification_gap"
            )
            # Down-rank to low priority — concrete appearance masks speculative content
            if f.severity in ("critical", "high"):
                f.severity = "medium"
                f.priority = "medium"
            elif f.priority not in ("critical", "high"):
                f.priority = "low"

        validated.append(f)

    return validated


# ---- Orchestrate all gates ----

def apply_quality_gates(
    findings: list[Finding],
    signals_absent: list[str] | None = None,
    detectors_ran: list[str] | None = None,
) -> list[Finding]:
    """Apply all four quality gates in sequence.

    Order: escape_hatches → evidence_structure → absence_signal_respect → mixed_substance

    This is the single entry point called from gap_reviewer.read_result() after
    findings are parsed and before they are returned to the orchestrator.
    """
    result = validate_escape_hatches(findings)
    result = validate_evidence_structure(result)
    result = validate_absence_signal_respect(result, signals_absent or [], detectors_ran or [])
    result = validate_mixed_substance_unverified(result)
    return result