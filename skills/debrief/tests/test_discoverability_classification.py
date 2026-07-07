"""Tests for the discoverability classification rule.

Guards against regressions:
- The canonical reference doc exists and lists DISCOVERABLE + USER_ONLY.
- The bad-behavior-rubric splits lazy_shallow_thinking into the two new classes.
- /go, /improve, /skill-audit, /claude-audit each have a discoverability section.
- The pushback-test detection cue is documented.
- No new top-level commands created.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _find_packages_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "packages").is_dir():
            return parent
    raise RuntimeError(f"could not find packages/ from {cur}")


REPO_ROOT = _find_packages_root(Path(__file__))
PLUGIN_ROOT = REPO_ROOT / "packages/.claude-marketplace/plugins"

DISC_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/discoverability-classification.md"
)
RUBRIC_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/bad-behavior-rubric.md"
)
GO_SKILL = PLUGIN_ROOT / "cc-skills-sdlc/skills/go/SKILL.md"
IMPROVE_SKILL = PLUGIN_ROOT / "improve-partner/skills/improve/SKILL.md"
SKILL_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/skill-audit/SKILL.md"
CLAUDE_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/claude-audit/SKILL.md"


# ---- Canonical doc invariants ----

def test_disc_doc_exists():
    assert DISC_DOC.exists(), f"missing: {DISC_DOC}"


def test_disc_doc_has_both_classes():
    text = DISC_DOC.read_text(encoding="utf-8")
    assert "DISCOVERABLE" in text
    assert "USER_ONLY" in text


def test_disc_doc_has_pushback_test():
    """The detection cue (pushback test) must be documented."""
    text = DISC_DOC.read_text(encoding="utf-8")
    assert "pushback" in text.lower()
    assert "without receiving new information" in text.lower() or "without new info" in text.lower()


def test_disc_doc_has_contract_rule():
    """The core rule: asking for a DISCOVERABLE fact = inventing it."""
    text = DISC_DOC.read_text(encoding="utf-8")
    assert "contract violation equal to inventing" in text.lower() or "equal to inventing" in text.lower()


def test_disc_doc_has_ownership_table():
    text = DISC_DOC.read_text(encoding="utf-8")
    assert "/go" in text
    assert "/debrief" in text
    assert "/improve" in text
    assert "/skill-audit" in text
    assert "/claude-audit" in text


def test_disc_doc_has_worked_examples():
    """Positive (violation), negative (good behavior), valid blocker."""
    text = DISC_DOC.read_text(encoding="utf-8")
    assert "Positive example" in text
    assert "Negative example" in text
    assert "Valid blocker" in text or "USER_ONLY" in text


def test_disc_doc_does_not_weaken_verification():
    """The rule must explicitly preserve verification discipline — it must NOT
    teach models to skip verification."""
    text = DISC_DOC.read_text(encoding="utf-8")
    assert "does NOT weaken verification" in text or "refusing to act on unverified" in text


# ---- Rubric split ----

def test_rubric_has_discoverable_fact_offloading():
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    assert "discoverable_fact_offloading" in text, (
        "rubric must include the new discoverable_fact_offloading class"
    )


def test_rubric_has_unsupported_or_shallow_claim():
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    assert "unsupported_or_shallow_claim" in text


def test_rubric_removed_old_lazy_shallow_thinking():
    """The old lazy_shallow_thinking category must be gone — it was split."""
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    # The category table row must not contain the old name as a behavior_type.
    assert "| `lazy_shallow_thinking` |" not in text, (
        "lazy_shallow_thinking must be split, not kept as a category"
    )


def test_rubric_severity_assigns_block_to_offloading():
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    # discoverable_fact_offloading must appear in the BLOCK severity line.
    block_section = text[text.find("**BLOCK**"):text.find("**REVISE**")]
    assert "discoverable_fact_offloading" in block_section, (
        "discoverable_fact_offloading must be BLOCK severity"
    )


# ---- Per-command section presence ----

@pytest.mark.parametrize(
    "path,anchor",
    [
        (GO_SKILL, "Discoverability"),
        (IMPROVE_SKILL, "Discoverability"),
        (SKILL_AUDIT_SKILL, "Discoverability"),
        (CLAUDE_AUDIT_SKILL, "Discoverability"),
    ],
)
def test_disc_section_present(path: Path, anchor: str):
    text = path.read_text(encoding="utf-8")
    assert anchor in text, f"{path} missing Discoverability section"


def test_go_has_missing_input_emit_fields():
    """/go must list the 5 missing_input emit fields."""
    text = GO_SKILL.read_text(encoding="utf-8")
    idx = text.find("Discoverability")
    section = text[idx:idx+2000]
    for field in ("missing_input", "discoverability", "discovery_attempted", "evidence", "remaining_need"):
        assert field in section, f"/go discoverability section missing field: {field}"


def test_improve_routes_does_not_absorb():
    """/improve must route to /debrief, /skill-audit, /claude-audit — not absorb."""
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    idx = text.find("Discoverability")
    section = text[idx:idx+1500]
    assert "does NOT absorb" in section or "do not absorb" in section.lower()
    assert "/debrief" in section


def test_skill_audit_flags_ask_before_discover():
    """/skill-audit must flag instructions that ask before local discovery."""
    text = SKILL_AUDIT_SKILL.read_text(encoding="utf-8")
    idx = text.find("Discoverability")
    section = text[idx:idx+1500]
    assert "ask the user" in section.lower() or "before attempting" in section.lower()


# ---- No new commands ----

def test_no_new_command_for_discoverability():
    """The rule must not introduce a new slash command."""
    import re
    forbidden = ("/discover", "/discoverability", "/classify-input", "/missing-input")
    for path in PLUGIN_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if re.search(
                rf"triggers:\s*\n[\s\S]{{0,200}}-\s*{re.escape(token)}",
                text,
            ):
                pytest.fail(f"{token} appears as a trigger in {path}")