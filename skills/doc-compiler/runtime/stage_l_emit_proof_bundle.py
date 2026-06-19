#!/usr/bin/env python3
"""Stage L: Emit Proof Bundle for doc-compiler.

Reads all pipeline artifacts and emits proof-bundle.json.
This is the final stage — it certifies that the pipeline completed successfully.
Emits: proof-bundle.json

Required prior stages: I (static validation), J (runtime validation), K (external critic)
must all pass before this stage can emit a valid bundle.
"""
import json, sys
from pathlib import Path
from datetime import datetime

BASE = Path("P:/packages/.claude-marketplace/plugins/cc-skills-analysis/skills/doc-compiler")

# Pipeline artifacts to check (name -> path)
# Note: validation stages (I, J, K) emit JSON with "passed"/"gate_passed" fields
# Intermediate stages (A-H) emit data artifacts without "passed" fields
ARTIFACTS = {
    "stage_a_source": BASE / "source-model.json",
    "stage_b_doc_model": BASE / "doc-model.json",
    "stage_c_diagram_plan": BASE / "diagram-plan.json",
    "stage_d_guides": BASE / "guides-loaded.json",
    "stage_e_diagrams": BASE / "diagrams.json",
    "stage_f_gate": BASE / "gate-result.json",
    "stage_g_plan": BASE / "artifact-plan.json",
    "stage_h_index": BASE / "index.html",
    "stage_i_static": BASE / "static-validation.json",
    "stage_j_runtime": BASE / "runtime-validation.json",
    "stage_k_report": BASE / "validation-report.json",
    "stage_l_proof_meta": BASE / "proof-metadata.json",
}


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def check_artifact(name: str, path: Path) -> dict:
    """Check an artifact's existence and validity."""
    if not path.exists():
        return {"name": name, "exists": False, "passed": False, "error": "file not found"}
    try:
        if path.suffix in (".json",):
            data = load_json(path)
            # Validation stages have "passed" or "gate_passed"
            passed = data.get("passed", data.get("gate_passed", True))
            return {
                "name": name,
                "exists": True,
                "passed": passed,
                "size_bytes": path.stat().st_size,
                "data_keys": list(data.keys())[:10]
            }
        else:
            # Non-JSON files just need to exist
            return {
                "name": name,
                "exists": True,
                "passed": True,
                "size_bytes": path.stat().st_size,
            }
    except Exception as ex:
        return {"name": name, "exists": True, "passed": False, "error": str(ex)}


def main() -> None:
    print("Stage L: Aggregating proof bundle...")

    artifact_statuses = []
    all_exist = True

    for name, path in ARTIFACTS.items():
        status = check_artifact(name, path)
        artifact_statuses.append(status)
        if not status["exists"]:
            all_exist = False

    # Load key artifacts for summary
    source_model = load_json(ARTIFACTS["stage_a_source"])
    gate_result = load_json(ARTIFACTS["stage_f_gate"])
    static_val = load_json(ARTIFACTS["stage_i_static"])
    runtime_val = load_json(ARTIFACTS["stage_j_runtime"])
    external_val = load_json(ARTIFACTS["stage_k_report"])

    gate_passed = gate_result.get("gate_passed", False)
    static_passed = static_val.get("passed", False)
    runtime_passed = runtime_val.get("runtime_verification", {}).get("all_passed", False)
    external_passed = external_val.get("gate_passed", False)

    # Build proof bundle
    bundle = {
        "kind": "proof-bundle",
        "version": "1.0.0",
        "generated_at": datetime.now().isoformat(),
        "pipeline_completed": all_exist and gate_passed and static_passed and runtime_passed and external_passed,
        "gate_passed": gate_passed and static_passed and runtime_passed and external_passed,
        "skill_name": source_model.get("name", "unknown"),
        "skill_version": source_model.get("version", "0.0.0"),
        "source_kind": source_model.get("kind", "unknown"),
        "source_path": source_model.get("source_path", ""),
        "artifacts": {},
        "validation_summary": {
            "diagram_gate": gate_passed,
            "static_validation": static_passed,
            "runtime_validation": runtime_passed,
            "external_critic": external_passed
        }
    }

    for status in artifact_statuses:
        bundle["artifacts"][status["name"]] = {
            "exists": status["exists"],
            "passed": status.get("passed", False),
            "size_bytes": status.get("size_bytes", 0),
        }

    # Count diagrams
    diagrams_data = load_json(ARTIFACTS["stage_e_diagrams"])
    bundle["diagram_count"] = len(diagrams_data.get("diagrams", []))

    OUT = BASE / "proof-bundle.json"
    OUT.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    final_passed = bundle["gate_passed"]
    print(f"\nStage L: {'PASS — PROOF BUNDLE CERTIFIED' if final_passed else 'FAIL — PIPELINE INCOMPLETE'}")
    print(f"  pipeline_completed={all_exist}")
    print(f"  gate_passed={final_passed}")
    print(f"  diagram_gate={gate_passed}")
    print(f"  static_validation={static_passed}")
    print(f"  runtime_validation={runtime_passed}")
    print(f"  external_critic={external_passed}")
    print(f"  diagrams={bundle['diagram_count']}")

    for status in artifact_statuses:
        icon = "✓" if status["passed"] else "✗"
        exists_icon = "✓" if status["exists"] else "?"
        print(f"  {icon}{exists_icon} {status['name']}")

    print(f"\nWritten: {OUT}")
    sys.exit(0 if final_passed else 1)


if __name__ == "__main__":
    main()