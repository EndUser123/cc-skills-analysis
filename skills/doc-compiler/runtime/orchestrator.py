#!/usr/bin/env python3
"""doc-compiler Orchestrator

Runs all 12 stages of the doc-compiler pipeline in order.
Each stage reads its input artifacts and emits its output artifact.

Usage:
    python -m doc_compiler.runtime.orchestrator [--target <path>]

The target is a SKILL.md, plugin.json, README.md, or workflow YAML/JSON file.

Environment:
    DOCC_TARGET  — fallback target path if --target not provided
"""
import json, os, sys, subprocess
from pathlib import Path
from datetime import datetime

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
RUNTIME = BASE / "runtime"

STAGES = [
    ("A", "stage_a_source_extractor"),
    ("B", "stage_b_doc_model_builder"),
    ("C", "stage_c_diagram_strategy_router"),
    ("D", "stage_d_guide_loader"),
    ("E", "stage_e_diagram_generator"),
    ("F", "stage_f_diagram_critic_gate"),
    ("G", "stage_g_artifact_plan_builder"),
    ("H", "stage_h_template_html_emitter"),
    ("I", "stage_i_static_validator"),
    ("J", "stage_j_runtime_validator"),
    ("K", "stage_k_external_critic"),
    ("L", "stage_l_emit_proof_bundle"),
]

# Gate stages handled by LangGraph quality-control subgraphs
# F (diagram), I+J (UI), K (final review) — all others are plain subprocess
_GATE_STAGES = {"F", "I", "J", "K"}

# Lazy-import quality graphs (defer langgraph load to when gate is reached)
_qg = None

def _load_quality_graph():
    global _qg
    if _qg is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("quality_graph", RUNTIME / "quality_graph.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["quality_graph"] = mod
        spec.loader.exec_module(mod)
        _qg = mod
    return _qg


def get_target() -> Path:
    """Resolve the target file path from CLI or environment."""
    if len(sys.argv) > 1 and sys.argv[1] == "--target":
        target = Path(sys.argv[2])
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target = Path(sys.argv[1])
    else:
        target_path = os.environ.get("DOCC_TARGET", "")
        if not target_path:
            print("ERROR: Provide target path as CLI arg or set DOCC_TARGET", file=sys.stderr)
            print("Usage: python -m doc_compiler.runtime.orchestrator [--target] <path>", file=sys.stderr)
            sys.exit(1)
        target = Path(target_path)
    return target


def run_stage(stage_name: str, stage_module: str, target: Path) -> bool:
    """Run a single stage and return whether it passed.

    Gate stages (F, I, J, K) are handled by LangGraph quality-control subgraphs.
    """
    stage_path = RUNTIME / f"{stage_module}.py"
    if not stage_path.exists():
        print(f"  ERROR: {stage_path} not found", file=sys.stderr)
        return False

    env = os.environ.copy()
    env["DOCC_TARGET"] = str(target.resolve())

    print(f"\n{'='*60}")
    print(f"Stage {stage_name}: {stage_module}")
    print(f"{'='*60}")

    # Dispatch gate stages to LangGraph subgraphs
    if stage_name == "F":
        return _run_diagram_qc(target, env)
    if stage_name == "I":
        return _run_ui_qc(target, env)
    if stage_name == "J":
        return _run_runtime_validator(target, env)
    if stage_name == "K":
        return _run_final_review_qc(target, env)

    try:
        result = subprocess.run(
            [sys.executable, str(stage_path)],
            cwd=str(BASE),
            env=env,
            capture_output=False,
            text=True,
            timeout=300,
        )
        passed = result.returncode == 0
        status = "PASS" if passed else "FAIL"
        print(f"Stage {stage_name}: {status} (exit {result.returncode})")
        return passed
    except subprocess.TimeoutExpired:
        print(f"Stage {stage_name}: FAIL -- timeout after 300s", file=sys.stderr)
        return False
    except Exception as ex:
        print(f"Stage {stage_name}: FAIL -- {ex}", file=sys.stderr)
        return False


def _run_diagram_qc(target: Path, env: dict) -> bool:
    """Run diagram QC subgraph (Stage F loop, max 3 retries)."""
    qg = _load_quality_graph()
    diagrams_json = str(BASE / "diagrams.json")
    diagrams_dir = str(BASE / "diagrams")
    doc_model = str(BASE / "doc-model.json")

    print("  [LangGraph] Running diagram_repair_subgraph (max 3 retries)...")
    try:
        result = qg.run_diagram_qc(diagrams_json, diagrams_dir, doc_model, max_retries=3)
        passed = result.get("gate_passed", False)
        retries = result.get("retry_count", 0)
        blocked = result.get("blocked_diagrams", [])
        issues = result.get("issues", [])
        print(f"  Diagram QC: {'PASS' if passed else 'FAIL'} (retries={retries})")
        if blocked:
            print(f"  Blocked diagrams: {blocked}")
        for issue in issues[:5]:
            print(f"    ISSUE: {issue}")
        return passed
    except Exception as ex:
        print(f"  Diagram QC ERROR: {ex}", file=sys.stderr)
        return False


def _run_ui_qc(target: Path, env: dict) -> bool:
    """Run static validation (Stage I) via LangGraph ui_repair_subgraph."""
    qg = _load_quality_graph()
    index_html = str(BASE / "index.html")
    source_model = str(BASE / "source-model.json")

    print("  [LangGraph] Running ui_repair_subgraph for Stage I (max 2 retries)...")
    try:
        result = qg.run_ui_qc(index_html, source_model, max_retries=2)
        passed = result.get("gate_passed", False)
        retries = result.get("retry_count", 0)
        static_fails = result.get("static_failures", [])
        print(f"  Static Validation: {'PASS' if passed else 'FAIL'} (retries={retries})")
        if static_fails:
            print(f"  Static failures ({len(static_fails)}): {static_fails[:5]}")
        return passed
    except Exception as ex:
        print(f"  Static Validation ERROR: {ex}", file=sys.stderr)
        return False


def _run_runtime_validator(target: Path, env: dict) -> bool:
    """Run browser runtime validation (Stage J) as a plain subprocess call."""
    stage_path = RUNTIME / "stage_j_runtime_validator.py"
    if not stage_path.exists():
        print(f"  ERROR: {stage_path} not found", file=sys.stderr)
        return False

    env = env.copy()
    env["DOCC_TARGET"] = str(target.resolve())

    print(f"\n{'='*60}")
    print(f"Stage J: stage_j_runtime_validator")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            [sys.executable, str(stage_path)],
            cwd=str(BASE),
            env=env,
            capture_output=False,
            text=True,
            timeout=180,
        )
        passed = result.returncode == 0
        status = "PASS" if passed else "FAIL"
        print(f"Stage J: {status} (exit {result.returncode})")
        return passed
    except subprocess.TimeoutExpired:
        print(f"Stage J: FAIL -- timeout after 180s", file=sys.stderr)
        return False
    except Exception as ex:
        print(f"Stage J: FAIL -- {ex}", file=sys.stderr)
        return False


def _run_final_review_qc(target: Path, env: dict) -> bool:
    """Run final-review subgraph (Stage K loop, max 2 retries)."""
    qg = _load_quality_graph()
    index_html = str(BASE / "index.html")
    source_model = str(BASE / "source-model.json")

    print("  [LangGraph] Running final_review_subgraph (max 2 retries)...")
    try:
        result = qg.run_final_review(index_html, source_model, max_retries=2)
        passed = result.get("review_passed", False)
        retries = result.get("retry_count", 0)
        blocked = result.get("blocked_checks", [])
        recs = result.get("recommendations", [])
        print(f"  Final Review: {'PASS' if passed else 'FAIL'} (retries={retries})")
        if blocked:
            print(f"  Blocked checks ({len(blocked)}): {blocked[:3]}")
        for rec in recs[:3]:
            print(f"    REC: {rec}")
        return passed
    except Exception as ex:
        print(f"  Final Review ERROR: {ex}", file=sys.stderr)
        return False


def main() -> None:
    print(f"doc-compiler orchestrator (with LangGraph QC subgraphs)")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Base: {BASE}")

    target = get_target()
    print(f"Target: {target}")
    if not target.exists():
        print(f"ERROR: Target file does not exist: {target}", file=sys.stderr)
        sys.exit(1)

    # Verify runtime directory structure
    if not RUNTIME.exists():
        print(f"ERROR: Runtime directory not found: {RUNTIME}", file=sys.stderr)
        sys.exit(1)

    stage_results = {}
    failed = False

    for stage_name, stage_module in STAGES:
        passed = run_stage(stage_name, stage_module, target)
        stage_results[stage_name] = passed
        if not passed:
            failed = True
            print(f"\nStage {stage_name} FAILED -- stopping pipeline.")
            break

    # Summary
    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    for name, passed in stage_results.items():
        status = "PASS" if passed else "FAIL"
        icon = " PASS " if passed else " FAIL "
        print(f"  [{icon}] Stage {name}")

    if failed:
        print("\nPipeline FAILED -- some stages did not pass.")
        sys.exit(1)
    else:
        print("\nPipeline COMPLETED -- all stages passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()