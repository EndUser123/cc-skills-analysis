#!/usr/bin/env python3
"""Stage I: Emit Proof Metadata for doc-compiler.

Reads: artifact-proof.json + validation-report.json
Emits: proof metadata in index.html directory.
Gate: All prior stages (E, F, H) must pass before this step.
"""
import json, sys
from pathlib import Path
from datetime import datetime

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
PROOF       = BASE / "artifact-proof.json"
VAL_REPORT  = BASE / "validation-report.json"
SOURCE      = BASE / "source-model.json"
PLAN        = BASE / "artifact-plan.json"
INDEX        = BASE / "index.html"

MIN_MUST_TEST = 9  # number of MUST_TEST fields expected in verification_matrix


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    errors = []

    # Check prerequisites
    proof = load_json(PROOF)
    val_report = load_json(VAL_REPORT)
    model = load_json(SOURCE)
    plan = load_json(PLAN)

    # Gate checks
    if not proof:
        errors.append("artifact-proof.json not found or empty")
    if not val_report:
        errors.append("validation-report.json not found or empty")
    if not model:
        errors.append("source-model.json not found or empty")

    # Check external validator passed
    external_passed = val_report.get("passed", False) if val_report else False
    if not external_passed:
        errors.append("Stage H (external critic) did not pass")

    # Check runtime verification
    runtime = proof.get("runtime_verification", {})
    if runtime:
        all_passed = runtime.get("all_passed", False)
        if not all_passed:
            passed = runtime.get("passed", 0)
            total = runtime.get("total", 0)
            errors.append(f"Stage G runtime verification incomplete: {passed}/{total} checks passed")

    # Check verification matrix completeness
    vmatrix = proof.get("verification_matrix", {})
    must_test_keys = [k for k, v in vmatrix.items() if isinstance(v, dict) and "passed" in v]
    missing_must_test = [k for k in must_test_keys if vmatrix[k].get("passed") is None]

    if missing_must_test:
        errors.append(f"verification_matrix missing passed field for: {missing_must_test}")

    # Check for generic reasons
    generic_reasons = ["ok", "verified", "works", "good", "passed", "fine"]
    for key, val in vmatrix.items():
        if isinstance(val, dict) and "reason" in val:
            reason = str(val["reason"]).strip().lower()
            if reason in generic_reasons:
                errors.append(f"verification_matrix.{key}.reason is generic: '{val['reason']}'")

    # Check mandatory fields in proof
    mandatory_fields = [
        ("source_path", str),
        ("artifact_path", str),
        ("generated_at", str),
        ("coverage", dict),
        ("verification_matrix", dict),
        ("toc_state", dict),
        ("css_contract", dict),
    ]

    for field, expected_type in mandatory_fields:
        val = proof.get(field)
        if val is None:
            errors.append(f"mandatory field '{field}' is missing or null")
        elif not isinstance(val, expected_type):
            errors.append(f"mandatory field '{field}' has wrong type: expected {expected_type.__name__}")

    # Check coverage numbers match
    coverage = proof.get("coverage", {})
    steps_declared = coverage.get("steps_declared", coverage.get("workflow_steps_declared", 0))
    steps_rendered = coverage.get("workflow_sections_rendered", 0)

    if steps_declared and steps_rendered and steps_rendered < steps_declared:
        errors.append(f"steps_rendered ({steps_rendered}) < steps_declared ({steps_declared})")

    # Build proof metadata output
    proof_metadata = {
        "skill_name": model.get("name", ""),
        "skill_version": model.get("version", ""),
        "source_path": proof.get("source_path", ""),
        "artifact_path": str(INDEX.resolve()) if INDEX.exists() else "",
        "generated_at": datetime.now().isoformat(),
        "generator_skill_version": "3.0.0",
        "mermaid_version": "11",
        "coverage": coverage,
        "verification_matrix": vmatrix,
        "toc_state": proof.get("toc_state", {}),
        "css_contract": proof.get("css_contract", {}),
        "listener_integrity": proof.get("listener_integrity", {}),
        "critic_results": {
            "mermaid_gate_passed": val_report.get("gate_passed", False) if val_report else False,
            "external_validator_passed": external_passed,
            "validation_report_path": str(VAL_REPORT.resolve()),
            "unresolved_ambiguities": val_report.get("failed_checks", []) if val_report else []
        },
        "stage_i_status": "pass" if not errors else "fail",
        "errors": errors
    }

    out_path = BASE / "proof-metadata.json"
    out_path.write_text(json.dumps(proof_metadata, indent=2), encoding="utf-8")

    if errors:
        print(f"Stage I: FAIL — {len(errors)} errors:")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print(f"Stage I: PASS — proof metadata emitted")
        print(f"Written: {out_path}")
        sys.exit(0)


if __name__ == "__main__":
    main()
