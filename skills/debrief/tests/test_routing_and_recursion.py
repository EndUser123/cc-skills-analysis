"""Regression tests for safe debrief routing and bounded recursion."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "__lib"))

from debrief_core import (
    Budget,
    Category,
    Finding,
    FindingKind,
    State,
    recurse_layer,
    run,
    write_layer,
)


def test_write_layer_rejects_verified_opportunity_even_when_it_has_an_origin():
    finding = Finding(
        finding_id="opportunity-1",
        state=State.VERIFIED,
        category=Category.DESIGN,
        kind=FindingKind.OPPORTUNITY,
        origin_file="src/example.py",
        origin_line=10,
        idea="reuse the pattern",
        generalization_test="try it in another module",
    )

    result = write_layer([finding])

    assert result["written"] == []
    assert result["rejected"] == [finding]
    assert finding.state == State.VERIFIED
    assert finding.recursion_exhausted is True


def test_run_surfaces_deferred_opportunities_as_written():
    result = run(
        transcript_text="defer that; defer that",
        initial_findings=[],
        layer_extractor=lambda _finding: ([], []),
        truth_callable=lambda _finding: {"status": "VERIFIED", "evidence": "confirmed"},
        budget=Budget(max_layers=1),
    )

    assert result["summary"]["opportunities_written"] >= 1
    assert result["summary"]["written"] >= 1  # includes the opportunity
    assert result["summary"]["blocked_unverified"] == 0


def test_recurse_layer_does_not_extract_the_same_finding_twice():
    parent = Finding(
        finding_id="parent-1",
        state=State.LOCATED,
        origin_file="src/example.py",
        origin_line=10,
    )
    calls = []

    def extractor(_finding):
        calls.append(1)
        return [], []

    recurse_layer(
        [parent, parent],
        Budget(max_layers=2),
        extractor,
        visited={"parent-1"},
    )

    assert calls == []
    assert parent.recursion_exhausted is True


# ── new tests for the debrief update ────────────────────────────────────────

def test_structured_opportunity_reaches_task_kind_opportunity_full():
    """A structured opportunity with idea + generalization_test + truth
    produces a task with TASK_KIND: opportunity-full."""
    result = run(
        transcript_text="we should generalize the approach",
        initial_findings=[{
            "symptom_text": "repeated pattern in auth handling",
            "symptom_source": "transcript L10",
            "kind": "opportunity",
            "idea": "generalize auth guard pattern",
            "generalization_test": "apply to two unrelated routes",
            "evidence_strength": "repeated_pattern",
        }],
        layer_extractor=lambda _finding: ([], []),
        truth_callable=lambda _finding: {"status": "VERIFIED", "evidence": "confirmed"},
    )
    assert result["summary"]["opportunities_written"] >= 1
    opp_tasks = [t for t in result["tasks"]["written"]
                 if "TASK_KIND: opportunity-full" in t.get("task_body", "")]
    assert len(opp_tasks) >= 1
    body = opp_tasks[0]["task_body"]
    assert "IDEA: generalize auth guard pattern" in body
    assert "GENERALIZATION_TEST:" in body
    assert "VERIFIED FACTS:" in body


def test_weak_opportunity_rejected():
    """A weak-opportunity with evidence_strength=weak gets PROMOTE_TO: reject."""
    result = run(
        transcript_text="maybe there is a pattern here",
        initial_findings=[{
            "symptom_text": "vague pattern feeling",
            "symptom_source": "transcript L5",
            "kind": "opportunity",
            "idea": "something about guards",
            "generalization_test": "try it once",
            "evidence_strength": "weak",
        }],
        layer_extractor=lambda _finding: ([], []),
        truth_callable=lambda _finding: {"status": "VERIFIED", "evidence": "confirmed"},
    )
    assert result["summary"]["opportunities_written"] == 0
    # The rejected opportunity should be visible in findings
    assert result["summary"]["total_findings"] >= 1


def test_three_layer_causal_chain_reconstructed():
    """A 3-layer defect chain walks parent_id links and emits root cause first."""
    def resolver(text):
        return ("src/root.py", 42, "root cause")
    calls = []
    def extractor(parent):
        calls.append(parent.finding_id)
        if parent.origin_file == "src/mid.py":
            return (["root cause: missing null check"],
                    ["src/root.py:42"])
        elif parent.origin_file == "src/top.py":
            return (["mid layer: unvalidated input"],
                    ["src/mid.py:15"])
        else:
            return ([], [])
    def truth(f):
        return {"status": "VERIFIED", "evidence": "confirmed"}
    result = run(
        transcript_text="crash on null input, then fell back to a workaround",
        initial_findings=[("crash at top layer", "src/top.py:100")],
        layer_extractor=extractor,
        source_tree_resolver=resolver,
        truth_callable=truth,
        budget=Budget(max_layers=3, max_findings_per_layer=4),
    )
    # Must have at least 1 written task with the chain
    assert result["summary"]["written"] >= 1, f"No written tasks: {result}"
    for t in result["tasks"]["written"]:
        body = t["task_body"]
        # Chain indicator must be present
        assert "Causal chain (root cause first)" in body


def test_principle_verification_receives_exact_claim():
    """Principle extraction passes the actual claim, not the original finding."""
    from debrief_core import extract_generalizable_principle
    received_claims = []
    def truth_func(claim="", file_path=""):
        received_claims.append(claim)
        return {"status": "VERIFIED", "evidence": claim, "applies_to": "coding"}
    fp = Finding(
        finding_id="p-test", state=State.VERIFIED, kind=FindingKind.DEFECT,
        category=Category.DEFECT,
        origin_file="src/foo.py", origin_line=42,
        origin_explanation="guard the .lower() on a list",
    )
    principle, applies_to, status = extract_generalizable_principle(fp, truth_func)
    assert len(received_claims) >= 1
    # The claim should reference the fix being generalizable, not the original bug
    assert "generalizable principle" in received_claims[0].lower(), \
        f"Claim does not mention generalizability: {received_claims[0]}"


def test_contract_mode_still_blocks_unverified():
    """Contract truth-mode still produces zero written tasks for unverified defects."""
    result = run(
        transcript_text="rows duplicate on ingest, fell back to workaround",
        initial_findings=[("rows duplicate", "L10")],
        layer_extractor=lambda _finding: ([], []),
        truth_callable=lambda _finding: {"status": "UNVERIFIED", "evidence": ""},
    )
    assert result["summary"]["written"] == 0
    assert result["summary"]["recursion_exhausted"] >= 1


def test_defect_compatibility():
    """Existing defect behavior: defect with resolver + truth produces written task."""
    def resolver(text):
        return ("src/db.py", 42, "missing unique constraint")
    def truth(f):
        return {"status": "VERIFIED", "evidence": "confirmed"}
    result = run(
        transcript_text="rows duplicate on ingest",
        initial_findings=[("rows duplicate", "L10")],
        layer_extractor=lambda _finding: ([], []),
        source_tree_resolver=resolver,
        truth_callable=truth,
    )
    assert result["summary"]["written"] >= 1
    for t in result["tasks"]["written"]:
        body = t["task_body"]
        assert "TASK_KIND: full" in body
        assert "TLDR:" in body
