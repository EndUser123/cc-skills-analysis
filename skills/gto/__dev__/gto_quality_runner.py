#!/usr/bin/env python3
"""GTO Quality Runner — automation-first implementer + verify + aggregate workflow.

Runs the GTO or GTO_v2 pipeline (orchestrator → gap reviewer → merge) and emits
a machine-readable FINALVERDICT. This is the single entry point for quality-gate
automation: no human memory branching, deterministic JSON output, terminal-scoped.

Usage (automation / hook integration):
    python gto_quality_runner.py --variant both
    python gto_quality_runner.py --variant gto
    python gto_quality_runner.py --variant gto_v2

Usage (CLI debug / replay):
    python gto_quality_runner.py --variant both --dry-run
    python gto_quality_runner.py --variant both --dump-handoff

Inputs (from environment):
    WT_SESSION          → terminal_id (console_{WT_SESSION})
    CLAUDE_SESSION_ID   → session_id (primary override)
    CLAUDE_CODE_SESSION_ID → session_id (fallback, inherited from Claude Code runtime)
    CLAUDE_ARTIFACTS_ROOT → artifacts root override (default: P:/.claude/.artifacts)

Exit codes:
    0  → final_status in accept, accept-with-small-fixes  AND all phases completed
    1  → final_status indicates revise, OR critical errors, OR phases incomplete

Output:
    JSON to stdout: {mission, variants, final_status}
    Text to stderr: human-readable summary for terminal logs
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # skills/gto/__dev__/ → cc-skills-analysis/

PYTHON = sys.executable

# Fix module resolution so `python -m skills.gto.orchestrator` works from any cwd
import sys as _sys
_cc_path = str(SKILLS_ROOT.parent)  # P:/packages/.claude-marketplace/plugins
if _cc_path not in _sys.path:
    _sys.path.insert(0, _cc_path)

CLAUDE_ARTIFACTS_ROOT = Path(os.environ.get("CLAUDE_ARTIFACTS_ROOT", "P:/.claude/.artifacts"))

FINALVERDICT_ACCEPT = {"accept", "accept-with-small-fixes"}
FINALVERDICT_REVISE = {"revise-before-use", "revise"}
FINALVERDICT_BLOCK = {"reject", "blocked"}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_terminal_id() -> str:
    raw = os.environ.get("WT_SESSION", "")
    if raw:
        return f"console_{raw}"
    return "unknown"


def get_session_id() -> str:
    """Return session ID from env.

    Prefers CLAUDE_SESSION_ID (explicit override) over CLAUDE_CODE_SESSION_ID
    (inherited by subprocess from Claude Code runtime). In this deployment,
    CLAUDE_SESSION_ID is unset so CLAUDE_CODE_SESSION_ID is the active source.
    """
    return os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def get_artifacts_root() -> Path:
    root_str = os.environ.get("CLAUDE_ARTIFACTS_ROOT", "").strip()
    if root_str:
        return Path(root_str)
    return Path("P:/.claude/.artifacts")


def artifacts_dir(terminal_id: str) -> Path:
    return get_artifacts_root() / terminal_id / "gto"


def variant_artifacts_dir(terminal_id: str, variant: str) -> Path:
    """Per-variant artifact directory aligned with each orchestrator's actual output path.

    gto orchestrator → {terminal_id}/gto/
    gto_v2 orchestrator → {terminal_id}/gto_v2/
    """
    if variant == "gto_v2":
        return get_artifacts_root() / terminal_id / "gto_v2"
    return get_artifacts_root() / terminal_id / "gto"


def state_file(terminal_id: str, variant: str | None = None) -> Path:
    if variant:
        return variant_artifacts_dir(terminal_id, variant) / "state" / "run_state.json"
    return artifacts_dir(terminal_id) / "state" / "run_state.json"


def output_file(terminal_id: str, variant: str | None = None) -> Path:
    if variant:
        return variant_artifacts_dir(terminal_id, variant) / "outputs" / "artifact.json"
    return artifacts_dir(terminal_id) / "outputs" / "artifact.json"


def gap_reviewer_handoff(terminal_id: str, variant: str) -> Path:
    return variant_artifacts_dir(terminal_id, variant) / "gap_reviewer_handoff.json"


def gap_reviewer_result(terminal_id: str, variant: str) -> Path:
    return variant_artifacts_dir(terminal_id, variant) / "gap_reviewer_result.json"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator runner
# ─────────────────────────────────────────────────────────────────────────────

def run_orchestrator(skill: str, terminal_id: str, session_id: str) -> subprocess.CompletedProcess:
    """Run the GTO orchestrator for the given skill variant."""
    if skill == "gto_v2":
        module = "skills.gto_v2.orchestrator"
    else:
        module = "skills.gto.orchestrator"

    cmd = [
        PYTHON, "-m", module,
        "--terminal-id", terminal_id,
        "--session-id", session_id,
        "--root", str(SKILLS_ROOT),
    ]

    return subprocess.run(
        cmd,
        cwd=str(SKILLS_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gap Reviewer subagent
# ─────────────────────────────────────────────────────────────────────────────

def gap_reviewer_needed(terminal_id: str, variant: str) -> bool:
    return gap_reviewer_handoff(terminal_id, variant).exists()


def run_gap_reviewer_agent(terminal_id: str, session_id: str, variant: str) -> tuple[bool, str]:
    """Spawn Gap Reviewer subagent via claude -p --bare.

    Reads the handoff, writes gap_reviewer_result.json.
    Returns (True, "") if result file was written, (False, error_msg) otherwise.
    """
    handoff_path = gap_reviewer_handoff(terminal_id, variant)
    result_path = gap_reviewer_result(terminal_id, variant)

    if not handoff_path.exists():
        return False, "handoff file missing"

    prompt = GAP_REVIEWER_AGENT_PROMPT.format(
        handoff_path=str(handoff_path),
        result_path=str(result_path),
    )

    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8",
    ) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        # Only set CLAUDE_SESSION_ID if session_id is non-empty — passing ''
        # overwrites the inherited CLAUDE_CODE_SESSION_ID in the subprocess
        if session_id:
            env = {**os.environ, "CLAUDE_SESSION_ID": session_id}
        else:
            env = dict(os.environ)

        result = subprocess.run(
            ["claude", "-p", "--bare", f"@{prompt_file}"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(SKILLS_ROOT),
            env=env,
        )
        if result.returncode != 0:
            return False, f"claude -p exit {result.returncode}: {result.stderr[:300]}"
        if not result_path.exists():
            return False, f"claude -p returned 0 but result file not written"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "claude -p timed out after 300s"
    except Exception as e:
        return False, f"claude -p exception: {e}"
    finally:
        try:
            Path(prompt_file).unlink()
        except Exception:
            pass


GAP_REVIEWER_AGENT_PROMPT = """You are a gap-to-opportunity reviewer. You receive pre-populated detector evidence and produce a structured review.

Read the handoff file at: {handoff_path}

The handoff JSON contains:
- detected_facts: concrete observations from deterministic detectors
- signals_absent: detectors that ran but found nothing (absence as evidence)
- session_context: terminal_id, session_id, git_sha, files edited this session
- findings: current findings from the deterministic pipeline

Produce a JSON object with two fields and write it to: {result_path}

1. "review": an object with these sections:
   - "facts": list of concrete observations grounded in the detector evidence. Each entry is {{"claim": "...", "source": "detector_name or file:line"}}
   - "inferences": list of hypotheses about failure modes or friction points. Each entry is {{"hypothesis": "...", "confidence": "low|medium|high", "evidence": "what supports this"}}
   - "unknowns": list of important questions that cannot be answered from the evidence. Each entry is {{"question": "...", "why_it_matters": "..."}}
   - "recommendations": list of specific next actions, ranked by impact. Produce as many as the evidence supports. Each entry is {{"action": "...", "goal": "...", "assumption": "...", "rationale": "..."}}

2. "findings": a JSON array of any NEW gaps you discovered that are NOT already in the input findings, following the standard finding schema:
   {{"id": "GAPR-{{domain}}-{{number}}", "title": "...", "description": "...", "domain": "...", "gap_type": "...", "severity": "...", "action": "realize", "priority": "...", "evidence": [...]}}

Rules:
- Do not duplicate findings already present in the input
- Prefer issues predictable from system structure (overlapping validators, mode flags, format constraints)
- Do not propose large refactors without a concrete pain point from the evidence
- Mark confidence honestly — do not inflate inferences to facts
- If the session was exploratory with no clear trajectory, say so rather than forcing predictions
- Frame recommendations as actions the user can take, not obligations

Respond ONLY with the JSON object written to {result_path}, no other output."""


# ─────────────────────────────────────────────────────────────────────────────
# Pytest runner
# ─────────────────────────────────────────────────────────────────────────────

def run_pytest_for_variant(skill: str, terminal_id: str) -> dict[str, Any]:
    """Run pytest for the given GTO variant.

    Returns a dict with keys: passed (bool), returncode (int), output (str), duration_s (float).
    """
    t0 = time.perf_counter()
    test_paths = []

    # Discover test paths for the skill variant
    if skill == "gto_v2":
        test_dirs = [
            SKILLS_ROOT / "skills" / "gto_v2",
        ]
    else:
        test_dirs = [
            SKILLS_ROOT / "skills" / "gto",
        ]

    for test_dir in test_dirs:
        for pattern in ["**/test_*.py", "**/tests/*.py"]:
            test_paths.extend(test_dir.glob(pattern))

    # Deduplicate and filter out __pycache__
    seen = set()
    unique_paths = []
    for p in test_paths:
        key = str(p.resolve())
        if key not in seen and "__pycache__" not in key:
            seen.add(key)
            unique_paths.append(p)

    if not unique_paths:
        return {
            "passed": True,
            "skipped": True,
            "returncode": 0,
            "output": "(no tests found)",
            "duration_s": time.perf_counter() - t0,
        }

    # Run pytest with json report
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as f:
        report_file = f.name

    try:
        cmd = [
            PYTHON, "-m", "pytest",
            "--json-report",
            "--json-report-file=" + report_file,
            "-v",
            *[str(p) for p in unique_paths],
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(SKILLS_ROOT),
        )
        duration = time.perf_counter() - t0

        # Load pytest JSON report if available
        report_data = load_json(Path(report_file))
        passed = result.returncode == 0

        if report_data:
            summary = report_data.get("summary", {})
            num_passed = summary.get("passed", 0) if isinstance(summary, dict) else 0
            num_failed = summary.get("failed", 0) if isinstance(summary, dict) else 0
            output = f"passed={num_passed} failed={num_failed}"
        else:
            output = result.stdout[:500] if result.stdout else result.stderr[:500]

        return {
            "passed": passed,
            "skipped": False,
            "returncode": result.returncode,
            "output": output,
            "duration_s": duration,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "skipped": False,
            "returncode": -1,
            "output": "pytest timed out after 300s",
            "duration_s": time.perf_counter() - t0,
        }
    except Exception as e:
        return {
            "passed": False,
            "skipped": False,
            "returncode": -1,
            "output": str(e),
            "duration_s": time.perf_counter() - t0,
        }
    finally:
        try:
            Path(report_file).unlink()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Verdict aggregation (single-variant)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_variant_verdict(
    terminal_id: str,
    artifacts_dir: Path,
    skill: str,
) -> dict[str, Any]:
    """Read artifact + state for a single variant, compute per-phase status."""
    state_path = artifacts_dir / "state" / "run_state.json"
    output_path = artifacts_dir / "outputs" / "artifact.json"

    state = load_json(state_path) or {}
    artifact = load_json(output_path) or {}

    findings: list[dict] = artifact.get("findings", [])
    summary: dict = artifact.get("summary", {})

    escape_hatches = sum(1 for f in findings if f.get("metadata", {}).get("escape_hatch"))
    unverified_impl_claims = sum(1 for f in findings if f.get("metadata", {}).get("unverified_implementation_claim"))
    downgraded_absent = sum(1 for f in findings if f.get("metadata", {}).get("downgraded_absent_signal"))
    mixed_substance = sum(1 for f in findings if f.get("metadata", {}).get("mixed_substance"))

    total_findings = len(findings)
    by_severity: dict[str, int] = summary.get("by_severity", {})
    by_domain: dict[str, int] = summary.get("by_domain", {})

    phase = state.get("phase", "")
    verification_status = state.get("verification_status", "pending")
    health = summary.get("health", {})
    health_grade = health.get("grade", "unknown") if isinstance(health, dict) else health

    if phase != "completed":
        verdict_status = "revise-before-use"
        verdict_reason = f"orchestrator phase is '{phase}', expected 'completed'"
    elif verification_status == "fail":
        verdict_status = "revise-before-use"
        verdict_reason = "artifact verification failed"
    elif escape_hatches > 0 or mixed_substance > 0:
        verdict_status = "accept-with-small-fixes"
        verdict_reason = f"quality gates triggered ({escape_hatches} esc, {mixed_substance} mixed)"
    elif unverified_impl_claims > 0:
        verdict_status = "accept-with-small-fixes"
        verdict_reason = f"{unverified_impl_claims} unverified implementation claims"
    elif downgraded_absent > 0:
        verdict_status = "accept"
        verdict_reason = "absent-signal findings downgraded but pipeline healthy"
    elif total_findings == 0:
        verdict_status = "accept"
        verdict_reason = "no findings — clean run"
    else:
        verdict_status = "accept"
        verdict_reason = "pipeline complete with findings"

    passes = verdict_status in FINALVERDICT_ACCEPT

    return {
        "status": verdict_status,
        "reason": verdict_reason,
        "passes": passes,
        "confidence": 0.9 if phase == "completed" else 0.5,
        "phase": phase,
        "verification_status": verification_status,
        "health_grade": health_grade,
        "findings_total": total_findings,
        "findings_by_severity": by_severity,
        "findings_by_domain": by_domain,
        "gates": {
            "escape_hatches": escape_hatches,
            "unverified_implementation_claims": unverified_impl_claims,
            "downgraded_absent_signal": downgraded_absent,
            "mixed_substance": mixed_substance,
        },
        "artifacts": {
            "artifact": str(output_path) if output_path.exists() else None,
            "state": str(state_path) if state_path.exists() else None,
        },
    }


def run_variant_workflow(
    skill: str,
    terminal_id: str,
    session_id: str,
    run_pytest: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Run implementer → pytest → verifier for a single variant.

    Returns a dict with keys: implementer, pytest (optional), verifier, errors, timing.
    """
    errors: list[str] = []
    timing: dict[str, float] = {}

    # ── Implementer phase ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    result = run_orchestrator(skill, terminal_id, session_id)
    timing["orchestrator_s"] = time.perf_counter() - t0

    if result.returncode != 0:
        errors.append(f"orchestrator error: {result.stderr[:500]}")

    impl_phase = "completed" if result.returncode == 0 else "failed"
    impl_pass = result.returncode == 0

    # ── Pytest phase ──────────────────────────────────────────────────────
    pytest_result: dict[str, Any] | None = None
    if run_pytest and not dry_run:
        t1 = time.perf_counter()
        pytest_result = run_pytest_for_variant(skill, terminal_id)
        timing[f"{skill}_pytest_s"] = time.perf_counter() - t1
        if not pytest_result["passed"]:
            errors.append(f"pytest {skill}: {pytest_result['output']}")

    # ── Gap Reviewer ─────────────────────────────────────────────────────
    gap_agent_ran = False
    gap_agent_error = ""
    if not dry_run and gap_reviewer_needed(terminal_id, skill):
        t2 = time.perf_counter()
        gap_agent_ran, gap_agent_error = run_gap_reviewer_agent(terminal_id, session_id, skill)
        timing[f"{skill}_gap_reviewer_s"] = time.perf_counter() - t2
        if not gap_agent_ran:
            errors.append(f"gap reviewer agent ({skill}): {gap_agent_error}")

        # Re-run orchestrator to merge agent results
        t3 = time.perf_counter()
        result2 = run_orchestrator(skill, terminal_id, session_id)
        timing[f"{skill}_orchestrator_merge_s"] = time.perf_counter() - t3
        if result2.returncode != 0:
            errors.append(f"orchestrator merge error ({skill}): {result2.stderr[:500]}")

    elif dry_run:
        timing[f"{skill}_gap_reviewer_s"] = 0.0
        timing[f"{skill}_orchestrator_merge_s"] = 0.0

    # ── Verifier phase ───────────────────────────────────────────────────
    adir = variant_artifacts_dir(terminal_id, skill)
    verifier = aggregate_variant_verdict(terminal_id, adir, skill)
    verifier["gap_reviewer_ran"] = gap_agent_ran

    return {
        "implementer": {
            "phase": impl_phase,
            "returncode": result.returncode,
            "passed": impl_pass,
            "stderr": result.stderr[:300] if result.stderr else None,
        },
        "pytest": pytest_result,
        "verifier": verifier,
        "errors": errors,
        "timing": timing,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Final verdict aggregation
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_final_verdict(variants: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-variant results into a final status.

    Rules:
    - Any variant with final status in revise-before-use/revoke → final_status = revise-before-use
    - All variants accept-with-small-fixes → final_status = accept-with-small-fixes
    - All variants accept → final_status = accept
    - Mixed accept + accept-with-small-fixes → accept-with-small-fixes
    """
    statuses = []
    for name, v in variants.items():
        ver = v.get("verifier", {})
        statuses.append(ver.get("status", "unknown"))

    if any(s in FINALVERDICT_REVISE for s in statuses):
        final = "revise-before-use"
    elif all(s == "accept" for s in statuses):
        final = "accept"
    else:
        # Mixed: accept + accept-with-small-fixes
        final = "accept-with-small-fixes"

    return {
        "status": final,
        "variant_statuses": dict(zip(variants.keys(), statuses)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GTO Quality Runner — automation-first implementer + verify + aggregate",
    )
    parser.add_argument(
        "--variant",
        choices=["gto", "gto_v2", "both"],
        default="both",
        help="Skill variant to run (default: both)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without LLM agents — just aggregate existing artifacts",
    )
    parser.add_argument(
        "--no-pytest",
        action="store_true",
        help="Skip pytest phase",
    )
    parser.add_argument(
        "--dump-handoff",
        action="store_true",
        help="Print handoff path and exit (for debugging)",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Emit only the verdict JSON to stdout (no text)",
    )
    args = parser.parse_args(argv)

    terminal_id = get_terminal_id()
    session_id = get_session_id()
    run_pytest = not args.no_pytest

    # Determine which variants to run
    if args.variant == "both":
        variant_list = ["gto", "gto_v2"]
    else:
        variant_list = [args.variant]

    # Dump handoff path for debug
    if args.dump_handoff:
        handoff = gap_reviewer_handoff(terminal_id)
        print(handoff)
        return 0

    # Build mission string
    mission = f"gto-quality-runner/{'/'.join(variant_list)}"

    # Run each variant sequentially
    variants_result: dict[str, Any] = {}
    all_errors: list[str] = []

    for skill in variant_list:
        result = run_variant_workflow(
            skill=skill,
            terminal_id=terminal_id,
            session_id=session_id,
            run_pytest=run_pytest,
            dry_run=args.dry_run,
        )
        variants_result[skill] = result
        all_errors.extend(result.get("errors", []))

    # Aggregate final verdict
    final_verdict = aggregate_final_verdict(variants_result)

    # Build output
    output = {
        "mission": mission,
        "variants": variants_result,
        "final_status": final_verdict["status"],
        "final_status_detail": final_verdict,
        "terminal_id": terminal_id,
        "session_id": session_id,
        "errors": all_errors,
    }

    # Output
    if args.json_output:
        print(json.dumps(output, indent=2))
    else:
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        for skill, v in variants_result.items():
            impl = v["implementer"]
            ver = v["verifier"]
            py = v.get("pytest")
            gap_ran = ver.get("gap_reviewer_ran", False)
            status = ver.get("status", "unknown")
            reason = ver.get("reason", "")
            findings = ver.get("findings_total", 0)
            phase = ver.get("phase", "?")
            esc = ver.get("gates", {}).get("escape_hatches", 0)
            unverified = ver.get("gates", {}).get("unverified_implementation_claims", 0)
            mixed = ver.get("gates", {}).get("mixed_substance", 0)
            py_status = f"pytest={'PASS' if py['passed'] else 'FAIL' if py else 'SKIP'}" if py else ""
            gap_tag = f"gap={'YES' if gap_ran else 'no'}"
            print(
                f"[gto_quality_runner] [{skill}] status={status} "
                f"findings={findings} phase={phase} "
                f"esc={esc} unverified={unverified} mixed={mixed} "
                f"{gap_tag} {py_status} — {reason}",
                file=sys.stderr,
            )
        print(json.dumps(output, indent=2), file=sys.stderr)

    # Exit code
    final_status = final_verdict["status"]
    all_phases_complete = all(
        v.get("implementer", {}).get("phase") == "completed"
        for v in variants_result.values()
    )

    if final_status in FINALVERDICT_ACCEPT and all_phases_complete:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(run())