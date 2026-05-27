#!/usr/bin/env python3
"""GTO Orchestrator — main entry point for session-aware gap analysis.

Usage:
    python orchestrator.py [options]

Runs deterministic detectors, session transcript analysis, carryover resolution,
and produces RNS-compatible machine output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


from .models import GTOArtifact, Finding, EvidenceRef
from .settings import GTOSettings
from .__lib.context import get_git_sha
from .__lib.detectors import run_basic_detectors
from .__lib.carryover import load_carryover_open_only, save_carryover, prune_carryover, apply_carryover_enrichment
from .__lib.resolve import resolve_findings
from .__lib.session_goal_detector import SessionGoalDetector
from .__lib.session_outcome_detector import SessionOutcomeDetector, SessionOutcomeResult
from .__lib.transcript import read_turns, extract_edited_files
from .__lib.docs_followup import detect_docs_followup
from .__lib.normalize import normalize_findings
from .__lib.dedupe import dedupe_findings
from .__lib.merge import merge_findings
from .__lib.route import route_findings
from .__lib.dependency_order import order_findings
from .__lib.freshness import classify_freshness
from .__lib.targeting import resolve_target
from .__lib.coverage import compute_coverage, compute_health_score
from .__lib.evidence import write_artifact
from .__lib.state import RunState, load_state, save_state, sync_to_execution_state
from .__lib.verify import verify_artifact
from .__lib.changelog import detect_changelog_findings
from .__lib.invocation_tracker import check_invocations
from .__lib.clustering import cluster_findings
from .__lib.context_boundaries import context_boundary_findings
from .__lib.impact_radius import enrich_with_impact_radius
from .__lib.branch_awareness import adjust_for_branch
from .__lib.stuckness import detect_stuckness
from .__lib.hook_health import detect_hook_errors
from .__lib.workflow_hygiene import detect_workflow_hygiene
from .__lib.verification_debt import detect_verification_debt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GTO Gap Analysis Orchestrator")
    parser.add_argument("--target", help="Target directory or project to analyze")
    parser.add_argument("--terminal-id", default="default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--merge-only", action="store_true", help="Skip detectors, only merge agent results into existing artifact")
    return parser.parse_args(argv)


def _resolve_session_id_from_identity(terminal_id: str) -> str:
    """Extract session_id from identity.json when CLI arg is empty."""
    artifacts_root = Path(os.environ.get("CLAUDE_ARTIFACTS_ROOT", "P:\\\\\\.claude/.artifacts"))
    identity_file = artifacts_root / terminal_id / "identity.json"
    if not identity_file.exists():
        return ""
    try:
        data = json.loads(identity_file.read_text(encoding="utf-8"))
        return data.get("claude", {}).get("session_id", "")
    except (json.JSONDecodeError, OSError):
        return ""


def _resolve_transcript_from_identity(terminal_id: str) -> Path | None:
    """Resolve transcript path from identity.json (hook-captured, no scanning)."""
    artifacts_root = Path(os.environ.get("CLAUDE_ARTIFACTS_ROOT", "P:\\\\\\.claude/.artifacts"))
    identity_file = artifacts_root / terminal_id / "identity.json"
    if not identity_file.exists():
        return None
    try:
        data = json.loads(identity_file.read_text(encoding="utf-8"))
        tp = data.get("claude", {}).get("transcript_path", "")
        if tp and Path(tp).exists():
            return Path(tp)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _load_session_chain(terminal_id: str) -> list[str]:
    """Load session transcript paths from session registry for this terminal."""
    registry_path = Path("P:\\\\\\.claude/.artifacts/session_registry.jsonl")
    if not registry_path.exists():
        return []
    try:
        import sys as _sys
        sys.path.insert(0, "P:\\\\\\packages/snapshot/scripts/hooks/__lib")
        from session_registry import query_registry
    except ImportError:
        return []
    entries = query_registry(terminal_id=terminal_id, limit=20)
    # Deduplicate by session_id, keep most recent per session, oldest-first order
    seen: set[str] = set()
    result: list[str] = []
    for e in reversed(entries):
        sid = e.get("session_id", "")
        tp = e.get("transcript_path", "")
        if sid and sid not in seen and tp and Path(tp).exists():
            seen.add(sid)
            result.append(tp)
    return list(reversed(result))


def _convert_outcome_findings(
    outcome_result: object,
    terminal_id: str,
    session_id: str,
    git_sha: str | None,
) -> list[Finding]:
    """Convert SessionOutcomeResult items to GTO Finding objects."""
    findings: list[Finding] = []
    items = getattr(outcome_result, "items", [])
    if not items:
        return findings

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
                evidence=[
                    EvidenceRef(kind="session_outcome", value=category, detail=f"confidence={confidence}"),
                ],
            )
        )

    return findings


def _extract_context(
    transcript_path: Path | None,
    items: list[object],
    window: int = 5,
) -> list[dict[str, str]]:
    """Extract transcript turns surrounding each outcome item for LLM review."""
    if not transcript_path or not transcript_path.exists() or not items:
        return []
    turns = read_turns(transcript_path)
    if not turns:
        return []
    excerpts: list[dict[str, str]] = []
    for item in items:
        turn_num = getattr(item, "turn_number", 0)
        if turn_num <= 0:
            continue
        idx = turn_num - 1
        start = max(0, idx - window)
        end = min(len(turns), idx + window + 1)
        for t in turns[start:end]:
            excerpts.append({"role": t.role, "content": t.content})
    return excerpts


def _run_merge_only(
    args: argparse.Namespace,
    settings: GTOSettings,
    paths: object,
    state: RunState,
    state_file: Path,
) -> int:
    """Merge agent results into existing artifact without re-running detectors."""
    artifact_path = paths.outputs_dir / "artifact.json"
    if not artifact_path.exists():
        print("GTO merge-only: no existing artifact, aborting", file=sys.stderr)
        return 1

    # Load existing findings from artifact
    raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    all_findings = [Finding.from_dict(f) for f in raw.get("findings", [])]

    # Merge agent results (same logic as full run, lines 381-409)
    from .agents.domain_analyzer import read_result as read_domain
    from .agents.findings_reviewer import read_result as read_reviewer, read_verdicts
    from .agents.action_normalizer import read_result as read_normalizer
    from .agents.gap_reviewer import read_result as read_gap

    domain_result = read_domain(paths.artifacts_dir / "domain_analyzer_result.json")
    if domain_result.success and domain_result.findings:
        all_findings.extend(domain_result.findings)
        all_findings = dedupe_findings(all_findings)

    rejected_ids, _ = read_verdicts(paths.artifacts_dir / "findings_reviewer_result.json")
    if rejected_ids:
        all_findings = [f for f in all_findings if f.id not in rejected_ids]

    normalizer_result = read_normalizer(paths.artifacts_dir / "action_normalizer_result.json")
    if normalizer_result.success and normalizer_result.findings:
        normalized_ids = {f.id for f in normalizer_result.findings}
        all_findings = [f for f in all_findings if f.id not in normalized_ids]
        all_findings.extend(normalizer_result.findings)

    gap_result = read_gap(paths.artifacts_dir / "gap_reviewer_result.json")
    if gap_result.success and gap_result.findings:
        gap_ids = {f.id for f in gap_result.findings}
        all_findings = [f for f in all_findings if f.id not in gap_ids]
        all_findings.extend(gap_result.findings)

    # Post-processing pipeline
    all_findings = route_findings(all_findings)
    all_findings = order_findings(all_findings)
    all_findings = enrich_with_impact_radius(settings.root, all_findings)
    all_findings = cluster_findings(all_findings)
    all_findings = adjust_for_branch(settings.root, all_findings)

    # Compute coverage + health
    coverage = compute_coverage(all_findings)
    freshness = classify_freshness(
        artifact_git_sha=state.git_sha,
        current_git_sha=settings.git_sha,
        artifact_target=state.current_target,
        current_target=state.current_target,
    )
    health = compute_health_score(all_findings, freshness)

    # Write artifact
    artifact = GTOArtifact.empty(
        mode="full",
        terminal_id=args.terminal_id,
        session_id=args.session_id,
        target=state.current_target,
        git_sha=settings.git_sha,
    )
    artifact.freshness = freshness
    artifact.coverage = coverage
    artifact.summary = {
        "total_findings": len(all_findings),
        "by_severity": coverage.get("by_severity", {}),
        "by_domain": coverage.get("by_domain", {}),
        "health": health,
    }
    write_artifact(artifact_path, artifact, all_findings)

    # Update state
    state.phase = "completed"
    state.verification_status = "pending"
    state.last_artifact = str(artifact_path)
    state.expected_artifacts = [str(artifact_path)]
    save_state(state_file, state)
    sync_to_execution_state(state, paths.artifacts_dir)

    verification = verify_artifact(artifact_path)
    state.verification_status = "pass" if verification["valid"] else "fail"
    save_state(state_file, state)
    sync_to_execution_state(state, paths.artifacts_dir)

    print(f"GTO merge-only: {len(all_findings)} findings", file=sys.stderr)
    return 0 if verification["valid"] else 1


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()

    # Resolve session_id: CLI arg → identity.json fallback
    if not args.session_id:
        args.session_id = _resolve_session_id_from_identity(args.terminal_id)

    settings = GTOSettings(
        terminal_id=args.terminal_id,
        session_id=args.session_id,
        git_sha=get_git_sha(root),
        root=root,
        mode="full",
    )

    paths = settings.paths
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.outputs_dir.mkdir(parents=True, exist_ok=True)

    # Initialize state
    state_file = paths.state_dir / "run_state.json"
    state = load_state(state_file)
    prev_git_sha = state.git_sha  # capture before overwrite
    state.run_id = f"{args.terminal_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    state.phase = "running"
    state.current_target = resolve_target(args.target, None, None)
    state.git_sha = settings.git_sha
    state.verification_required = True
    state.verification_status = "pending"
    save_state(state_file, state)
    sync_to_execution_state(state, paths.artifacts_dir)

    # Merge-only mode: skip all detectors, load from existing artifact + merge agent results
    if args.merge_only:
        return _run_merge_only(args, settings, paths, state, state_file)

    # Phase 1: Deterministic detectors
    findings = run_basic_detectors(root, args.terminal_id, args.session_id, settings.git_sha)

    # Phase 1.2: Marker staleness — detect stale session markers from prior runs
    from .__lib.detectors import detect_marker_staleness, detect_missing_verification_evidence
    marker_findings = detect_marker_staleness(root, args.terminal_id, args.session_id, settings.git_sha)
    findings.extend(marker_findings)

    # Phase 1.3: Missing verification evidence — detect findings citing hooks/telemetry without test coverage
    verification_findings = detect_missing_verification_evidence(root, args.terminal_id, args.session_id, settings.git_sha)
    findings.extend(verification_findings)

    # Phase 1.4: Changelog detection — files changed since previous GTO run
    changelog_findings = detect_changelog_findings(
        root, prev_git_sha, settings.git_sha,
        args.terminal_id, args.session_id, settings.git_sha,
    )
    findings.extend(changelog_findings)

    # Capture changed files for carryover decay check
    from .__lib.changelog import get_changed_files as _get_changed_files
    changed_files_for_decay = (
        _get_changed_files(root, prev_git_sha, settings.git_sha)
        if prev_git_sha and settings.git_sha and prev_git_sha != settings.git_sha
        else []
    )

    # Phase 1.5: Resolve transcript from identity.json (hook-captured, no scanning)
    transcript_path = _resolve_transcript_from_identity(args.terminal_id)

    # Phase 1.6: Extract files edited this session from transcript tool calls
    session_edited_files = extract_edited_files(transcript_path, root) if transcript_path else []

    # Phase 1.7: Build session chain from session registry
    chain = _load_session_chain(args.terminal_id)

    # Phase 1.8: Detect session goals from transcript chain
    goal_result = None
    if chain:
        goal_result = SessionGoalDetector(root).detect_goal_from_chain(chain)

    # Phase 1.9: Detect session outcomes (uncompleted goals, open questions, deferred items)
    outcome_detector = SessionOutcomeDetector(root)
    outcome_result = outcome_detector.detect(transcript_path, args.terminal_id)
    session_findings = _convert_outcome_findings(outcome_result, args.terminal_id, args.session_id, settings.git_sha)

    # Phase 1.10: Filter outcomes that were actually completed during the session
    if outcome_result.items and transcript_path:
        from .__lib.completion_checker import check_completions
        filtered_items = check_completions(transcript_path, outcome_result.items)
        if len(filtered_items) < len(outcome_result.items):
            filtered_result = SessionOutcomeResult(
                items=filtered_items, total_count=len(filtered_items)
            )
            session_findings = _convert_outcome_findings(
                filtered_result, args.terminal_id, args.session_id, settings.git_sha
            )
        # Write handoff for optional LLM review of remaining ambiguous items
        # Low-confidence deferred candidates (confidence < 0.5) are included
        # for the session reviewer subagent to classify as confirmed/rejected.
        if filtered_items:
            from .agents.session_reviewer import write_handoff
            write_handoff(
                paths.artifacts_dir / "session_reviewer_handoff.json",
                filtered_items,
                _extract_context(transcript_path, filtered_items),
            )

    findings.extend(session_findings)

    # Phase 1.12: Context boundary detection — context switches within this session
    boundary_findings = context_boundary_findings(
        transcript_path, args.terminal_id, args.session_id, settings.git_sha,
    )
    findings.extend(boundary_findings)

    # Phase 1.13: Skill invocation tracking — were previous recommendations actioned?
    invocation_findings = check_invocations(
        transcript_path, changelog_findings,
        args.terminal_id, args.session_id, settings.git_sha,
    )
    findings.extend(invocation_findings)

    # Phase 1.14: Hook health detection — hook execution errors from transcript
    hook_error_findings = detect_hook_errors(
        transcript_path, args.terminal_id, args.session_id, settings.git_sha,
    )
    findings.extend(hook_error_findings)

    # Phase 1.15: Workflow hygiene — uncommitted changes in working tree
    hygiene_findings = detect_workflow_hygiene(
        root, args.terminal_id, args.session_id, settings.git_sha,
    )
    findings.extend(hygiene_findings)

    # Phase 1.16: Verification debt — edits without test verification
    verification_findings = detect_verification_debt(
        transcript_path, args.terminal_id, args.session_id, settings.git_sha,
    )
    findings.extend(verification_findings)

    # Phase 1.11: Write agent handoffs for LLM enrichment
    if findings:
        project_context = {
            "root": str(root),
            "git_sha": settings.git_sha,
            "terminal_id": args.terminal_id,
            "has_readme": (root / "README.md").exists(),
            "has_git": (root / ".git").exists(),
        }
        from .agents.domain_analyzer import write_handoff as write_domain_handoff
        write_domain_handoff(
            paths.artifacts_dir / "domain_analyzer_handoff.json",
            findings,
            project_context,
        )

    # Phase 2: Load carryover (open only — resolved findings stay suppressed)
    carryover = load_carryover_open_only(paths.artifacts_dir)
    if carryover:
        # Apply escalation/decay based on carry count and file changes
        carryover = apply_carryover_enrichment(carryover, changed_files_for_decay)
        # Drop carryover findings superseded by a current-run finding with the same ID
        current_ids = {f.id for f in findings}
        carryover = [f for f in carryover if f.id not in current_ids]
        findings.extend(carryover)

    # Phase 4: Merge, normalize, dedupe, route, order
    all_findings = merge_findings(findings, [])
    all_findings = normalize_findings(all_findings)

    # Docs follow-up detection
    docs_findings = detect_docs_followup(root, all_findings)
    all_findings.extend(docs_findings)

    all_findings = dedupe_findings(all_findings)

    # Phase 4.5: Resolve findings based on session edits
    edited_file_set: set[str] = set()
    for fp in session_edited_files:
        try:
            edited_file_set.add(str(fp.relative_to(root)).replace("\\", "/"))
        except ValueError:
            edited_file_set.add(str(fp).replace("\\", "/"))
    all_findings = resolve_findings(all_findings, edited_file_set, root)

    # Split: display excludes resolved, carryover includes them
    carryover_findings = list(all_findings)
    all_findings = [f for f in all_findings if f.status != "resolved"]

    # Phase 4.7: Read agent enrichment results (written by LLM-spawned subagents)
    from .agents.domain_analyzer import read_result as read_domain
    from .agents.findings_reviewer import read_result as read_reviewer, read_verdicts
    from .agents.action_normalizer import read_result as read_normalizer

    domain_result = read_domain(paths.artifacts_dir / "domain_analyzer_result.json")
    if domain_result.success and domain_result.findings:
        all_findings.extend(domain_result.findings)
        all_findings = dedupe_findings(all_findings)

    # Apply findings reviewer verdicts (reject/keep) — verdicts format, not Finding-shaped
    rejected_ids, _ = read_verdicts(paths.artifacts_dir / "findings_reviewer_result.json")
    if rejected_ids:
        all_findings = [f for f in all_findings if f.id not in rejected_ids]

    normalizer_result = read_normalizer(paths.artifacts_dir / "action_normalizer_result.json")
    if normalizer_result.success and normalizer_result.findings:
        # Replace with normalized versions
        normalized_ids = {f.id for f in normalizer_result.findings}
        all_findings = [f for f in all_findings if f.id not in normalized_ids]
        all_findings.extend(normalizer_result.findings)

    # Read gap reviewer result — structured review + any new findings
    from .agents.gap_reviewer import read_result as read_gap
    gap_result = read_gap(paths.artifacts_dir / "gap_reviewer_result.json")
    if gap_result.success and gap_result.findings:
        gap_ids = {f.id for f in gap_result.findings}
        all_findings = [f for f in all_findings if f.id not in gap_ids]
        all_findings.extend(gap_result.findings)

    # Write findings_reviewer and action_normalizer handoffs for next agent pass
    if all_findings:
        from .agents.findings_reviewer import write_handoff as write_reviewer_handoff
        from .agents.action_normalizer import write_handoff as write_normalizer_handoff
        from .agents.gap_reviewer import write_handoff as write_gap_handoff
        write_reviewer_handoff(
            paths.artifacts_dir / "findings_reviewer_handoff.json",
            all_findings,
        )
        write_normalizer_handoff(
            paths.artifacts_dir / "action_normalizer_handoff.json",
            all_findings,
        )
        # Gap reviewer: context-enriched handoff with detector evidence + absence signals
        detectors_ran = list({f.source_name for f in all_findings if f.source_name})
        # Only list a detector as "empty" if it produced NO findings this run.
        # invocation_tracker always emits at least INVOCATION-UNACTIONED-001, so never
        # list it in detectors_empty (avoids schema contradiction: GAPR-pipeline-1).
        invocation_ran = any(f.source_name == "invocation_tracker" for f in all_findings)
        _detectors_empty = [
            "session_goal_detector", "context_boundary_detector",
            "stuckness_detector",
            "hook_health_detector", "workflow_hygiene_detector",
            "verification_debt_detector",
        ]
        if not invocation_ran:
            _detectors_empty.append("invocation_tracker")
        # Filter: remove detectors that actually produced findings
        detectors_empty = [d for d in _detectors_empty if d not in detectors_ran]
        outcome_dicts = [
            {"category": getattr(i, "category", ""), "content": getattr(i, "content", "")}
            for i in (outcome_result.items if outcome_result else [])
        ]
        write_gap_handoff(
            paths.artifacts_dir / "gap_reviewer_handoff.json",
            all_findings,
            session_outcomes=outcome_dicts,
            changed_files=changed_files_for_decay,
            session_context={
                "terminal_id": args.terminal_id,
                "session_id": args.session_id,
                "git_sha": settings.git_sha,
                "root": str(root),
            },
            detectors_ran=detectors_ran,
            detectors_empty=detectors_empty,
        )

    all_findings = route_findings(all_findings)
    all_findings = order_findings(all_findings)

    # Phase 4.7.5: Staleness re-check — suppress findings with stale git evidence
    # (e.g., workflow_hygiene detected uncommitted files that were committed before this point)
    import subprocess as _sp
    try:
        _git_status = _sp.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(root), timeout=10,
        )
        _dirty_files = set(_git_status.stdout.strip().splitlines()) if _git_status.stdout.strip() else set()
        _dirty_names = {line.split(maxsplit=1)[-1] if line else "" for line in _dirty_files}
    except Exception:
        _dirty_names = None  # can't verify, don't suppress

    if _dirty_names is not None:
        _stale: list[Finding] = []
        for f in all_findings:
            if f.source_name == "workflow_hygiene_detector" and f.gap_type == "techdebt":
                # Re-check: are the files still uncommitted?
                for ev in f.evidence:
                    if ev.kind == "git_status" and ev.detail:
                        mentioned = {name.strip() for name in ev.detail.split(",")}
                        if not mentioned & _dirty_names:
                            f.status = "resolved"
                            _stale.append(f)
                            break
        if _stale:
            all_findings = [f for f in all_findings if f.status != "resolved"]

    # Phase 4.8: Impact radius enrichment
    all_findings = enrich_with_impact_radius(root, all_findings)

    # Phase 4.9: Finding clustering
    all_findings = cluster_findings(all_findings)

    # Phase 4.10: Branch-aware priority adjustment
    all_findings = adjust_for_branch(root, all_findings)

    # Phase 4.11: Stuckness detection from session chain
    stuckness_findings = detect_stuckness(
        root, chain, carryover,
        args.terminal_id, args.session_id, settings.git_sha,
    )
    all_findings.extend(stuckness_findings)

    # Phase 5: Compute coverage + health score
    coverage = compute_coverage(all_findings)

    # Phase 6: Determine freshness
    freshness = classify_freshness(
        artifact_git_sha=prev_git_sha,
        current_git_sha=settings.git_sha,
        artifact_target=state.current_target,
        current_target=state.current_target,
    )

    health = compute_health_score(all_findings, freshness)

    # Phase 7: Build and write artifact
    artifact = GTOArtifact.empty(
        mode="full",
        terminal_id=args.terminal_id,
        session_id=args.session_id,
        target=state.current_target,
        git_sha=settings.git_sha,
    )
    artifact.freshness = freshness
    artifact.coverage = coverage
    artifact.summary = {
        "total_findings": len(all_findings),
        "by_severity": coverage.get("by_severity", {}),
        "by_domain": coverage.get("by_domain", {}),
        "health": health,
    }

    artifact_path = paths.outputs_dir / "artifact.json"
    write_artifact(artifact_path, artifact, all_findings)

    # Phase 8: Save carryover for future runs (includes resolved for dedup)
    save_carryover(paths.artifacts_dir, carryover_findings)
    prune_carryover(paths.artifacts_dir)

    # Phase 9: Update state
    state.phase = "completed"
    state.verification_status = "pending"
    state.last_artifact = str(artifact_path)
    state.expected_artifacts = [str(artifact_path)]
    save_state(state_file, state)
    sync_to_execution_state(state, paths.artifacts_dir)

    # Phase 10: Verify
    verification = verify_artifact(artifact_path)
    state.verification_status = "pass" if verification["valid"] else "fail"
    save_state(state_file, state)
    sync_to_execution_state(state, paths.artifacts_dir)

    # Output summary
    print(f"GTO complete: {len(all_findings)} findings", file=sys.stderr)
    print(f"Artifact: {artifact_path}", file=sys.stderr)
    print(f"Freshness: {freshness}", file=sys.stderr)

    return 0 if verification["valid"] else 1


if __name__ == "__main__":
    sys.exit(run())
