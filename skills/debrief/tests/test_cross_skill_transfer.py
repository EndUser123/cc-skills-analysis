"""Tests for Cross-Skill Transfer Check (XSTC).

Guards against regressions:
- The canonical template exists and lists all required fields + classifications.
- All 6 retained commands emit an XSTC section pointing at the canonical doc.
- The /improve section is positioned before Suggest (post-Recommendation gate).
- The /debrief section is positioned after the HANDOFF block, before Suggest.
- No new top-level commands were created.
"""

from __future__ import annotations

import re
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

XSTC_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/cross-skill-transfer-check.md"
)

IMPROVE_SKILL = PLUGIN_ROOT / "improve-partner/skills/improve/SKILL.md"
DEBRIEF_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/debrief/SKILL.md"
REDTEAM_CMD = PLUGIN_ROOT / "red-team/commands/red-team.md"
SKILL_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/skill-audit/SKILL.md"
REVIEW_SKILL = PLUGIN_ROOT / "cc-skills-sdlc/skills/review/SKILL.md"
CLAUDE_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/claude-audit/SKILL.md"


# ---- Canonical template invariants ----

def test_xstc_doc_exists():
    assert XSTC_DOC.exists(), f"missing: {XSTC_DOC}"


def test_xstc_doc_has_required_classifications():
    text = XSTC_DOC.read_text(encoding="utf-8")
    required = [
        "local_only",
        "applies_to_related_skills",
        "applies_to_hooks_or_gates",
        "applies_to_command_routing",
        "applies_to_transcript_mining",
        "applies_to_external_review",
        "applies_to_wiki_or_memory",
        "unsure_needs_audit",
    ]
    for c in required:
        assert c in text, f"classification missing from XSTC doc: {c!r}"


def test_xstc_doc_has_required_fields():
    text = XSTC_DOC.read_text(encoding="utf-8")
    required_fields = [
        "classification",
        "affected_surfaces",
        "evidence",
        "why_it_transfers_or_not",
        "owner",
        "recommended_action",
        "validation_step",
        "do_now_or_backlog",
    ]
    for f in required_fields:
        assert f in text, f"field missing from XSTC doc: {f!r}"


def test_xstc_doc_has_three_worked_examples():
    """Examples A (parrot routing), B (lazy stub), C (local one-off) per the spec."""
    text = XSTC_DOC.read_text(encoding="utf-8")
    assert "Example A" in text, "missing Example A (parrot routing)"
    assert "Example B" in text, "missing Example B (lazy stub)"
    assert "Example C" in text, "missing Example C (local one-off)"
    # Example A specifically must include the parrot-routing classification.
    assert "applies_to_command_routing" in text
    # Example C must include local_only.
    assert "classification: local_only" in text


def test_xstc_doc_no_chain_of_thought_requirement():
    """The template must NOT require the model to expose or narrate its chain
    of thought. It should ask for classification + evidence, not reasoning."""
    text = XSTC_DOC.read_text(encoding="utf-8")
    # Forbidden: explicit CoT narration requests.
    forbidden = [
        "explain your reasoning step by step",
        "show your chain of thought",
        "think out loud",
    ]
    for phrase in forbidden:
        assert phrase.lower() not in text.lower(), (
            f"XSTC doc requires CoT narration: {phrase!r}"
        )


def test_xstc_doc_has_evidence_or_audit_rule():
    text = XSTC_DOC.read_text(encoding="utf-8")
    # Rule 1: Evidence or audit (no vibes).
    assert "Evidence or audit" in text or "no vibes" in text.lower()
    # If you cannot cite a file:line, mark unsure_needs_audit.
    assert "unsure_needs_audit" in text


def test_xstc_doc_forbids_circular_routing_evidence():
    text = XSTC_DOC.read_text(encoding="utf-8")
    assert "circular" in text.lower()


# ---- Per-command emit points ----

@pytest.mark.parametrize(
    "path,expected_anchor",
    [
        (IMPROVE_SKILL, "## Cross-Skill Transfer Check (XSTC)"),
        (DEBRIEF_SKILL, "## Cross-Skill Transfer Check (XSTC)"),
        (REDTEAM_CMD, "## Cross-Skill Transfer Check (XSTC)"),
        (SKILL_AUDIT_SKILL, "## Cross-Skill Transfer Check (XSTC)"),
        (REVIEW_SKILL, "## Cross-Skill Transfer Check (XSTC)"),
        (CLAUDE_AUDIT_SKILL, "## Cross-Skill Transfer Check (XSTC)"),
    ],
)
def test_xstc_section_present(path: Path, expected_anchor: str):
    text = path.read_text(encoding="utf-8")
    assert expected_anchor in text, f"{path} missing XSTC anchor"


def test_improve_xstc_before_suggest():
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    suggest_idx = text.find("## Suggest")
    assert xstc_idx != -1 and suggest_idx != -1
    assert xstc_idx < suggest_idx, "/improve XSTC must come before ## Suggest"


def test_debrief_xstc_before_suggest():
    text = DEBRIEF_SKILL.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    suggest_idx = text.find("## Suggest")
    assert xstc_idx != -1 and suggest_idx != -1
    assert xstc_idx < suggest_idx, "/debrief XSTC must come before ## Suggest"


def test_redteam_xstc_does_not_block_verdict():
    """The XSTC is a structured aside in /red-team. The verdict comes first
    (Final output format block)."""
    text = REDTEAM_CMD.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    verdict_idx = text.find("## Final output format")
    assert verdict_idx != -1, "red-team must keep its Final output format section"
    # XSTC must come AFTER verdict (it's an aside in Recommended Next Steps).
    assert xstc_idx > verdict_idx, (
        "/red-team XSTC must not displace the Final output format section"
    )


def test_review_xstc_only_for_recurring_patterns():
    """The /review XSTC section must explicitly say it's for recurring
    patterns only, not every finding — otherwise the gate overfires."""
    text = REVIEW_SKILL.read_text(encoding="utf-8")
    # Locate the XSTC section, then check for "recurring" language.
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    assert xstc_idx != -1
    xstc_section = text[xstc_idx : xstc_idx + 800]  # one chunk is enough
    assert "recurring" in xstc_section.lower(), (
        "/review XSTC must gate on recurring patterns, not every finding"
    )


def test_skill_audit_xstc_advisory_status_disclosed():
    """The /skill-audit XSTC section must include the advisory disclaimer
    so future LLMs don't classify XSTC discipline as runtime-enforced."""
    text = SKILL_AUDIT_SKILL.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    assert xstc_idx != -1
    xstc_section = text[xstc_idx : xstc_idx + 2000]
    assert "advisory" in xstc_section.lower(), (
        "/skill-audit XSTC must declare its advisory status"
    )


def test_redteam_xstc_advisory_status_disclosed():
    """The /red-team XSTC section must include the advisory disclaimer."""
    text = REDTEAM_CMD.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    assert xstc_idx != -1
    xstc_section = text[xstc_idx : xstc_idx + 2000]
    assert "advisory" in xstc_section.lower(), (
        "/red-team XSTC must declare its advisory status"
    )


def test_claude_audit_xstc_advisory_status_disclosed():
    """The /claude-audit XSTC section must include the advisory disclaimer
    AND reference the CEC as the operational counterpart."""
    text = CLAUDE_AUDIT_SKILL.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    assert xstc_idx != -1
    xstc_section = text[xstc_idx : xstc_idx + 2500]
    assert "advisory" in xstc_section.lower(), (
        "/claude-audit XSTC must declare its advisory status"
    )
    assert "CEC" in xstc_section or "completion-evidence" in xstc_section.lower(), (
        "/claude-audit XSTC section should reference CEC as the operational counterpart"
    )


def test_skill_audit_xstc_strongest_owner_claim():
    text = SKILL_AUDIT_SKILL.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    assert xstc_idx != -1
    xstc_section = text[xstc_idx : xstc_idx + 1000]
    assert "canonical owner" in xstc_section.lower(), (
        "/skill-audit should claim canonical ownership for the skill/command/capability layer"
    )


def test_claude_audit_xstc_runtime_layer_only():
    text = CLAUDE_AUDIT_SKILL.read_text(encoding="utf-8")
    xstc_idx = text.find("## Cross-Skill Transfer Check (XSTC)")
    assert xstc_idx != -1
    xstc_section = text[xstc_idx : xstc_idx + 800]
    assert "runtime" in xstc_section.lower() or "hook" in xstc_section.lower(), (
        "/claude-audit XSTC should scope to runtime/hook/config issues"
    )


# ---- No-new-command invariants ----

def test_no_new_top_level_command_added_for_xstc():
    """Replaced by structural allowlist in test_no_new_triggers_structural.py.

    The XSTC-specific forbidden tokens (/xstc, /transfer-check, /cross-skill,
    /generalize-check) are now checked by name in
    test_no_cec_xstc_routing_triggers there. Kept as a pointer for grep-discoverability.
    """
    import test_no_new_triggers_structural as _nt
    _nt.test_no_cec_xstc_routing_triggers()


def test_no_wiki_ingest_for_xstc():
    """Replaced by test_no_wiki_ingest_trigger in test_no_new_triggers_structural.py."""
    import test_no_new_triggers_structural as _nt
    _nt.test_no_wiki_ingest_trigger()


# ---- Worked-example content checks ----

def test_example_a_parrot_routing_evidence_cites_routing_doc():
    """Example A must reference the routing-by-affordances doc so the reader
    can verify the parrot pattern from a concrete artifact."""
    text = XSTC_DOC.read_text(encoding="utf-8")
    assert "routing-by-affordances.md" in text


def test_example_b_lazy_stub_evidence_cites_capability_preservation():
    """Example B must reference the capability-preservation scaffold so the
    reader can verify lazy-stub classification from a concrete artifact."""
    text = XSTC_DOC.read_text(encoding="utf-8")
    assert "capability_preservation.py" in text or "capability-preservation" in text


def test_example_c_local_only_has_do_not_promote_signal():
    """Example C must show `local_only` results in no system-wide change —
    explicitly so future LLMs don't over-generalize from one-off findings."""
    text = XSTC_DOC.read_text(encoding="utf-8")
    # Find Example C section and check for the no-promote signal.
    c_idx = text.find("Example C")
    c_section = text[c_idx : c_idx + 800]
    assert "no system-wide change" in c_section or "do not promote" in c_section.lower(), (
        "Example C must signal no system-wide change for local_one"
    )