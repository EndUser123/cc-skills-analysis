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


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
            print(f"PASS {fn.__name__}")
    print("all tests passed")
