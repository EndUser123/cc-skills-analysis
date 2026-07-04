"""Adapter bridging /gto's deterministic detectors into /debrief.

Debrief gains gto's session-goal/outcome detection, carryover+resolution
registry, leverage scoring, and gap-to-skill routing behind the
``--gto-detectors`` flag. gto stays the source of truth for these modules;
debrief imports them lazily (in-function) so the base ``run`` path stays
import-free and never breaks if gto is absent or restructured.

Finding-model boundary: gto's ``Finding`` (skills/gto/models.py) and
debrief's ``Finding`` are different dataclasses. gto Findings live only
inside this module; the adapter converts to debrief's
``{symptom_text, symptom_source}`` shape at the boundary so debrief's
state machine stays the single source of truth.

Cross-package note: do NOT import from ``skills.gto.orchestrator`` — it
imports ``session_registry`` from the snapshot plugin (cross-package).
Only the self-contained ``skills.gto.__lib`` modules are imported here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Plugin root = skills/debrief/__lib/gto_adapter.py -> parents[3].
# gto's modules use absolute imports (`from skills.gto...`), which require
# the plugin root on sys.path. debrief.py only inserts its own __lib, so
# the adapter self-locates and inserts the plugin root before importing gto.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[3])


def _import_gto():
    """Lazy import of the gto __lib modules + Finding model.

    Importing gto is the one coupling point; kept lazy so debrief's base
    path never pays the cost. Raises ImportError with a clear message if
    gto is absent — callers should treat --gto-detectors as unavailable.
    """
    if _PLUGIN_ROOT not in sys.path:
        sys.path.insert(0, _PLUGIN_ROOT)
    from skills.gto.__lib import (
        session_goal_detector,
        session_outcome_detector,
        completion_checker,
        carryover,
        resolve,
        scoring,
        route,
        dedupe,
    )
    from skills.gto.__lib.session_outcome_detector import SessionOutcomeResult
    from skills.gto.models import Finding, EvidenceRef
    return {
        "session_goal_detector": session_goal_detector,
        "session_outcome_detector": session_outcome_detector,
        "completion_checker": completion_checker,
        "carryover": carryover,
        "resolve": resolve,
        "scoring": scoring,
        "route": route,
        "dedupe": dedupe,
        "SessionOutcomeResult": SessionOutcomeResult,
        "Finding": Finding,
        "EvidenceRef": EvidenceRef,
    }


def _outcome_to_findings(
    outcome_result: Any,
    gto: dict,
    terminal_id: str,
    session_id: str,
    git_sha: str | None,
) -> list:
    """Convert SessionOutcomeResult items to gto Findings.

    Inlined (rather than imported from orchestrator._convert_outcome_findings)
    to avoid pulling orchestrator's cross-package session_registry import.
    Mirrors skills/gto/orchestrator.py:324-380.
    """
    Finding = gto["Finding"]
    EvidenceRef = gto["EvidenceRef"]
    findings = []
    items = getattr(outcome_result, "items", []) or []
    category_domain_map = {
        "uncompleted_goal": "session",
        "identified_task": "session",
        "open_question": "session",
        "deferred_item": "session",
    }
    category_severity_map = {
        "uncompleted_goal": "medium",
        "identified_task": "medium",
        "open_question": "low",
        "deferred_item": "low",
    }
    for idx, item in enumerate(items):
        category = getattr(item, "category", "identified_task")
        content = getattr(item, "content", "")
        confidence = getattr(item, "confidence", 0.5)
        recurrence = getattr(item, "recurrence_count", 1)
        acknowledged = getattr(item, "acknowledged", False)
        severity = "high" if recurrence >= 2 else category_severity_map.get(category, "low")
        findings.append(
            Finding(
                id=f"SESSION-{category[:4].upper()}-{idx + 1:03d}",
                title=content[:120],
                description=f"Session outcome: {category} (recurrence={recurrence}, acknowledged={acknowledged})",
                source_type="detector",
                source_name="session_outcome_detector",
                domain=category_domain_map.get(category, "session"),
                gap_type=f"session_{category}",
                severity=severity,
                evidence_level="verified" if confidence >= 0.7 else "unverified",
                action="recover",
                priority=severity,
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[EvidenceRef(kind="session_outcome", value=category,
                                      detail=f"confidence={confidence}")],
            )
        )
    return findings


def run_gto_detectors(
    transcript_path: str | Path,
    session_id: str,
    artifacts_dir: str | Path,
    root: str | Path | None = None,
    terminal_id: str = "debrief",
) -> list:
    """Run gto's deterministic detectors on a JSONL transcript.

    Returns scored + owner-routed gto Findings. Mirrors the detector +
    carryover + resolution + route + score sequence from
    skills/gto/orchestrator.py (Phases 1.7-1.10, 2-4, 8) but skips
    gto-specific detritus (impact_radius, cluster, branch, changelog,
    friction, stale-docs, verification-debt, hook-health) which are not
    detector-shaped or are git-dependent.

    ``artifacts_dir`` is debrief's per-session artifact directory; gto's
    carryover.json is written there as a sibling of dream-state.json.
    """
    gto = _import_gto()
    transcript_path = Path(transcript_path)
    root = Path(root) if root else Path.cwd()
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    git_sha = None
    try:
        from skills.gto.__lib.context import get_git_sha
        git_sha = get_git_sha(root)
    except Exception:
        git_sha = None

    # Phase 1.8: goal detection (single-transcript form; chain form not needed
    # — debrief handles multi-session chains natively via chain_*.md).
    goal_result = None
    try:
        goal_result = gto["session_goal_detector"].SessionGoalDetector(root).detect_goal(transcript_path)
    except Exception:
        goal_result = None

    # Phase 1.9: outcome detection -> findings
    outcome_detector = gto["session_outcome_detector"].SessionOutcomeDetector(root)
    outcome_result = outcome_detector.detect(transcript_path, terminal_id)
    session_findings = _outcome_to_findings(
        outcome_result, gto, terminal_id, session_id, git_sha)

    # Phase 1.10: filter outcomes actually completed during the session
    if getattr(outcome_result, "items", None) and transcript_path.exists():
        try:
            filtered_items = gto["completion_checker"].check_completions(
                transcript_path, outcome_result.items)
            if len(filtered_items) < len(outcome_result.items):
                filtered_result = gto["SessionOutcomeResult"](
                    items=filtered_items, total_count=len(filtered_items))
                session_findings = _outcome_to_findings(
                    filtered_result, gto, terminal_id, session_id, git_sha)
        except Exception:
            pass

    findings = list(session_findings)

    # Phase 2: carryover (open only) + enrichment, drop superseded
    current_ids = {f.id for f in findings}
    try:
        carried = gto["carryover"].load_carryover_open_only(artifacts_dir)
        if carried:
            carried = gto["carryover"].apply_carryover_enrichment(carried, [])
            carried = [f for f in carried if f.id not in current_ids]
            findings.extend(carried)
    except Exception:
        pass

    # Phase 3: dedupe
    findings = gto["dedupe"].dedupe_findings(findings)

    # Phase 4: resolve against session-edited files + registry strategies
    try:
        resolve_ctx = gto["resolve"].ResolveCtx(
            edited_file_set=set(),
            root=root,
            transcript_explicit=True,
            session_id=session_id,
        )
        findings = gto["resolve"].resolve_findings(findings, resolve_ctx)
    except Exception:
        pass

    # Phase 8 prep: carryover includes resolved (for cross-run dedup); save before filtering
    carryover_findings = list(findings)

    # Post-processing: route -> score (skip gto-specific impact/cluster/branch)
    findings = gto["route"].route_findings(findings)
    findings = gto["scoring"].score_findings(findings)

    # Phase 8: persist carryover for future runs
    try:
        gto["carryover"].save_carryover(artifacts_dir, carryover_findings)
        gto["carryover"].prune_carryover(artifacts_dir)
    except Exception:
        pass

    return findings


def gto_findings_to_debrief(gto_findings: list) -> list[dict]:
    """Convert gto Findings to debrief's {symptom_text, symptom_source} shape.

    Output is consumed by ``debrief.py run --findings`` (the dedup JSON
    seam at scripts/debrief.py:184-194). Open findings only — resolved
    findings have no symptom to chase.
    """
    out: list[dict] = []
    for f in gto_findings:
        status = getattr(f, "status", "open")
        if status in {"resolved", "rejected", "mapped"}:
            continue
        title = getattr(f, "title", "") or ""
        desc = getattr(f, "description", "") or ""
        symptom_text = f"{title} — {desc}".strip(" —") or f.id
        # source: prefer first evidence value, then file, then source_name:id
        source = ""
        evidence = getattr(f, "evidence", []) or []
        if evidence:
            source = getattr(evidence[0], "value", "") or str(evidence[0])
        if not source:
            source = getattr(f, "file", "") or f"{getattr(f, 'source_name', 'gto')}:{f.id}"
        score = getattr(f, "metadata", {}).get("score")
        out.append({
            "symptom_text": symptom_text,
            "symptom_source": source,
            "gto_id": f.id,
            "gto_score": score,
            "gto_owner_skill": getattr(f, "owner_skill", None),
            "gto_severity": getattr(f, "severity", None),
            "gto_gap_type": getattr(f, "gap_type", None),
        })
    return out


def write_gap_review_handoff(
    artifacts_dir: str | Path,
    gto_findings: list,
    session_context: dict | None = None,
) -> Path:
    """Write the gap_reviewer agent handoff (gto's write_handoff wrapper).

    The gap_reviewer is an LLM agent, not a Python detector: this writes the
    context-enriched handoff; the /debrief-running LLM dispatches the agent
    (Agent tool + GAP_REVIEW_SYSTEM), which writes
    ``gap_reviewer_result.json``; a re-run of ``debrief.py run --gap-review``
    then picks it up via ``read_gap_review_debrief``.
    """
    _import_gto()  # ensure skills.gto package resolves before sub-import
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = artifacts_dir / "gap_reviewer_handoff.json"
    from skills.gto.agents.gap_reviewer import write_handoff
    write_handoff(
        handoff_path,
        gto_findings,
        session_context=session_context or {},
        detectors_ran=["session_goal_detector", "session_outcome_detector",
                       "completion_checker"],
    )
    return handoff_path


def read_gap_review_debrief(artifacts_dir: str | Path) -> list[dict]:
    """Read gap_reviewer_result.json + convert to debrief shape.

    Returns [] if no result file exists yet (first pass: handoff just
    written, agent not yet dispatched).
    """
    from skills.gto.agents.gap_reviewer import read_result
    result_path = Path(artifacts_dir) / "gap_reviewer_result.json"
    agent_result = read_result(result_path)
    if not getattr(agent_result, "success", False):
        return []
    return gto_findings_to_debrief(agent_result.findings)


def attach_score_and_owner(debrief_tasks: list[dict], debrief_findings: list[dict]) -> list[dict]:
    """Stamp gto score + owner_skill into WRITTEN debrief task bodies.

    ``debrief_findings`` is the output of ``gto_findings_to_debrief`` (the
    adapter side, carrying gto_id/score/owner). ``debrief_tasks`` is the
    ``written`` list from ``debrief_core.run()``. Match by symptom_text
    substring (the task body embeds the symptom text).
    """
    by_text = {}
    for f in debrief_findings:
        text = f.get("symptom_text", "")
        if text:
            by_text[text] = f
    for task in debrief_tasks:
        body = task.get("body", "") or task.get("description", "") or ""
        matched = None
        for text, f in by_text.items():
            if text and text in body:
                matched = f
                break
        if matched:
            score = matched.get("gto_score")
            owner = matched.get("gto_owner_skill")
            extra = []
            if score is not None:
                extra.append(f"gto_score: {score}")
            if owner:
                extra.append(f"owner_skill: {owner}")
            if extra and body:
                tag = f"\n[gto] {' | '.join(extra)}"
                if tag not in body:
                    task["body"] = body + tag
    return debrief_tasks


if __name__ == "__main__":
    import json
    import sys

    class _Self:
        """ponytail: minimal smoke — proves imports resolve + a synthetic
        run produces debrief-shaped findings. Real coverage in test suite."""

    if len(sys.argv) < 2:
        print("usage: gto_adapter.py <transcript.jsonl> [session_id] [artifacts_dir]",
              file=sys.stderr)
        sys.exit(2)
    tp = sys.argv[1]
    sid = sys.argv[2] if len(sys.argv) > 2 else "selfcheck"
    adir = sys.argv[3] if len(sys.argv) > 3 else "."
    findings = run_gto_detectors(tp, sid, adir)
    debrief_shaped = gto_findings_to_debrief(findings)
    print(json.dumps({
        "gto_findings": len(findings),
        "debrief_shaped": len(debrief_shaped),
        "sample": debrief_shaped[:2],
    }, indent=2))
