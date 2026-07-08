"""Tests for the report-contracts meta-reference + the evidence-contract rename
+ the Deeper Abstraction Check (Task 3, parts A–D).

Guards against regressions:
- A: the two non-CEC `evidence-contract.md` files were renamed and every
  remaining `evidence-contract.md` token lives inside `completion-evidence-contract.md`.
- B: `/ship` appears in the CEC "Where to emit" table; the `activation_verified`
  gap is noted honestly.
- C: `report-contracts.md` exists, names the four-element pattern, lists all six
  advisory contracts, and states the advisory/enforced separation.
- D: the Deeper Abstraction Check exists in `/ask` with the required question +
  seven fields + the don't-paste-rule rule, and `/improve` carries a pointer.
- No new top-level command; no /wiki-ingest; no automatic /wiki write introduced.
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

DEBRIEF_REFS = PLUGIN_ROOT / "cc-skills-analysis/skills/debrief/references"
CEC_DOC = DEBRIEF_REFS / "completion-evidence-contract.md"
REPORT_CONTRACTS_DOC = DEBRIEF_REFS / "report-contracts.md"
TPA_DOC = DEBRIEF_REFS / "thought-partner-addendum.md"
XSTC_DOC = DEBRIEF_REFS / "cross-skill-transfer-check.md"
DISCOVERABILITY_DOC = DEBRIEF_REFS / "discoverability-classification.md"
ROUTING_DOC = DEBRIEF_REFS / "routing-by-affordances.md"

ASK_SKILL = PLUGIN_ROOT / "cc-skills-architect/skills/ask/SKILL.md"
IMPROVE_SKILL = PLUGIN_ROOT / "improve-partner/skills/improve/SKILL.md"

PRE_MORTEM_REFS = PLUGIN_ROOT / "cc-skills-sdlc/skills/pre-mortem/references"
GIT_BATCH_REFS = PLUGIN_ROOT / "cc-skills-utils/skills/git/references/batch"


# ---- Part A: evidence-contract rename ----

def test_renamed_pre_mortem_file_exists():
    assert (PRE_MORTEM_REFS / "pre-mortem-evidence-tiers.md").exists(), (
        "pre-mortem/references/evidence-contract.md should be renamed to "
        "pre-mortem-evidence-tiers.md"
    )


def test_renamed_batch_file_exists():
    assert (GIT_BATCH_REFS / "batch-evidence-format.md").exists(), (
        "git/references/batch/evidence-contract.md should be renamed to "
        "batch-evidence-format.md"
    )


def test_old_pre_mortem_evidence_contract_removed():
    assert not (PRE_MORTEM_REFS / "evidence-contract.md").exists(), (
        "pre-mortem/references/evidence-contract.md must be removed (renamed)"
    )


def test_old_batch_evidence_contract_removed():
    assert not (GIT_BATCH_REFS / "evidence-contract.md").exists(), (
        "git/references/batch/evidence-contract.md must be removed (renamed)"
    )


def test_renamed_files_carry_disambiguation_note():
    """Both renamed files must point readers to the CEC at the top."""
    for path in (
        PRE_MORTEM_REFS / "pre-mortem-evidence-tiers.md",
        GIT_BATCH_REFS / "batch-evidence-format.md",
    ):
        text = path.read_text(encoding="utf-8")
        head = text[:600]
        assert "Completion Evidence Contract" in head, (
            f"{path.name} must disambiguate from the CEC in the top note"
        )
        assert "completion-evidence-contract.md" in head, (
            f"{path.name} top note must link the CEC path"
        )


def test_no_ambiguous_evidence_contract_references():
    """Every `evidence-contract.md` token in the marketplace must be inside a
    `completion-evidence-contract.md` reference (or a forward-pointer to it).

    This is the core anti-stale-link invariant: after the rename, the bare
    token must never point at a deleted file.
    """
    bad: list[str] = []
    for path in PLUGIN_ROOT.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in re.finditer(r"evidence-contract\.md", text):
            start = max(0, m.start() - 25)
            window = text[start : m.end()]
            if "completion-evidence-contract.md" in window:
                continue
            bad.append(f"{path}: ...{window}...")
    assert not bad, (
        "Found `evidence-contract.md` tokens not scoped to "
        "completion-evidence-contract.md:\n" + "\n".join(bad)
    )


# ---- Part B: /ship in the CEC emit table ----

def test_ship_in_cec_emit_table():
    text = CEC_DOC.read_text(encoding="utf-8")
    idx = text.find("## Where to emit")
    assert idx != -1, "CEC missing '## Where to emit' table"
    section = text[idx : idx + 3000]
    assert "| `/ship` |" in section, (
        "CEC 'Where to emit' table must include a /ship row"
    )


def test_ship_row_names_deploy_claim_types():
    text = CEC_DOC.read_text(encoding="utf-8")
    idx = text.find("## Where to emit")
    section = text[idx : idx + 3000]
    ship_idx = section.find("`/ship`")
    row = section[ship_idx : ship_idx + 400]
    for claim_type in (
        "plugin_bumped",
        "cache_rebuilt",
        "drift_checked",
        "runtime_behavior_changed",
        "user_visible_behavior_verified",
    ):
        assert claim_type in row, f"/ship row must name claim type: {claim_type!r}"


def test_cec_notes_activation_verified_gap_honestly():
    """The /ship row uses user_visible_behavior_verified for the conceptual
    activation_verified claim; the CEC must say that gap out loud rather than
    silently overloading the enum."""
    text = CEC_DOC.read_text(encoding="utf-8")
    assert "activation_verified" in text, (
        "CEC must name the missing activation_verified claim type honestly"
    )
    assert "does not exist" in text.lower() or "does not" in text.lower(), (
        "CEC must state plainly that activation_verified is not an enum value"
    )


# ---- Part C: report-contracts meta-reference ----

def test_report_contracts_doc_exists():
    assert REPORT_CONTRACTS_DOC.exists(), f"missing: {REPORT_CONTRACTS_DOC}"


def test_report_contracts_names_the_pattern():
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    for element in (
        "canonical reference",
        "per-command pointer",
        "advisory status",
        "static invariant test",
    ):
        assert element in text.lower() or element in text, (
            f"report-contracts.md must name pattern element: {element!r}"
        )


def test_report_contracts_lists_all_six_contracts():
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    for needle in (
        "completion-evidence-contract.md",
        "thought-partner-addendum.md",
        "Partner Posture Map",
        "cross-skill-transfer-check.md",
        "discoverability-classification.md",
        "routing-by-affordances.md",
    ):
        assert needle in text, (
            f"report-contracts.md registry missing contract: {needle!r}"
        )


def test_report_contracts_states_advisory_separation():
    """The doc must separate prompt-advisory from runtime-enforced and say none
    of the six contracts are runtime-enforced today."""
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "prompt-advisory" in lowered or "prompt_advisory" in lowered
    assert "runtime_enforced" in text or "runtime-enforced" in lowered
    # Must explicitly say the six contracts are advisory (not silently enforced).
    assert "prompt-advisory" in lowered and (
        "none of the six" in lowered or "not runtime" in lowered
        or "no runtime" in lowered
    )


def test_report_contracts_forbids_overclaim_of_enforcement():
    """The doc must carry the falsification condition: claiming runtime_enforced
    without a matching hook is the central overclaim."""
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    idx = text.find("## Falsification")
    assert idx != -1, "report-contracts.md must have a Falsification section"
    section = text[idx:]
    assert "runtime_enforced" in section or "runtime-enforced" in section.lower()


# ---- Part D: Deeper Abstraction Check ----

def test_deeper_abstraction_check_in_ask():
    text = ASK_SKILL.read_text(encoding="utf-8")
    assert "## Deeper Abstraction Check" in text, (
        "/ask must own the Deeper Abstraction Check section"
    )


def test_deeper_abstraction_check_required_question():
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    section = text[idx : idx + 3000]
    assert "What deeper abstraction does this local concept imply?" in section, (
        "Deeper Abstraction Check must pose the required question verbatim"
    )


def test_deeper_abstraction_check_required_fields():
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    section = text[idx : idx + 3000]
    for field in (
        "local_concept",
        "deeper_abstraction",
        "affected_surfaces",
        "current_owner",
        "evidence",
        "recommended_action",
    ):
        assert field in section, f"Deeper Abstraction Check missing field: {field!r}"


def test_deeper_abstraction_check_disposition_enum():
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    section = text[idx : idx + 3500]
    for value in (
        "should_be_shared_reference",
        "pointer_only",
        "runtime_hook",
        "test",
        "backlog",
        "do_nothing",
    ):
        assert value in section, (
            f"Deeper Abstraction Check disposition enum missing: {value!r}"
        )


def test_deeper_abstraction_check_states_the_rule():
    """The check must forbid the 'where do we paste this rule?' framing."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    section = text[idx : idx + 3000]
    assert "where should we paste this rule" in section.lower(), (
        "Deeper Abstraction Check must name the forbidden paste-rule framing"
    )
    assert "reusable abstraction or ownership model" in section.lower(), (
        "Deeper Abstraction Check must reframe toward reusable abstraction"
    )


def test_improve_points_at_deeper_abstraction_check():
    """/improve owns durable improvement work — it must carry a pointer to the
    /ask-owned check, not re-define the fields."""
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    assert "## Deeper Abstraction Check" in text, (
        "/improve must carry a Deeper Abstraction Check pointer section"
    )
    idx = text.find("## Deeper Abstraction Check")
    section = text[idx : idx + 1500]
    assert "ask/SKILL.md" in section or "/ask" in section, (
        "/improve pointer must reference /ask as the owner"
    )
    # /improve must NOT re-define the full field set (it's a pointer, not a copy).
    assert "local_concept" not in section, (
        "/improve pointer must not duplicate the canonical fields (pointer-only)"
    )


# ---- No-regression invariants ----

def test_no_new_top_level_command():
    import test_no_new_triggers_structural as _nt
    _nt.test_no_new_triggers_structural()


def test_no_wiki_ingest_trigger():
    import test_no_new_triggers_structural as _nt
    _nt.test_no_wiki_ingest_trigger()


def test_no_new_report_contract_triggers():
    """This work must not introduce commands for the new abstractions."""
    import test_no_new_triggers_structural as _nt
    found = _nt._enumerate_triggers(PLUGIN_ROOT)
    for trigger in (
        "/report-contract",
        "/report-contracts",
        "/deeper-abstraction",
        "/abstraction-check",
        "/meta-reference",
        "/coverage-authority",
        "/activation-truth",
        "/bounded-action",
    ):
        assert trigger not in found, (
            f"{trigger} introduced as a trigger — report-contracts work must "
            f"not add new commands"
        )


def test_no_automatic_wiki_write_introduced():
    """None of the new docs/sections may teach an auto-fire /wiki mechanism."""
    candidates = [
        REPORT_CONTRACTS_DOC,
        ASK_SKILL,
        IMPROVE_SKILL,
        PRE_MORTEM_REFS / "pre-mortem-evidence-tiers.md",
        GIT_BATCH_REFS / "batch-evidence-format.md",
    ]
    forbidden = (
        "wiki_after_write(",
        "from wiki_after_write",
        "auto-fire /wiki",
        "automatic /wiki",
    )
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase not in text, (
                f"{path.name} introduces forbidden /wiki write pattern: {phrase!r}"
            )


# ---- Part F: Three new vocabularies in /ask ----

def test_coverage_authority_in_ask():
    """Coverage Authority must be defined in the Deeper Abstraction Check area."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    assert idx != -1, "Deeper Abstraction Check missing from /ask"
    section = text[idx:]
    assert "coverage_authority" in section, (
        "Deeper Abstraction Check must include coverage_authority field"
    )
    for value in ("sampled", "targeted", "whole_repo_static", "runtime_surface", "live_behavior"):
        assert value in section, f"coverage_authority enum missing: {value!r}"


def test_coverage_authority_prohibits_full_coverage_without_authority():
    """The Coverage Authority section must forbid bare 'full coverage' claims."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("### Coverage Authority")
    assert idx != -1, "### Coverage Authority section missing from /ask"
    section = text[idx : idx + 2000]
    assert "full coverage" in section.lower(), (
        "Coverage Authority must address the 'full coverage' anti-pattern"
    )
    assert "without an authority" in section.lower() or "without an authority label" in section.lower() or "prohibited" in section.lower(), (
        "Coverage Authority must explicitly prohibit bare 'full coverage' claims"
    )


def test_activation_truth_model_in_ask():
    """Activation Truth Model must be defined in the Deeper Abstraction Check area."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    section = text[idx:]
    assert "activation_truth_layer" in section, (
        "Deeper Abstraction Check must include activation_truth_layer field"
    )
    for value in ("source_changed", "cache_rebuilt", "plugin_loaded", "command_resolves", "behavior_observed"):
        assert value in section, f"activation_truth_layer enum missing: {value!r}"


def test_activation_truth_model_prohibits_source_only_live_claim():
    """The Activation Truth section must forbid claiming 'live' from a source edit."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("### Activation Truth Model")
    assert idx != -1, "### Activation Truth Model section missing from /ask"
    section = text[idx : idx + 2000]
    assert "source_changed" in section.lower() or "source edit" in section.lower() or "source edit" in section, (
        "Activation Truth Model must address the source-edit-only overclaim"
    )
    assert "prohibited" in section.lower() or "must not" in section.lower() or "forbidden" in section.lower(), (
        "Activation Truth Model must explicitly state what is prohibited"
    )


def test_bounded_action_continuation_in_ask():
    """Bounded Action Continuation must exist in /ask STEP 5 or nearby."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    assert "Bounded Action Continuation" in text, (
        "/ask must own the Bounded Action Continuation rule"
    )
    idx = text.find("Bounded Action Continuation")
    section = text[idx : idx + 2000]
    # Must name the four conditions: authorized, bounded, reversible, directly implied
    for keyword in ("authorized", "bounded", "reversible", "directly implied"):
        assert keyword in section.lower() or keyword in section, (
            f"Bounded Action Continuation must name condition: {keyword!r}"
        )


def test_bounded_action_continuation_prohibits_deferral_after_authorized():
    """The rule must explicitly address the 'say the word' deferral pattern."""
    text = ASK_SKILL.read_text(encoding="utf-8")
    idx = text.find("Bounded Action Continuation")
    section = text[idx : idx + 2000]
    assert "say the word" in section.lower() or "deferral" in section.lower() or "re-ask" in section.lower(), (
        "Bounded Action Continuation must address the deferral-after-authorization failure pattern"
    )


def test_improve_pointer_mentions_report_contracts_vocabularies():
    """/improve must reference the three new vocabularies in its Deeper Abstraction Check pointer."""
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Deeper Abstraction Check")
    assert idx != -1, "/improve missing Deeper Abstraction Check section"
    section = text[idx : idx + 2000]
    # At minimum, one of the three field names must appear (snake_case or title-case)
    found_any = any(
        kw in section
        for kw in (
            "coverage_authority",
            "Coverage Authority",
            "activation_truth_layer",
            "Activation Truth",
            "bounded_actions_completed_or_deferred",
            "Bounded Action Continuation",
        )
    )
    assert found_any, (
        "/improve Deeper Abstraction Check pointer should reference the new vocabularies"
    )


# ---- Part G: Feedback Loop / Harness Calibration Addendum ----

def test_feedback_loop_addendum_section_exists():
    """report-contracts.md must carry the Feedback Loop Addendum section."""
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    assert "## Feedback Loop / Harness Calibration Addendum" in text, (
        "report-contracts.md must include the Feedback Loop Addendum section"
    )


def test_feedback_loop_addendum_names_all_seven_mechanisms():
    """The addendum must name all seven feedback-loop mechanisms."""
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    idx = text.find("## Feedback Loop / Harness Calibration Addendum")
    assert idx != -1, "Feedback Loop Addendum section missing"
    section = text[idx:]
    for mechanism in (
        "Runtime Ground Truth Freshness",
        "Public Baseline Taxonomy",
        "Two-Layer Gold Corpus",
        "Disallowed Conclusions",
        "Epistemic Hook Calibration",
        "Local JSONL Verification Packets",
        "Deterministic-First / LLM-Last",
    ):
        assert mechanism in section, (
            f"Feedback Loop Addendum missing mechanism: {mechanism!r}"
        )


def test_feedback_loop_addendum_cites_real_artifacts():
    """Each cited artifact path in the addendum must point at a real file/dir.

    These are the artifacts the addendum's runtime-status claims depend on.
    If any is renamed/moved, the addendum's falsification condition trips and
    this test fails so the doc is updated, not silently broken.
    """
    rt = REPO_ROOT / ".claude/hooks/analysis/runtime-ground-truth.md"
    assert rt.exists(), f"addendum cites missing artifact: {rt}"
    gold = REPO_ROOT / ".data/evals/gold"
    assert gold.exists() and any(gold.iterdir()), (
        "addendum cites Two-Layer Gold Corpus but gold/ is empty or missing"
    )
    for script in ("replay_eval.py", "shadow_eval.py"):
        assert (REPO_ROOT / f".data/evals/{script}").exists(), (
            f"addendum cites missing eval script: {script}"
        )
    manifest = PLUGIN_ROOT / "cc-skills-architect/skills/ask/lib/abstraction_audit_manifest.py"
    assert manifest.exists(), f"addendum cites missing manifest script: {manifest}"


def test_feedback_loop_addendum_states_honest_runtime_status():
    """The addendum must state plainly that none of the seven is a BLOCK gate.

    This is the central honesty invariant: an addendum about calibration must
    not imply runtime BLOCK enforcement where only advisory/WARN exists.
    """
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    idx = text.find("## Feedback Loop / Harness Calibration Addendum")
    section = text[idx:]
    lowered = section.lower()
    assert "block-level gate" in lowered or "none of the seven is a block" in lowered, (
        "Addendum must state plainly that none of the seven is a BLOCK gate today"
    )
    # Each mechanism row must carry a runtime status, not an implied "enforced."
    for status_token in ("prompt_advisory", "documentation_only", "runtime_surface"):
        assert status_token in lowered, (
            f"Addendum must use honest protection_level token: {status_token!r}"
        )


def test_feedback_loop_addendum_names_coverage_authority():
    """The addendum must name its own coverage authority (targeted, not whole_repo_static)."""
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    idx = text.find("## Feedback Loop / Harness Calibration Addendum")
    section = text[idx:]
    assert "Coverage authority for this addendum" in section, (
        "Addendum must state its own coverage authority"
    )
    assert "`targeted`" in section, (
        "Addendum must label its coverage as targeted (not whole_repo_static)"
    )


def test_feedback_loop_addendum_carries_falsification():
    """The addendum must carry a falsification condition."""
    text = REPORT_CONTRACTS_DOC.read_text(encoding="utf-8")
    idx = text.find("## Feedback Loop / Harness Calibration Addendum")
    section = text[idx:]
    assert "**Falsification:**" in section, (
        "Addendum must carry a Falsification condition"
    )


def test_improve_carries_feedback_loop_pointer():
    """/improve must carry a Feedback Loop pointer (it owns durable improvement work
    and already has the Deeper Abstraction Check reference section)."""
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    assert "## Feedback Loop / Harness Calibration — pointer" in text, (
        "/improve must carry a Feedback Loop pointer section"
    )
    idx = text.find("## Feedback Loop / Harness Calibration — pointer")
    section = text[idx : idx + 1200]
    # Names the canonical home (report-contracts.md addendum).
    assert "report-contracts.md" in section, (
        "/improve pointer must name the canonical reference file"
    )
    assert "Feedback Loop" in section and "Addendum" in section, (
        "/improve pointer must name the addendum section"
    )
    # Must restate advisory status, not claim BLOCK enforcement.
    assert "BLOCK" in section, "pointer must address the BLOCK status boundary"
    assert "prompt-advisory" in section.lower() or "prompt_advisory" in section.lower(), (
        "pointer must restate advisory status"
    )
    # Pointer-only: must NOT redefine the seven mechanism definitions.
    assert "Two-Layer Gold Corpus" not in section, (
        "/improve pointer must not duplicate mechanism definitions (pointer-only)"
    )


def test_feedback_loop_addendum_introduces_no_new_command():
    """No mechanism in the addendum may become a user-visible command."""
    import test_no_new_triggers_structural as _nt
    found = _nt._enumerate_triggers(PLUGIN_ROOT)
    for trigger in (
        "/feedback-loop",
        "/harness-calibration",
        "/calibration",
        "/ground-truth",
        "/gold-corpus",
        "/verification-packet",
    ):
        assert trigger not in found, (
            f"{trigger} introduced as a trigger — Feedback Loop work must not add commands"
        )


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
            print(f"PASS {fn.__name__}")
    print("all tests passed")
