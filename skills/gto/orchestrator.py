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
from .__lib.chat_history_patterns import ChatHistoryPatterns
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
from .__lib.scoring import score_findings
from .__lib.machine_render import build_triage
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
from .__lib.evidence_map import write_evidence_map
from .__lib.prompt_quality import validate_prompt_output
from .__lib.structural_analysis import write_structural_summary
from .__lib import friction
from .__lib.stale_detector import detect_stale_docs

# Session registry access for session resolution
sys.path.insert(0, "P:/packages/.claude-marketplace/plugins/snapshot/scripts/hooks/__lib")
from session_registry import query_registry


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GTO Gap Analysis Orchestrator")
    parser.add_argument("--target", help="Target directory or project to analyze")
    parser.add_argument("--terminal-id", default="default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--merge-only", action="store_true", help="Skip detectors, only merge agent results into existing artifact")
    parser.add_argument(
        "--transcript", type=Path, default=None,
        help="Explicit JSONL transcript file to analyze (bypasses session registry lookup). "
             "Use when the session is not registered — e.g. an archived session or a /chs export "
             "produced with --format jsonl.",
    )
    parser.add_argument(
        "--top-n", type=int, default=3,
        help="Size of the leverage-ranked 'Top N by leverage' triage list in the "
             "artifact summary (the 'Do ALL' footer is always retained). 0 disables triage.",
    )
    return parser.parse_args(argv)


def _read_prev_health_score(artifact_path: Path) -> int | None:
    """Read the previous run's health score from an existing artifact, if any.

    Used to compute the run-over-run health trend. Returns None when there is
    no prior artifact or the score cannot be read, so the first run reports no
    trend rather than failing.
    """
    if not artifact_path.exists():
        return None
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        score = data.get("summary", {}).get("health", {}).get("score")
        return int(score) if score is not None else None
    except (OSError, ValueError, json.JSONDecodeError, AttributeError):
        return None


def _normalize_terminal_id_for_registry(terminal_id: str) -> tuple[str, ...]:
    """Return candidate keys to try for session_registry lookup.

    Handles both old (env_<12chars>) and new (UUID) terminal ID formats.
    Priority: exact match -> try other prefixes -> try with current working directory.
    """
    if not terminal_id:
        return ()

    candidates = []

    # 1. Add console_ prefix to bare UUID (most common case)
    if "-" in terminal_id and not terminal_id.startswith(("console_", "env_")):
        candidates.append(f"console_{terminal_id}")

    # 2. Try exact match
    candidates.append(terminal_id)

    # 3. Strip known prefixes
    for prefix in ("console_", "env_", "wt_", "tmux_"):
        if terminal_id.startswith(prefix):
            stripped = terminal_id[len(prefix):]
            if stripped and stripped not in candidates:
                candidates.append(stripped)
            break

    # 4. Add prefixes to stripped form (reverse of step 3)
    for prefix in ("console_", "env_"):
        if terminal_id and "-" in terminal_id and not terminal_id.startswith(prefix):
            prefixed = f"{prefix}{terminal_id}"
            if prefixed not in candidates:
                candidates.append(prefixed)

    return tuple(candidates)


def _resolve_session_id_from_registry(terminal_id: str) -> str:
    """Extract session_id from session_registry for this terminal (most recent entry)."""
    for key in _normalize_terminal_id_for_registry(terminal_id):
        try:
            entries = query_registry(terminal_id=key, limit=1)
            if entries:
                return entries[-1].get("session_id", "")
        except Exception:
            continue
    return ""


def _resolve_terminal_id_via_session_id(session_id: str) -> str:
    """Reverse-lookup: given a Claude session_id, find the terminal_id that owns it.

    Returns the terminal_id from the most recent registry entry matching session_id.
    Used as a fallback when the per-invocation terminal_id passed via $WT_SESSION
    does not match the registry key (which is keyed by Claude session_id).
    """
    if not session_id:
        return ""
    try:
        entries = query_registry(session_id=session_id, limit=1)
        if entries:
            return entries[-1].get("terminal_id", "")
    except Exception:
        pass
    return ""


def _session_id_from_transcript_path(transcript_path: Path | None) -> str:
    """Extract Claude session_id from a transcript JSONL filename.

    The transcript filename is the session_id: `de62c888-1196-4d53-a2b0-...jsonl`.
    Used when $CLAUDE_SESSION_ID is unset but we have an explicit --transcript
    or can discover the latest transcript via cwd.
    """
    if not transcript_path:
        return ""
    return transcript_path.stem


def _resolve_transcript_from_registry(terminal_id: str, session_id: str = "") -> Path | None:
    """Resolve transcript path from session_registry.

    Tries terminal_id first (primary), then falls back to session_id (cross-terminal
    chain) when the per-invocation terminal_id does not resolve.
    """
    # Primary: terminal_id lookup (try literal, then strip surface prefix)
    for key in _normalize_terminal_id_for_registry(terminal_id):
        try:
            entries = query_registry(terminal_id=key, limit=1)
            if entries:
                tp = entries[-1].get("transcript_path", "")
                if tp and Path(tp).exists():
                    return Path(tp)
        except Exception:
            continue
    # Fallback: session_id lookup (per-invocation terminal_id may not match registry key)
    if session_id:
        try:
            entries = query_registry(session_id=session_id, limit=1)
            if entries:
                tp = entries[-1].get("transcript_path", "")
                if tp and Path(tp).exists():
                    return Path(tp)
        except Exception:
            pass
    return None


def _session_resolution_status(terminal_id: str, session_id: str = "") -> str:
    """Classify whether a real session was resolved for this terminal_id.

    Uses session_registry.jsonl as the primary source of truth. Primary lookup
    is by terminal_id; if that returns no entries, falls back to session_id
    (the Claude session UUID, which IS the registry key in practice).

    Returns: "unresolved" (no registry entries, no identity.json),
             "stale" (identity.json exists but transcript gone),
             or "resolved" (registry has entries with transcript_path).
    """
    if not terminal_id or terminal_id == "default":
        return "unresolved"

    # Primary: check registry for entries with transcript_path
    # (try literal terminal_id, then strip surface prefix like "console_")
    for key in _normalize_terminal_id_for_registry(terminal_id):
        try:
            entries = query_registry(terminal_id=key, limit=1)
            if entries:
                latest = entries[-1]
                if latest.get("transcript_path") and Path(latest["transcript_path"]).exists():
                    return "resolved"
        except Exception:
            continue

    # Fallback A: check registry by session_id (the Claude session UUID)
    # This is the actual registry key in practice; terminal_id from $WT_SESSION
    # is a per-invocation artifact UUID that does not match the key.
    if session_id:
        try:
            entries = query_registry(session_id=session_id, limit=1)
            if entries:
                latest = entries[-1]
                if latest.get("transcript_path") and Path(latest["transcript_path"]).exists():
                    return "resolved"
        except Exception:
            pass

    # Fallback B: identity.json (only for supplemental data)
    artifacts_root = Path(os.environ.get("CLAUDE_ARTIFACTS_ROOT", "P:/.claude/.artifacts"))
    identity_file = artifacts_root / terminal_id / "identity.json"
    if not identity_file.exists():
        return "unresolved"
    if _resolve_transcript_from_registry(terminal_id, session_id) is None:
        return "stale"
    return "resolved"

def _make_unresolved_finding(terminal_id: str, session_id: str, git_sha: str) -> Finding:
    """HIGH finding emitted when GTO could not resolve a real session.

    Replaces the silent "0 findings" hollow success with an explicit, actionable
    failure: nothing was analyzed, and the operator must resolve the REAL
    terminal-id instead of inventing one.
    """
    return Finding(
        id="GTO-SESSION-UNRESOLVED",
        title="GTO analyzed NO session -- terminal-id did not resolve",
        description=(
            f"terminal-id {terminal_id!r} has no session_registry entry, "
            "so no session transcript was resolved and every session-aware "
            "detector was skipped. A low/zero finding count here is NOT a clean bill "
            "of health -- it means nothing was analyzed. Resolve the REAL terminal-id "
            "and re-run. Do not pass fabricated IDs like 'local', 'default', or 'test'."
        ),
        source_type="detector",
        source_name="session_resolution_guard",
        domain="other",
        gap_type="session_unresolved",
        severity="high",
        evidence_level="verified",
        action="recover",
        priority="high",
        status="open",
        terminal_id=terminal_id,
        session_id=session_id,
        git_sha=git_sha,
    )


def _load_session_chain(terminal_id: str) -> list[str]:
    """Load session transcript paths from session registry for this terminal."""
    entries: list[dict] = []
    for key in _normalize_terminal_id_for_registry(terminal_id):
        try:
            entries = query_registry(terminal_id=key, limit=20)
            if entries:
                break
        except Exception:
            continue
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

    # Prompt quality validation (warnings only, non-blocking)
    for agent_name, agent_result in [
        ("domain_analyzer", domain_result),
        ("gap_reviewer", gap_result),
    ]:
        if agent_result.success and agent_result.findings:
            dicts = [f.to_dict() if hasattr(f, "to_dict") else f for f in agent_result.findings]
            violations = validate_prompt_output(agent_name, dicts)
            for v in violations:
                print(f"PROMPT_QUALITY: {v}", file=sys.stderr)

    # Post-processing pipeline. Score after impact_radius enrichment so the
    # leverage score is populated, then order by it (same contract as run()).
    all_findings = route_findings(all_findings)
    all_findings = enrich_with_impact_radius(settings.root, all_findings)
    all_findings = cluster_findings(all_findings)
    all_findings = adjust_for_branch(settings.root, all_findings)
    all_findings = score_findings(all_findings)
    all_findings = order_findings(all_findings)

    # Compute coverage + health
    coverage = compute_coverage(all_findings)
    freshness = classify_freshness(
        artifact_git_sha=state.git_sha,
        current_git_sha=settings.git_sha,
        artifact_target=state.current_target,
        current_target=state.current_target,
    )
    prev_score = _read_prev_health_score(artifact_path)
    health = compute_health_score(all_findings, freshness, prev_score=prev_score)

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
        "triage": build_triage(all_findings, args.top_n),
    }
    write_artifact(artifact_path, artifact, all_findings)

    # Write evidence map
    write_evidence_map(paths.outputs_dir / "evidence_map.json", all_findings)
    write_structural_summary(paths.outputs_dir / "structural_summary.json", all_findings)

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

    # --transcript override: explicit JSONL bypasses registry lookup entirely.
    # Validate the path early so we fail fast before touching any state.
    explicit_transcript: Path | None = None
    if args.transcript is not None:
        explicit_transcript = Path(args.transcript).resolve()
        if not explicit_transcript.exists():
            print(f"GTO: --transcript path does not exist: {explicit_transcript}", file=sys.stderr)
            return 1
        # Detect likely-wrong file type: markdown chs exports silently produce 0 turns.
        # Check the first non-empty line — JSONL starts with '{', markdown starts with '#' or text.
        try:
            with open(explicit_transcript, encoding="utf-8", errors="ignore") as _f:
                _first = next((ln.strip() for ln in _f if ln.strip()), "")
            if _first and not _first.startswith("{"):
                print(
                    f"GTO: --transcript file does not look like JSONL (first line: {_first[:60]!r}).\n"
                    "GTO requires a Claude Code JSONL transcript, not a markdown export.\n"
                    "If you used /chs export, re-run with --format jsonl:\n"
                    "  python .../chs_cli.py --export --format jsonl --output session.jsonl\n"
                    "Then pass: --transcript session.jsonl",
                    file=sys.stderr,
                )
                return 1
        except (OSError, StopIteration):
            pass

    # Resolve session_id: CLI arg → registry fallback → transcript-filename fallback
    if not args.session_id:
        args.session_id = _resolve_session_id_from_registry(args.terminal_id)
    if not args.session_id and explicit_transcript:
        # Last resort: the transcript JSONL filename IS the session_id
        args.session_id = _session_id_from_transcript_path(explicit_transcript)

    # Session resolution guard: detect a fabricated/empty terminal-id up front.
    # Suppressed when an explicit transcript is provided — the caller owns the source.
    session_status = "resolved" if explicit_transcript else _session_resolution_status(args.terminal_id, args.session_id)

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

    # Session resolution guard: an unresolved terminal-id means every
    # session-aware detector below is skipped, so a "0 findings" result would be
    # a hollow success. Surface it as a HIGH finding instead.
    if session_status == "unresolved":
        findings.append(_make_unresolved_finding(
            args.terminal_id, args.session_id, settings.git_sha))

    # Phase 1.2: Marker staleness — detect stale session markers from prior runs
    from .__lib.detectors import detect_marker_staleness, detect_missing_verification_evidence
    marker_findings = detect_marker_staleness(root, args.terminal_id, args.session_id, settings.git_sha)
    findings.extend(marker_findings)

    # Phase 1.3: Missing verification evidence — detect findings citing hooks/telemetry without test coverage
    verification_findings = detect_missing_verification_evidence(root, args.terminal_id, args.session_id, settings.git_sha)
    findings.extend(verification_findings)

    # Phase 1.5: Resolve transcript — explicit --transcript overrides registry lookup.
    transcript_path = explicit_transcript or _resolve_transcript_from_registry(args.terminal_id, args.session_id)

    # Last-resort terminal_id repair: if the per-invocation terminal_id didn't
    # resolve to a transcript but the session_id did (via the registry fallback
    # above), reverse-look-up the canonical terminal_id for downstream phases
    # that key by terminal_id (e.g., carryover, state).
    if not explicit_transcript and transcript_path:
        # If the primary terminal_id lookup returned no entries but the session_id
        # fallback succeeded, swap args.terminal_id to the canonical one so all
        # downstream lookups are consistent.
        canonical_tid = _resolve_terminal_id_via_session_id(args.session_id)
        if canonical_tid and canonical_tid != args.terminal_id:
            args.terminal_id = canonical_tid

    # Phase 1.6: Extract files edited this session from transcript tool calls
    session_edited_files = extract_edited_files(transcript_path, root) if transcript_path else []

    # Phase 1.4: Changelog detection — files edited in session, mapped to skills
    changelog_findings = detect_changelog_findings(
        session_edited_files,
        terminal_id=args.terminal_id,
        session_id=args.session_id,
        git_sha=settings.git_sha,
    )
    findings.extend(changelog_findings)

    # Session-edited files used for carryover decay and gap reviewer handoff
    changed_files_for_decay = session_edited_files

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

    # Phase 1.9.5: Detect chat history patterns (avoidance, recurrence, dependencies, trajectory, reflection)
    chat_patterns: dict[str, any] = {}
    if transcript_path:
        pattern_detector = ChatHistoryPatterns(root)
        chat_patterns = {
            "avoidance_signals": [
                {"topic": s.topic, "confidence": s.confidence, "evidence": s.evidence_snippets[:2]}
                for s in pattern_detector.detect_avoidance_signals(transcript_path)
            ],
            "recurring_themes": [
                {"theme": t.theme, "session_count": t.session_count, "urgency": t.urgency, "confidence": t.confidence}
                for t in pattern_detector.detect_recurring_themes(transcript_path, chain)
            ],
            "dependency_gaps": [
                {"completed": d.completed_action, "missing": d.missing_dependency, "priority": d.priority, "evidence": d.evidence}
                for d in pattern_detector.detect_dependency_chain(transcript_path, session_edited_files)
            ],
            "implied_next_steps": [
                {"pattern": i.observed_pattern, "action": i.implied_action, "confidence": i.confidence, "file": i.file_affected}
                for i in pattern_detector.detect_work_trajectory(transcript_path)
            ],
            "reflection_triggers": [
                {"type": r.trigger_type, "context": r.context, "question": r.suggested_reflection, "priority": r.priority}
                for r in pattern_detector.detect_self_reflection_triggers(transcript_path)
            ],
        }

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

    # Phase 1.15: Workflow hygiene — session-edited files from transcript
    hygiene_findings = detect_workflow_hygiene(
        session_edited_files,
        terminal_id=args.terminal_id,
        session_id=args.session_id,
        git_sha=settings.git_sha,
    )
    findings.extend(hygiene_findings)

    # Phase 1.17: Friction detection — interaction and workflow patterns
    if transcript_path:
        friction_findings = []
        friction_findings.extend(friction.detect_correction_patterns(transcript_path, args.terminal_id, args.session_id, settings.git_sha))
        friction_findings.extend(friction.detect_workflow_repetition(transcript_path, args.terminal_id, args.session_id, settings.git_sha))
        findings.extend(friction_findings)

    # Phase 1.18: Stale documentation detection — docs referencing modified source files
    stale_findings = detect_stale_docs(
        root=root,
        session_edited_files=session_edited_files,
        terminal_id=args.terminal_id,
        session_id=args.session_id,
        git_sha=settings.git_sha,
    )
    findings.extend(stale_findings)

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

    # Prompt quality validation (warnings only, non-blocking)
    for _aq_name, _aq_result in [
        ("domain_analyzer", domain_result),
        ("gap_reviewer", gap_result),
    ]:
        if _aq_result.success and _aq_result.findings:
            _aq_dicts = [f.to_dict() if hasattr(f, "to_dict") else f for f in _aq_result.findings]
            for _aq_v in validate_prompt_output(_aq_name, _aq_dicts):
                print(f"PROMPT_QUALITY: {_aq_v}", file=sys.stderr)

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
        # Compute structural patterns for gap reviewer context
        from .__lib.structural_analysis import analyze_structure
        _structural_patterns = analyze_structure(all_findings)
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
            chat_history_patterns=chat_patterns,
            detectors_empty=detectors_empty,
            structural_patterns=_structural_patterns,
        )

    all_findings = route_findings(all_findings)
    # Ordering is deferred to after enrichment + stuckness so the final written
    # list is leverage-score ordered (see Phase 4.12 below).

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

    # Phase 4.12: Score then order — leverage (value/effort) drives final order.
    # Scoring runs after impact_radius enrichment (which feeds the score) and
    # after all findings are collected, so the written list is correctly ranked.
    all_findings = score_findings(all_findings)
    all_findings = order_findings(all_findings)

    # Phase 5: Compute coverage + health score
    coverage = compute_coverage(all_findings)

    # Phase 6: Determine freshness
    freshness = classify_freshness(
        artifact_git_sha=prev_git_sha,
        current_git_sha=settings.git_sha,
        artifact_target=state.current_target,
        current_target=state.current_target,
    )

    artifact_path = paths.outputs_dir / "artifact.json"
    prev_score = _read_prev_health_score(artifact_path)
    health = compute_health_score(all_findings, freshness, prev_score=prev_score)

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
        "triage": build_triage(all_findings, args.top_n),
    }

    write_artifact(artifact_path, artifact, all_findings)

    # Phase 7.5: Write evidence map (provenance index alongside artifact)
    write_evidence_map(paths.outputs_dir / "evidence_map.json", all_findings)
    structural_summary = write_structural_summary(paths.outputs_dir / "structural_summary.json", all_findings)

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
    if session_status == "unresolved":
        print(
            "GTO SESSION UNRESOLVED: terminal-id "
            f"{args.terminal_id!r} has no session_registry entry -- analyzing "
            "current session state only. Historical session chain not available.",
            file=sys.stderr,
        )
    print(f"GTO complete: {len(all_findings)} findings", file=sys.stderr)
    print(f"Artifact: {artifact_path}", file=sys.stderr)
    print(f"Freshness: {freshness}", file=sys.stderr)

    # Return success for unresolved sessions (non-critical missing registry)
    return 0 if verification["valid"] else 1


if __name__ == "__main__":
    sys.exit(run())
