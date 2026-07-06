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


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
            print(f"PASS {fn.__name__}")
    print("all tests passed")
