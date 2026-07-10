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


def test_run_surfaces_deferred_opportunities_as_skipped():
    result = run(
        transcript_text="defer that; defer that",
        initial_findings=[],
        layer_extractor=lambda _finding: ([], []),
        budget=Budget(max_layers=1),
    )

    assert result["summary"]["opportunities_skipped"] >= 1
    assert result["tasks"]["written"] == []


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
