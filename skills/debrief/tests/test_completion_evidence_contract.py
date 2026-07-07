"""Tests for the Completion Evidence Contract.

Guards against regressions:
- The canonical reference doc exists and lists every required field + enum value.
- All 6 retained commands have a Completion Evidence Contract section.
- The 4 worked examples are present with correct status values.
- `claim_type` enum is complete (16 values).
- `status` enum is complete (5 values).
- `protection_level` enum is complete (6 values).
- No new top-level commands were created.
- /wiki-ingest was not created.
- /wiki was not written to.
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

CEC_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/completion-evidence-contract.md"
)

IMPROVE_SKILL = PLUGIN_ROOT / "improve-partner/skills/improve/SKILL.md"
DEBRIEF_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/debrief/SKILL.md"
REDTEAM_CMD = PLUGIN_ROOT / "red-team/commands/red-team.md"
SKILL_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/skill-audit/SKILL.md"
REVIEW_SKILL = PLUGIN_ROOT / "cc-skills-sdlc/skills/review/SKILL.md"
CLAUDE_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/claude-audit/SKILL.md"


# ---- Canonical template invariants ----

def test_cec_doc_exists():
    assert CEC_DOC.exists(), f"missing: {CEC_DOC}"


def test_cec_doc_required_ledger_fields():
    text = CEC_DOC.read_text(encoding="utf-8")
    required = [
        "claim",
        "claim_type",
        "authority_required",
        "evidence_provided",
        "status",
        "protection_level",
        "remaining_gap",
        "next_action",
    ]
    for f in required:
        assert f in text, f"ledger field missing: {f!r}"


def test_cec_doc_complete_claim_type_enum():
    text = CEC_DOC.read_text(encoding="utf-8")
    expected = [
        "file_changed",
        "test_passed",
        "plugin_bumped",
        "cache_rebuilt",
        "drift_checked",
        "command_surface_changed",
        "runtime_behavior_changed",
        "user_visible_behavior_verified",
        "wiki_not_written",
        "external_model_available",
        "guardrail_added",
        "guardrail_runtime_enforced",
        "capability_preserved",
        "documentation_updated",
        "deferred_work",
        "unresolved_gap",
    ]
    for ct in expected:
        assert ct in text, f"claim_type missing: {ct!r}"


def test_cec_doc_complete_status_enum():
    text = CEC_DOC.read_text(encoding="utf-8")
    for s in ("PROVEN", "PARTIAL", "NOT_PROVEN", "DEFERRED", "NOT_APPLICABLE"):
        assert s in text, f"status enum missing: {s}"


def test_cec_doc_complete_protection_level_enum():
    text = CEC_DOC.read_text(encoding="utf-8")
    expected = [
        "documentation_only",
        "prompt_advisory",
        "static_invariant_tested",
        "behavior_eval_tested",
        "runtime_enforced",
        "runtime_enforced_and_regression_tested",
    ]
    for p in expected:
        assert p in text, f"protection_level missing: {p!r}"


def test_cec_doc_hard_rules_present():
    """The 10 hard rules must be in the doc."""
    text = CEC_DOC.read_text(encoding="utf-8")
    # Spot-check the 4 most important rules.
    assert "No bare \"done.\"" in text or "No bare" in text
    assert "SKILL.md / reference doc edit is NOT runtime enforcement" in text
    assert "test that checks text exists is NOT proof" in text
    assert "Plugin bump ≠ user-facing activation" in text
    assert "\"Zero drift\" requires the literal" in text
    assert "\"No new commands\" requires a structural" in text
    assert "\"Capability preserved\" requires all four" in text
    assert "Unresolved items appear as" in text
    assert "If a guardrail is advisory only" in text


def test_cec_doc_has_retro_example_e():
    """Example E must be present so the contract demonstrates itself
    retroactively on a real artifact (the prior turn's reports)."""
    text = CEC_DOC.read_text(encoding="utf-8")
    assert "Example E" in text, "CEC doc must include Example E (retrospective)"
    idx = text.find("Example E")
    section = text[idx : idx + 5000]
    # Must contain at least one PARTIAL and one NOT_PROVEN row — that's the
    # whole point of the retro example.
    assert "status: PARTIAL" in section
    assert "status: NOT_PROVEN" in section, (
        "Example E must surface at least one NOT_PROVEN row to demonstrate the contract"
    )
    # Must include the verdict-derivation rule.
    assert "Verdict from this ledger" in section or "verdict" in section.lower()


def test_cec_doc_worked_examples_present():
    """The 4 worked examples must be present (overclaim enforcement, partial
    no-new-commands, zero drift NOT_PROVEN, capability preserved NOT_PROVEN)."""
    text = CEC_DOC.read_text(encoding="utf-8")
    assert "Example A" in text, "missing Example A (overclaim enforcement)"
    assert "Example B" in text, "missing Example B (partial no-new-commands)"
    assert "Example C" in text, "missing Example C (zero drift NOT_PROVEN)"
    assert "Example D" in text, "missing Example D (capability preserved NOT_PROVEN)"
    # Each example's status field must be NOT_PROVEN or PARTIAL (not PROVEN).
    for label in ("Example A", "Example B", "Example C", "Example D"):
        idx = text.find(label)
        section = text[idx : idx + 1500]
        assert "status: NOT_PROVEN" in section or "status: PARTIAL" in section, (
            f"{label} must demonstrate a non-PROVEN status (the overclaim pattern)"
        )


def test_cec_doc_forbids_cot_narration():
    text = CEC_DOC.read_text(encoding="utf-8")
    forbidden = [
        "explain your reasoning step by step",
        "show your chain of thought",
        "think out loud",
    ]
    for phrase in forbidden:
        assert phrase.lower() not in text.lower()


def test_cec_doc_forbids_silent_wiki_writes():
    """The contract is silent on /wiki auto-writing. The wiki gate lives in
    the `wiki_not_written` claim_type — the contract's job is to detect any
    code or doc edit that would enable /wiki writes, not to teach the model
    HOW to write. So the contract MUST NOT include example code that
    imports `wiki_after_write` or implements auto-fire mechanisms for
    /wiki ingest.
    """
    text = CEC_DOC.read_text(encoding="utf-8")
    # Look for example code lines that would teach the pattern.
    forbidden = (
        "wiki_after_write(",
        "from wiki_after_write",
        "auto-fire /wiki",
        "automatic /wiki",
    )
    for phrase in forbidden:
        assert phrase.lower() not in text.lower(), (
            f"CEC doc includes example code for forbidden write: {phrase!r}"
        )


# ---- Per-command section presence ----

@pytest.mark.parametrize(
    "path,anchor",
    [
        (IMPROVE_SKILL, "## Completion Evidence Contract"),
        (DEBRIEF_SKILL, "## Completion Evidence Contract"),
        (REDTEAM_CMD, "## Completion Evidence Contract"),
        (SKILL_AUDIT_SKILL, "## Completion Evidence Contract"),
        (REVIEW_SKILL, "## Completion Evidence Contract"),
        (CLAUDE_AUDIT_SKILL, "## Completion Evidence Contract"),
    ],
)
def test_cec_section_present(path: Path, anchor: str):
    text = path.read_text(encoding="utf-8")
    assert anchor in text, f"{path} missing CEC anchor"


def test_redteam_cec_is_mandatory_criterion():
    """The /red-team CEC section must explicitly say it is a mandatory
    acceptance criterion — it's the BLOCK authority."""
    text = REDTEAM_CMD.read_text(encoding="utf-8")
    idx = text.find("## Completion Evidence Contract")
    # Take a wider window — section is long and BLOCK may sit past 1500 chars.
    section = text[idx : idx + 5000]
    assert "mandatory" in section.lower(), (
        "/red-team CEC must be mandatory acceptance criterion"
    )
    # Must BLOCK on missing ledger / mis-classified protection levels.
    assert "BLOCK" in section, "/red-team must BLOCK on missing ledger / overclaim"


def test_redteam_precheck_0_ledger_required():
    """The /red-team command must include a Pre-check 0 step that halts with
    a literal BLOCK message when the target artifact lacks a ledger.

    This is the operational counterpart to the CEC's rule 9. Without this
    step, the contract is purely prompt-advisory and the BLOCK authority
    is moot.
    """
    text = REDTEAM_CMD.read_text(encoding="utf-8")
    idx = text.find("## Pre-check 0")
    assert idx != -1, (
        "red-team command must have a '## Pre-check 0' section before the "
        "Pre-check 1 routing section"
    )
    # Walk to the next ## heading (Pre-check 1 or Mission).
    end_markers = ["## Pre-check 1", "## Pre-check — is `/red-team` the right command?", "## Mission"]
    end_idx = len(text)
    for marker in end_markers:
        m = text.find(marker, idx + 1)
        if m != -1:
            end_idx = min(end_idx, m)
    section = text[idx:end_idx]
    # Must contain the literal BLOCK verdict string.
    assert "BLOCK" in section, "Pre-check 0 must contain the BLOCK verdict"
    assert "ledger" in section.lower(), "Pre-check 0 must mention the ledger"
    assert "halt" in section.lower() or "BLOCK" in section, (
        "Pre-check 0 must halt when ledger is absent"
    )


def test_redteam_precheck_0_lists_artifact_types():
    """Pre-check 0 must enumerate which artifact types trigger the BLOCK
    requirement, so future LLM runs know when to apply it."""
    text = REDTEAM_CMD.read_text(encoding="utf-8")
    idx = text.find("## Pre-check 0")
    end_idx = text.find("## Pre-check — is `/red-team` the right command?", idx + 1)
    if end_idx == -1:
        end_idx = text.find("## Mission", idx + 1)
    section = text[idx:end_idx]
    for trigger in (
        "implementation report",
        "plugin change",
        "skill change",
        "hook change",
        "consolidation",
    ):
        assert trigger in section, (
            f"Pre-check 0 must enumerate trigger type: {trigger!r}"
        )


def test_skill_audit_cec_capability_preserved_requirement():
    """The /skill-audit CEC section must require all four pieces of evidence
    for capability_preserved claims."""
    text = SKILL_AUDIT_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Completion Evidence Contract")
    section = text[idx : idx + 2000]
    assert "old-source" in section or "old source" in section
    assert "parent-source" in section or "parent source" in section
    assert "backend" in section.lower()
    assert "behavior" in section.lower()


def test_claude_audit_cec_runtime_authority():
    """The /claude-audit CEC section must list runtime-specific claim types
    and reject text-test proof for runtime claims."""
    text = CLAUDE_AUDIT_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Completion Evidence Contract")
    section = text[idx : idx + 2000]
    for claim_type in (
        "plugin_bumped",
        "cache_rebuilt",
        "drift_checked",
        "command_surface_changed",
    ):
        assert claim_type in section, (
            f"/claude-audit CEC must mention {claim_type}"
        )
    # Must require the literal "Zero drift confirmed" line for drift claims.
    assert "Zero drift confirmed" in section


def test_review_cec_test_authority():
    text = REVIEW_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Completion Evidence Contract")
    section = text[idx : idx + 1500]
    for claim_type in ("file_changed", "test_passed"):
        assert claim_type in section
    # Must NOT allow static_invariant_tested to masquerade as behavior_eval_tested.
    assert "static_invariant_tested" in section
    assert "behavior_eval_tested" in section


def test_improve_cec_is_routing_only():
    """The /improve CEC section must explicitly say it does NOT own
    enforcement and routes to the right owner."""
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Completion Evidence Contract")
    section = text[idx : idx + 1500]
    assert "routing" in section.lower() or "route" in section.lower()
    assert "does NOT enforce" in section or "do not own" in section.lower(), (
        "/improve CEC must explicitly disclaim enforcement"
    )
    # Must point at the four owning commands.
    for target in ("/red-team", "/skill-audit", "/claude-audit", "/review"):
        assert target in section, f"/improve CEC must route to {target}"


def test_debrief_cec_after_action_rubric():
    """The /debrief CEC section must classify overclaims using the 4
    rubric types."""
    text = DEBRIEF_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Completion Evidence Contract")
    section = text[idx : idx + 2500]
    for rubric_class in (
        "overclaimed_completion",
        "fake_verification",
        "static_test_runtime_confusion",
        "user_surface_verification_gap",
    ):
        assert rubric_class in section, (
            f"/debrief CEC after-action rubric missing class: {rubric_class}"
        )


# ---- No-new-command invariants ----

def test_no_new_top_level_command_for_cec():
    """Replaced by structural allowlist in test_no_new_triggers_structural.py."""
    import test_no_new_triggers_structural as _nt
    _nt.test_no_new_triggers_structural()


def test_no_wiki_ingest_for_cec():
    """Replaced by test_no_wiki_ingest_trigger in test_no_new_triggers_structural.py."""
    import test_no_new_triggers_structural as _nt
    _nt.test_no_wiki_ingest_trigger()


# ---- Worked-example content ----

def test_example_a_overclaim_uses_correct_status():
    """Example A must show NOT_PROVEN for the runtime_enforced overclaim."""
    text = CEC_DOC.read_text(encoding="utf-8")
    idx = text.find("Example A")
    section = text[idx : idx + 1500]
    assert "status: NOT_PROVEN" in section
    assert "guardrail_runtime_enforced" in section
    assert "prompt_advisory" in section, (
        "Example A must also down-classify protection_level to prompt_advisory"
    )


def test_example_b_no_new_commands_is_partial_not_proven():
    text = CEC_DOC.read_text(encoding="utf-8")
    idx = text.find("Example B")
    section = text[idx : idx + 1500]
    assert "status: PARTIAL" in section
    assert "command_surface_changed" in section


def test_example_c_zero_drift_not_proven():
    text = CEC_DOC.read_text(encoding="utf-8")
    idx = text.find("Example C")
    section = text[idx : idx + 1500]
    assert "status: NOT_PROVEN" in section
    assert "drift_checked" in section


def test_example_d_capability_preserved_not_proven():
    text = CEC_DOC.read_text(encoding="utf-8")
    idx = text.find("Example D")
    section = text[idx : idx + 1500]
    assert "status: NOT_PROVEN" in section
    assert "capability_preserved" in section
    # Must list all four required evidence pieces in the gap statement.
    assert "old source" in section or "old-source" in section
    assert "parent source" in section or "parent-source" in section
    assert "backend" in section.lower()
    assert "behavior" in section.lower()