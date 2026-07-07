"""Tests for the capability-preservation mechanical scaffold.

These pin the discriminating facts the rubric in
references/capability-preservation-check.md relies on. They do NOT test
classification (a judgment) — they test that the scaffold surfaces the right
structural signal for each of the three regression shapes from the 2026-07
consolidation:

  - pending_unimplemented    : adv-review (runner/calibrate/harness missing)
  - true_thin_stub           : review-pr  (empty steps, short redirect body)
  - retained_engine_w_deprec : prompt_refiner (empty steps BUT long body)
"""
import json
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path("P:/packages/.claude-marketplace/plugins")
SCRIPTS = PLUGIN_ROOT / "cc-skills-analysis" / "skills" / "skill-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import capability_preservation as cp  # noqa: E402


def test_adv_review_is_pending_unimplemented_not_thin_stub():
    """adv-review must NOT read as a true thin stub: it references a backend
    runner that does not exist on disk. The regression was misclassifying
    this as a stub."""
    r = cp.analyze(PLUGIN_ROOT / "cc-skills-ai-api" / "skills" / "adv-review")
    assert r["workflow_steps_raw"] == "[]"
    # The three pending backends are mentioned but absent.
    for backend in ("runner.py", "calibrate.py", "harness_registry.py"):
        entry = r["referenced_backends"][backend]
        assert entry["mentioned"] is True, backend
        assert entry["exists"] is False, backend
    assert r["py_files_on_disk"] == []
    # Body describes the roster, so it must not trip the thin-stub prose signal.
    assert r["thin_stub_structural_signal"] is False


def test_review_pr_is_structural_thin_stub():
    """review-pr is a genuine thin stub: empty steps, short redirect body,
    no missing backend referenced."""
    r = cp.analyze(PLUGIN_ROOT / "cc-skills-sdlc" / "skills" / "review-pr")
    assert r["workflow_steps_raw"] == "[]"
    assert r["thin_stub_structural_signal"] is True
    # No pending backend advertised.
    missing = {k: v for k, v in r["referenced_backends"].items()
               if v.get("mentioned") and not v.get("exists")}
    assert missing == {}, missing


def test_prompt_refiner_deprecation_header_but_not_thin_stub():
    """prompt_refiner has empty workflow_steps AND a deprecation header, but
    the body retains the load-bearing engine description. The thin-stub
    prose-length signal must be False so it is NOT misclassified as a stub."""
    r = cp.analyze(PLUGIN_ROOT / "cc-skills-architect" / "skills" / "prompt_refiner")
    assert r["workflow_steps_raw"] == "[]"
    assert "deprecated" in r["deprecation_markers"]
    assert r["thin_stub_structural_signal"] is False


def test_missing_skill_dir_returns_error():
    r = cp.analyze(PLUGIN_ROOT / "cc-skills-analysis" / "skills" / "__does_not_exist__")
    assert "error" in r


# ---------------------------------------------------------------------------
# Cross-taxonomy mapping invariant
# ---------------------------------------------------------------------------
# The /skill-audit rubric (Step 2 table) and the /go runtime classifier
# (capability_claim_audit.py, pinned by the go schema enum) describe the same
# capability-preservation domain for different audiences. They intentionally
# do NOT share a class set. This test catches one-sided drift: add a class to
# either taxonomy without a mapping row in the rubric doc -> this fails.

GO_SCHEMA = PLUGIN_ROOT / "cc-skills-sdlc" / "skills" / "go" / "schemas" / "verification-result.schema.json"
RUBRIC_DOC = SCRIPTS.parent / "references" / "capability-preservation-check.md"


def _skill_audit_classes_from_rubric():
    """First-column tokens of the Step 2 class table."""
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    table = text[text.index("## Step 2"):text.index("## Step 3")]
    return set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", table, re.MULTILINE))


def _go_classes_from_schema():
    schema = json.loads(GO_SCHEMA.read_text(encoding="utf-8"))
    enum = (schema["properties"]["capability_audit"]["properties"]["claims"]
            ["items"]["properties"]["classification"]["enum"])
    assert enum, "classification enum missing from go schema"
    return set(enum)


def _parse_mapping_block():
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    block = text[text.index("BEGIN CAPABILITY TAXONOMY MAPPING"):
                 text.index("END CAPABILITY TAXONOMY MAPPING")]
    pairs, gap_go, gap_rubric = [], set(), set()
    for line in block.splitlines():
        line = line.strip()
        if " -> " in line:
            left, right = line.split(" -> ", 1)
            pairs.append((left.strip(), right.strip()))
        elif line.startswith("gap_in_go:"):
            gap_go.add(line.split(":", 1)[1].strip())
        elif line.startswith("gap_in_rubric:"):
            gap_rubric.add(line.split(":", 1)[1].strip())
    return pairs, gap_go, gap_rubric


def test_capability_taxonomy_mapping_covers_both_sides():
    pairs, gap_go, gap_rubric = _parse_mapping_block()
    skill_classes = _skill_audit_classes_from_rubric()
    go_classes = _go_classes_from_schema()

    skill_covered = {left for left, _ in pairs} | gap_go
    go_covered = {right for _, right in pairs} | gap_rubric

    missing_skill = skill_classes - skill_covered
    missing_go = go_classes - go_covered
    assert not missing_skill, f"rubric classes with no mapping entry: {sorted(missing_skill)}"
    assert not missing_go, f"go classes with no mapping entry: {sorted(missing_go)}"


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
            print(f"PASS {fn.__name__}")
    print("all tests passed")
