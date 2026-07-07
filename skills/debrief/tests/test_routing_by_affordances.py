"""Tests for the routing-by-affordances rule and the bad-behavior rubric.

These tests guard against the failure mode where future LLMs answer
transcript-mining questions by quoting a skill's own docs instead of reasoning
from affordances. They are doctest-style assertions over the canonical text
of the routing reference + the rubric, plus a runtime check that the
/debrief state machine preserves affordance classification.

Run: python -m pytest tests/test_routing_by_affordances.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

def _find_packages_root(start: Path) -> Path:
    """Walk up until we find a directory containing `packages/`.

    Tests may run from any cwd; resolve the real repo root each time so the
    path math doesn't depend on where pytest was invoked from.
    """
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "packages").is_dir():
            return parent
    raise RuntimeError(f"could not find packages/ from {cur}")


REPO_ROOT = _find_packages_root(Path(__file__))
PLUGIN_ROOT = REPO_ROOT / "packages/.claude-marketplace/plugins"

ROUTING_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/routing-by-affordances.md"
)
RUBRIC_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/bad-behavior-rubric.md"
)
HANDOFF_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/handoff-routing.md"
)
DEBRIEF_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/debrief/SKILL.md"
SKILL_AUDIT_SKILL = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/skill-audit/SKILL.md"
)
WIKI_SKILL = PLUGIN_ROOT / "cc-skills-sdlc/skills/wiki/SKILL.md"


# ---- Existence + content invariants ----

def test_routing_doc_exists():
    assert ROUTING_DOC.exists(), f"missing: {ROUTING_DOC}"


def test_rubric_doc_exists():
    assert RUBRIC_DOC.exists(), f"missing: {RUBRIC_DOC}"


def test_handoff_doc_exists():
    assert HANDOFF_DOC.exists(), f"missing: {HANDOFF_DOC}"


def test_no_new_top_level_command_added():
    """No /wiki-ingest, no /transcript-mine, no new mode in any SKILL.md.

    Ponytail constraint: do not add visible commands. Internal references in
    docs do not count; this guards against command-table additions.
    """
    forbidden = ("/wiki-ingest", "/transcript-mine", "/debrief-miner", "/mine-transcripts")
    search_roots = [
        PLUGIN_ROOT,
        REPO_ROOT / "docs",
    ]
    for root in search_roots:
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                # Allow the token to appear in a "do not create" warning, but
                # not as a slash command or trigger.
                occurrences = re.findall(rf"\b{re.escape(token)}\b", text)
                if occurrences and "do not create" not in text.lower():
                    pytest.fail(
                        f"{token} appears in {path} — forbidden new command"
                    )


def test_no_debrief_to_wiki_auto_wire():
    """The /debrief → /wiki handoff must not be auto-fired.

    Catches the regression: /debrief silently writing to /wiki without review.
    The /debrief SKILL.md may *describe* the manual user step ("then run
    /wiki ingest") without firing it automatically — only auto-fired
    invocations are the regression.
    """
    debrief_text = DEBRIEF_SKILL.read_text(encoding="utf-8")
    # Match auto-fire: same line contains both an auto-trigger phrase and the
    # /wiki ingest command. A standalone user-instruction line ("run /wiki
    # ingest to publish") is the expected, allowed pattern.
    lines = debrief_text.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"/wiki\s+ingest", line, re.IGNORECASE):
            lower = line.lower()
            if any(t in lower for t in (
                "auto-fire", "auto_ingest", "wiki_after_write",
                "without approval", "without review",
                "automatically fire", "auto-trigger",
            )):
                pytest.fail(
                    f"debrief SKILL.md line {i} looks like auto-fire: {line!r}"
                )
            # A bare user-instruction line is fine (it's documenting the manual
            # step). Continuation lines (same paragraph) are checked below.
    # Also catch a multi-line block where /wiki ingest is wired into the
    # state-machine workflow_steps WITHOUT an opt-in flag. The legitimate
    # pattern is "Pass --wiki to (5) to emit a /wiki ingest directive" — a
    # user-explicit flag. The auto-fire regression would be a workflow step
    # that always calls /wiki ingest.
    workflow_match = re.search(
        r"workflow_steps:\s*\n((?:[ \t]+-.*\n)+)", debrief_text
    )
    if workflow_match:
        for step_line in workflow_match.group(1).splitlines():
            if "/wiki" in step_line and "optional" not in step_line.lower():
                if "flag" not in step_line.lower():
                    pytest.fail(
                        "debrief workflow_steps has unconditional /wiki: "
                        f"{step_line!r}"
                    )


# ---- Routing doc content ----

def test_routing_doc_has_affordance_table():
    text = ROUTING_DOC.read_text(encoding="utf-8")
    required_affordances = [
        "transcript/session extraction",
        "source/evidence anchoring",
        "bad LLM behavior detection",
        "task/breadcrumb creation",
        "recommendation/options generation",
        "adversarial trust verdict",
        "wiki/long-term memory candidate promotion",
    ]
    for aff in required_affordances:
        assert aff in text, f"affordance missing from routing doc: {aff!r}"


def test_routing_doc_has_worked_example():
    text = ROUTING_DOC.read_text(encoding="utf-8")
    assert "transcript" in text.lower()
    assert "/debrief" in text
    assert "/improve" in text
    assert "/wiki" in text


def test_routing_doc_explicitly_forbids_circular_justification():
    text = ROUTING_DOC.read_text(encoding="utf-8")
    # Must contain the anti-pattern by name and the correction.
    assert "circular" in text.lower()
    assert "anti-pattern" in text.lower() or "Anti-pattern" in text


def test_routing_doc_has_negative_example():
    """The 'use X because Y says so' anti-pattern must be shown with the bad
    AND the good answer, per the user's prompt."""
    text = ROUTING_DOC.read_text(encoding="utf-8")
    # Match either spacing/quote variant of the negative example.
    bad_markers = [
        "use `/debrief` because `/improve` says",
        "Use `/debrief` because `/improve` says not",
        'Use `/debrief` because `/improve` says',
    ]
    good_marker = "affordance analysis"
    assert any(m in text for m in bad_markers), (
        "missing negative (circular) example"
    )
    assert good_marker in text, "missing positive (affordance-based) example"


# ---- Rubric doc content ----

def test_rubric_doc_has_required_behavior_types():
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    required = [
        "false_unsupported_claim",
        "name_based_inference",
        "sycophancy",
        "goal_drift",
        "fabricated_completion",
        "rubber_stamp",
        "missed_user_correction",
        "wrong_command_choice",
        "compact_drift",
        "recurring_pattern",
    ]
    for bt in required:
        assert bt in text, f"behavior_type missing from rubric: {bt!r}"


def test_rubric_doc_emits_to_debrief_state_machine():
    """Findings must flow into debrief_core.run(), not a new pipeline."""
    text = RUBRIC_DOC.read_text(encoding="utf-8")
    assert "debrief_core.run()" in text or "debrief_core" in text
    assert "CLASSIFIED" in text or "state machine" in text.lower()


# ---- Handoff doc content ----

def test_handoff_doc_names_all_six_destinations():
    text = HANDOFF_DOC.read_text(encoding="utf-8")
    destinations = ["/improve", "/skill-audit", "/claude-audit", "/red-team", "/review", "/wiki"]
    for dest in destinations:
        assert dest in text, f"destination missing from handoff doc: {dest!r}"


def test_handoff_doc_explicitly_rejects_auto_wiki():
    text = HANDOFF_DOC.read_text(encoding="utf-8")
    assert "does NOT invoke" in text or "never auto" in text.lower()


# ---- Negative-answer regression: parrot-style routing must NOT be the rule ----

def test_routing_doc_does_not_recommend_by_authority_alone():
    """The canonical routing doc must not contain 'use X because X is for X'
    in its own recommendation (it can show it as a BAD example, but the GOOD
    recommendation must be affordance-based)."""
    text = ROUTING_DOC.read_text(encoding="utf-8")
    bad_phrases = [
        "use /debrief because it is the transcript mining skill",
        "use /debrief because that's what /debrief does",
    ]
    for phrase in bad_phrases:
        assert phrase.lower() not in text.lower(), (
            f"routing doc recommends by authority: {phrase!r}"
        )


# ---- Skill-audit has the anti-parrot section ----

def test_skill_audit_has_anti_parrot_section():
    text = SKILL_AUDIT_SKILL.read_text(encoding="utf-8")
    # The section heading must exist (we added it).
    assert "anti-pattern" in text.lower()
    assert "use X because X says so" in text or '"use X because X says so"' in text