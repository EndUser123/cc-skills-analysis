"""Tests for the Thought Partner Addendum (TPA) report contract.

Guards against regressions:
- The canonical reference doc exists and names `/improve` as canonical owner.
- All required fields + the urgency enum are present.
- The 7 rules, 3 worked examples, and the negative example are present.
- The per-command placement table covers all 7 commands.
- The falsification condition is present verbatim.
- The owner (`/improve`) and all 6 pointer commands carry a TPA section.
- `/red-team`'s TPA does not displace the PROCEED/REVISE/BLOCK verdict.
- `/review`'s TPA is gated ("ONLY when ... not for routine reviews").
- No new top-level command was created (delegates to the structural allowlist).
- /wiki-ingest was not created; no /wiki auto-write code was introduced.
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

TPA_DOC = (
    PLUGIN_ROOT
    / "cc-skills-analysis/skills/debrief/references/thought-partner-addendum.md"
)

IMPROVE_SKILL = PLUGIN_ROOT / "improve-partner/skills/improve/SKILL.md"
DEBRIEF_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/debrief/SKILL.md"
REDTEAM_CMD = PLUGIN_ROOT / "red-team/commands/red-team.md"
SKILL_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/skill-audit/SKILL.md"
REVIEW_SKILL = PLUGIN_ROOT / "cc-skills-sdlc/skills/review/SKILL.md"
CLAUDE_AUDIT_SKILL = PLUGIN_ROOT / "cc-skills-analysis/skills/claude-audit/SKILL.md"
GO_SKILL = PLUGIN_ROOT / "cc-skills-sdlc/skills/go/SKILL.md"


# ---- Canonical template invariants ----

def test_tpa_doc_exists():
    assert TPA_DOC.exists(), f"missing: {TPA_DOC}"


def test_tpa_doc_canonical_owner_is_improve():
    text = TPA_DOC.read_text(encoding="utf-8")
    # The header must declare /improve as the canonical owner.
    head = text[: text.index("\n\n##")]  # preamble before first section
    assert "Canonical owner: `/improve`" in head, (
        "TPA doc must declare `/improve` as canonical owner in the preamble"
    )


def test_tpa_doc_advisory_status():
    """The doc must state plainly that the TPA is prompt-advisory, not
    runtime-enforced — so no one mistakes a static test for runtime gating."""
    text = TPA_DOC.read_text(encoding="utf-8")
    assert "prompt-advisory" in text.lower() or "prompt_advisory" in text.lower()
    assert "runtime_enforced" in text or "runtime-enforced" in text


def test_tpa_doc_required_fields():
    text = TPA_DOC.read_text(encoding="utf-8")
    for f in ("observation", "why_it_matters", "evidence", "recommended_action", "urgency"):
        assert f in text, f"required field missing: {f!r}"


def test_tpa_doc_urgency_enum():
    text = TPA_DOC.read_text(encoding="utf-8")
    for v in ("now", "later", "watch"):
        assert v in text, f"urgency enum value missing: {v!r}"


def test_tpa_doc_seven_rules_present():
    """Spot-check phrases that carry the load of the 7 rules."""
    text = TPA_DOC.read_text(encoding="utf-8")
    checks = [
        "material",                       # rule 1: only when material
        "generic caveats",                # rule 2: omit generic caveats
        "would not change a decision",    # rule 3: omit if no decision changes
        "INFERENCE",                      # rule 4: mark weak evidence
        "runtime-enforced",               # rule 5: say if advisory
        "displace",                       # rule 6: do not displace
        "1–5",                            # rule 7: keep short
    ]
    for c in checks:
        assert c in text, f"rule signal missing: {c!r}"


def test_tpa_doc_worked_examples_present():
    text = TPA_DOC.read_text(encoding="utf-8")
    assert "Example 1" in text, "missing Example 1 (bounded impl report)"
    assert "Example 2" in text, "missing Example 2 (red-team overclaim)"
    assert "Example 3" in text, "missing Example 3 (deterministic-first overuse)"
    # Example 2 must be the prompt-mediated BLOCK-overclaim shape.
    idx = text.find("Example 2")
    section = text[idx : idx + 2000]
    assert "prompt" in section.lower() or "advisory" in section.lower()
    assert "BLOCK" in section or "protection_level" in section


def test_tpa_doc_negative_example_present():
    """The three forbidden generic caveats must appear, marked forbidden."""
    text = TPA_DOC.read_text(encoding="utf-8")
    idx = text.lower().find("negative example")
    assert idx != -1, "missing Negative example section"
    section = text[idx : idx + 1500]
    for caveat in ("Be careful with scope", "More tests may be useful", "Consider documentation"):
        assert caveat in section, f"negative example must forbid: {caveat!r}"
    assert "FORBIDDEN" in section, "negative example must mark items FORBIDDEN"


def test_tpa_doc_per_command_table_covers_all():
    text = TPA_DOC.read_text(encoding="utf-8")
    for cmd in ("/improve", "/go", "/red-team", "/debrief", "/skill-audit", "/claude-audit", "/review"):
        assert cmd in text, f"per-command table missing: {cmd}"


def test_tpa_doc_what_this_is_not_present():
    text = TPA_DOC.read_text(encoding="utf-8")
    idx = text.find("What this is NOT")
    assert idx != -1, "missing 'What this is NOT' section"
    section = text[idx : idx + 1500]
    # Must forbid each of the rejected shapes.
    for token in ("/thought-partner", "/next", "/reconcile", "/wiki-ingest", "chain-of-thought", "self-reflection"):
        assert token in section, f"'What this is NOT' missing: {token!r}"


def test_tpa_doc_falsification_present():
    text = TPA_DOC.read_text(encoding="utf-8")
    idx = text.find("## Falsification")
    assert idx != -1, "missing Falsification section"
    # Collapse whitespace so a hard line-wrap in the doc does not defeat the
    # verbatim-phrase check (wrap is formatting, not contract content).
    section = re.sub(r"\s+", " ", text[idx:])
    for phrase in (
        "priority, risk, sequencing, scope, confidence, cost, maintainability, or long-term value",
        "generic caveats",
        "chain-of-thought",
        "new command",
        "trivial work",
    ):
        assert phrase in section, f"falsification missing phrase: {phrase!r}"


def test_tpa_doc_forbids_cot_narration():
    """The contract must not require or teach chain-of-thought narration."""
    text = TPA_DOC.read_text(encoding="utf-8")
    forbidden = [
        "explain your reasoning step by step",
        "show your chain of thought",
        "think out loud",
    ]
    for phrase in forbidden:
        assert phrase.lower() not in text.lower()


def test_tpa_doc_no_silent_wiki_write_code():
    """The doc must not teach an auto-fire /wiki write mechanism."""
    text = TPA_DOC.read_text(encoding="utf-8")
    forbidden = ("wiki_after_write(", "from wiki_after_write", "auto-fire /wiki", "automatic /wiki")
    for phrase in forbidden:
        assert phrase.lower() not in text.lower()


# ---- Per-command section presence ----

@pytest.mark.parametrize(
    "path",
    [IMPROVE_SKILL, DEBRIEF_SKILL, REDTEAM_CMD, SKILL_AUDIT_SKILL, REVIEW_SKILL, CLAUDE_AUDIT_SKILL, GO_SKILL],
)
def test_tpa_section_present(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "## Thought Partner Addendum" in text, f"{path} missing TPA section"


def test_improve_tpa_section_claims_ownership():
    """The /improve section must declare canonical ownership + reference the doc."""
    text = IMPROVE_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Thought Partner Addendum")
    section = text[idx : idx + 2000]
    assert "canonical owner" in section.lower()
    assert "thought-partner-addendum.md" in section
    # Must list the required fields so an /improve run can emit the shape.
    for f in ("observation", "why_it_matters", "evidence", "recommended_action", "urgency"):
        assert f in section, f"/improve TPA section missing field: {f!r}"


def test_all_pointer_sections_reference_canonical_doc():
    """Each pointer section must point at the canonical reference doc."""
    for path in (DEBRIEF_SKILL, REDTEAM_CMD, SKILL_AUDIT_SKILL, REVIEW_SKILL, CLAUDE_AUDIT_SKILL, GO_SKILL):
        text = path.read_text(encoding="utf-8")
        idx = text.find("## Thought Partner Addendum")
        assert idx != -1, f"{path} missing TPA section"
        section = text[idx : idx + 1500]
        assert "thought-partner-addendum.md" in section, (
            f"{path} TPA section must reference the canonical doc"
        )
        assert "prompt-advisory" in section.lower() or "prompt_advisory" in section.lower(), (
            f"{path} TPA section must state it is prompt-advisory"
        )


def test_redteam_tpa_does_not_displace_verdict():
    """/red-team's TPA must NOT displace the PROCEED/REVISE/BLOCK verdict."""
    text = REDTEAM_CMD.read_text(encoding="utf-8")
    idx = text.find("## Thought Partner Addendum")
    section = text[idx : idx + 1500]
    assert "PROCEED" in section and "REVISE" in section and "BLOCK" in section, (
        "/red-team TPA must name the PROCEED/REVISE/BLOCK verdict it must not displace"
    )
    assert "displace" in section.lower() or "do not" in section.lower(), (
        "/red-team TPA must say it does not displace the verdict"
    )


def test_review_tpa_is_gated():
    """/review's TPA must be gated — ONLY for broader patterns, not routine reviews."""
    text = REVIEW_SKILL.read_text(encoding="utf-8")
    idx = text.find("## Thought Partner Addendum")
    section = text[idx : idx + 1500]
    assert "ONLY when" in section or "not for routine" in section.lower(), (
        "/review TPA must be gated to non-routine findings"
    )


# ---- No-new-command invariants ----

def test_no_new_top_level_command_for_tpa():
    """Delegate to the structural allowlist."""
    import test_no_new_triggers_structural as _nt
    _nt.test_no_new_triggers_structural()


def test_no_wiki_ingest_for_tpa():
    """Delegate to the named wiki-ingest prohibition."""
    import test_no_new_triggers_structural as _nt
    _nt.test_no_wiki_ingest_trigger()


def test_no_tpa_named_commands_introduced():
    """/thought-partner, /next, /reconcile must never appear as triggers.
    Named check so the policy is visible in the test name."""
    import test_no_new_triggers_structural as _nt
    found = _nt._enumerate_triggers(PLUGIN_ROOT)
    for trigger in ("/thought-partner", "/next", "/reconcile"):
        assert trigger not in found, (
            f"{trigger} was introduced as a trigger — "
            f"TPA work must not add new commands"
        )


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
            print(f"PASS {fn.__name__}")
    print("all tests passed")
