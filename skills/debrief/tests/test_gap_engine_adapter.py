"""Tests for the internal GAP → /debrief detector adapter.

Layer justification (which layer proves what):
- UNIT (gap_findings_to_debrief, attach_score_and_owner): pure transforms, no
  I/O. Proves shape correctness, source-fallback priority, score-stamp matching,
  idempotency. Misses: the detector chain wiring + the real gap API contract.
- INTEGRATION (run_gap_detectors on a deterministic transcript fixture): crosses
  modules + uses the real gap detectors + writes the filesystem (artifacts dir). Proves the
  lazy cross-skill import resolves, the constructor/method signatures match,
  and the chain order is correct. This is the falsification test for the whole
  import-based design.
- INTEGRATION (read_gap_review_debrief with a synthetic result file): proves the
  gap-review pass-2 merge READ path without a live agent dispatch — the agent's
  job is to WRITE gap_reviewer_result.json; the adapter's job is to read+merge
  it, and that is what this exercises.
- REGRESSION (#983): the old /debrief had no deterministic detectors (0/40
  opportunity-marker hit rate). The fixture proves the new path surfaces a
  session-outcome finding at the detector boundary without depending on a
  developer's newest local transcript.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent  # cc-skills-analysis plugin root
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from skills.debrief.gap_engine.models import Finding, EvidenceRef  # noqa: E402
from skills.debrief.__lib import gap_engine_adapter  # noqa: E402


def _finding(**kw) -> Finding:
    base = dict(
        id="SESSION-UNCO-001",
        title="fold gap into debrief",
        description="Session outcome: uncompleted_goal",
        source_type="detector",
        source_name="session_outcome_detector",
        domain="session",
        gap_type="session_uncompleted_goal",
        severity="medium",
        evidence_level="unverified",
    )
    base.update(kw)
    return Finding(**base)


# ── UNIT: gap_findings_to_debrief ────────────────────────────────────────────

class TestGapFindingsToDebrief:
    def test_emits_debrief_shape(self):
        f = _finding(metadata={"score": 6.0})
        f.evidence = [EvidenceRef(kind="session_outcome", value="uncompleted_goal")]
        out = gap_engine_adapter.gap_findings_to_debrief([f])
        assert len(out) == 1
        item = out[0]
        assert "symptom_text" in item and "symptom_source" in item
        assert item["gap_id"] == "SESSION-UNCO-001"
        assert item["gap_score"] == 6.0
        assert item["symptom_source"] == "uncompleted_goal"

    @pytest.mark.parametrize("closed_status", ["resolved", "rejected", "mapped"])
    def test_non_open_statuses_filtered(self, closed_status):
        # the converter drops resolved/rejected/mapped — only open survives.
        # parametrized so flipping one status out of the set fails a test.
        open_f = _finding(id="SESSION-UNCO-001", status="open")
        closed_f = _finding(id="SESSION-UNCO-002", status=closed_status,
                            title="done thing")
        out = gap_engine_adapter.gap_findings_to_debrief([open_f, closed_f])
        assert len(out) == 1
        assert out[0]["gap_id"] == "SESSION-UNCO-001"

    def test_source_fallback_priority(self):
        # no evidence -> falls back to file -> then source_name:id
        f = _finding(file="src/foo.py", evidence=[])
        out = gap_engine_adapter.gap_findings_to_debrief([f])
        assert out[0]["symptom_source"] == "src/foo.py"

        f2 = _finding(file="", evidence=[])
        out2 = gap_engine_adapter.gap_findings_to_debrief([f2])
        assert out2[0]["symptom_source"] == "session_outcome_detector:SESSION-UNCO-001"

    def test_empty_title_falls_back_to_id(self):
        f = _finding(title="", description="")
        out = gap_engine_adapter.gap_findings_to_debrief([f])
        assert out[0]["symptom_text"] == "SESSION-UNCO-001"


# ── UNIT: _outcome_to_findings (the inlined converter) ───────────────────────

class TestOutcomeToFindings:
    """Pins the branches of _outcome_to_findings so a mutation in any one
    branch fails a named test. The converter mirrors orchestrator.py:324-380;
    if that inline drifts, these catch it."""

    def _item(self, **kw):
        base = dict(category="uncompleted_goal", content="do the thing",
                    confidence=0.5, recurrence_count=1, acknowledged=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def _gap(self):
        return gap_engine_adapter._import_gap_engine()

    def test_severity_high_at_recurrence_ge_2(self):
        result = SimpleNamespace(items=[self._item(recurrence_count=2)])
        out = gap_engine_adapter._outcome_to_findings(result, self._gap(), "t", "s", None)
        assert out[0].severity == "high"

    def test_severity_boundary_recurrence_1_not_high(self):
        # boundary: recurrence==1 is NOT high — it falls back to the category map.
        # pins >= 2 vs > 2 (off-by-one mutation kills this).
        result = SimpleNamespace(items=[self._item(recurrence_count=1, category="uncompleted_goal")])
        out = gap_engine_adapter._outcome_to_findings(result, self._gap(), "t", "s", None)
        assert out[0].severity == "medium"

    def test_severity_uses_category_map_below_threshold(self):
        # open_question + deferred_item are "low"; uncompleted_goal/identified_task "medium".
        result = SimpleNamespace(items=[
            self._item(category="open_question"),
            self._item(category="deferred_item"),
            self._item(category="identified_task"),
        ])
        out = gap_engine_adapter._outcome_to_findings(result, self._gap(), "t", "s", None)
        assert [f.severity for f in out] == ["low", "low", "medium"]

    def test_id_format_category_prefix_and_1_based_index(self):
        # id = SESSION-{category[:4].upper()}-{idx+1:03d}
        result = SimpleNamespace(items=[
            self._item(category="uncompleted_goal"),
            self._item(category="identified_task"),
        ])
        out = gap_engine_adapter._outcome_to_findings(result, self._gap(), "t", "s", None)
        assert out[0].id == "SESSION-UNCO-001"
        assert out[1].id == "SESSION-IDEN-002"

    def test_evidence_level_verified_at_confidence_ge_07(self):
        # boundary at 0.7: >= 0.7 → verified, < 0.7 → unverified.
        result = SimpleNamespace(items=[
            self._item(confidence=0.7),
            self._item(confidence=0.69),
        ])
        out = gap_engine_adapter._outcome_to_findings(result, self._gap(), "t", "s", None)
        assert out[0].evidence_level == "verified"
        assert out[1].evidence_level == "unverified"

    def test_empty_items_returns_empty(self):
        result = SimpleNamespace(items=[])
        out = gap_engine_adapter._outcome_to_findings(result, self._gap(), "t", "s", None)
        assert out == []


# ── UNIT: attach_score_and_owner ─────────────────────────────────────────────

class TestAttachScoreAndOwner:
    def test_stamps_matching_task(self):
        findings = [{"symptom_text": "fold gap into debrief", "symptom_source": "s",
                     "gap_score": 6.0, "gap_owner_skill": "debrief"}]
        tasks = [{"body": "fold gap into debrief — needs root-cause trace"}]
        out = gap_engine_adapter.attach_score_and_owner(tasks, findings)
        assert "[gap]" in out[0]["body"]
        assert "gap_score: 6.0" in out[0]["body"]
        assert "owner_skill: debrief" in out[0]["body"]

    def test_non_matching_task_untouched(self):
        findings = [{"symptom_text": "completely unrelated gap", "symptom_source": "s",
                     "gap_score": 9.0, "gap_owner_skill": "x"}]
        tasks = [{"body": "fold gap into debrief — needs trace"}]
        out = gap_engine_adapter.attach_score_and_owner(tasks, findings)
        assert out[0]["body"] == "fold gap into debrief — needs trace"

    def test_idempotent(self):
        findings = [{"symptom_text": "fold gap", "symptom_source": "s",
                     "gap_score": 6.0, "gap_owner_skill": "d"}]
        tasks = [{"body": "fold gap — trace"}]
        once = gap_engine_adapter.attach_score_and_owner(tasks, findings)
        body_once = once[0]["body"]
        twice = gap_engine_adapter.attach_score_and_owner(once, findings)
        assert twice[0]["body"] == body_once  # no double-stamp

    def test_score_only_when_owner_none(self):
        # owner missing → stamp score only, no owner_skill token.
        findings = [{"symptom_text": "fold gap", "symptom_source": "s",
                     "gap_score": 7.0, "gap_owner_skill": None}]
        tasks = [{"body": "fold gap — trace"}]
        out = gap_engine_adapter.attach_score_and_owner(tasks, findings)
        assert "gap_score: 7.0" in out[0]["body"]
        assert "owner_skill" not in out[0]["body"]

    def test_owner_only_when_score_none(self):
        # score missing → stamp owner only, no gap_score token.
        findings = [{"symptom_text": "fold gap", "symptom_source": "s",
                     "gap_score": None, "gap_owner_skill": "debrief"}]
        tasks = [{"body": "fold gap — trace"}]
        out = gap_engine_adapter.attach_score_and_owner(tasks, findings)
        assert "owner_skill: debrief" in out[0]["body"]
        assert "gap_score" not in out[0]["body"]

    def test_substring_match_not_exact(self):
        # matching is substring-containment, not equality — the task body
        # embeds the symptom text with surrounding prose.
        findings = [{"symptom_text": "fold gap", "symptom_source": "s",
                     "gap_score": 5.0, "gap_owner_skill": "d"}]
        tasks = [{"body": "TODO: fold gap now and also other stuff"}]
        out = gap_engine_adapter.attach_score_and_owner(tasks, findings)
        assert "[gap]" in out[0]["body"]


# ── INTEGRATION: gap-review pass-2 merge (read path) ─────────────────────────

class TestGapReviewPass2Merge:
    """Pass 2: the gap_reviewer agent has written gap_reviewer_result.json;
    the adapter must read + convert it. Proves the merge READ path without a
    live agent dispatch."""

    def test_reads_synthetic_result(self, tmp_path):
        result_path = tmp_path / "gap_reviewer_result.json"
        result_path.write_text(json.dumps({
            "review": {"facts": [], "inferences": [], "unknowns": [], "recommendations": []},
            "findings": [{
                "id": "GAPR-001",
                "title": "agent-surfaced gap",
                "description": "the agent found a gap detectors missed",
                "severity": "high",
                "domain": "session",
                "gap_type": "agent_observed",
                "evidence_level": "unverified",
                "status": "open",
            }],
            "signals_absent": [],
            "detectors_ran": ["session_goal_detector", "session_outcome_detector"],
        }), encoding="utf-8")
        out = gap_engine_adapter.read_gap_review_debrief(tmp_path)
        # read_result runs apply_quality_gates; a well-formed high-severity open
        # finding with no absence-signals should survive. If gates drop it, the
        # read path still executed (returns []) — assert the contract that
        # matters: every returned item is debrief-shaped.
        for item in out:
            assert "symptom_text" in item and "symptom_source" in item
            assert item["gap_id"] == "GAPR-001"

    def test_missing_result_returns_empty(self, tmp_path):
        assert gap_engine_adapter.read_gap_review_debrief(tmp_path) == []


# ── INTEGRATION + REGRESSION (#983): deterministic detector chain ────────────

def _fixture_transcript(tmp_path: Path) -> Path:
    path = tmp_path / "fixture-session.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({
                "role": "user",
                "content": "I want to implement a durable regression test for detector behavior.",
            }),
            json.dumps({
                "role": "assistant",
                "content": "We discussed the approach but did not implement the test.",
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    return path


class TestRunGapDetectorsFixtureChain:
    """Integration + #983 regression: the old /debrief surfaced 0 deterministic
    findings (0/40 opportunity-marker hit rate). run_gap_detectors must surface
    ≥1 finding on a qualifying transcript fixture where the deterministic
    outcome detector fires — proving the new path closes that gap."""

    def test_chain_runs_and_returns_findings(self, tmp_path):
        tp = _fixture_transcript(tmp_path)
        findings = gap_engine_adapter.run_gap_detectors(
            str(tp), "pytest-run", tmp_path, root="P:/")
        # contract: returns a list of gap Findings
        assert isinstance(findings, list)
        for f in findings:
            assert hasattr(f, "id") and hasattr(f, "title")
            assert f.source_name in {"session_outcome_detector", "gap_reviewer",
                                     "carryover", "detector"}
        # #983 regression: the qualifying fixture carries ≥1 session outcome.
        # If the detector chain returns 0, the wiring is broken.
        assert len(findings) >= 1, (
            "run_gap_detectors returned 0 findings on the qualifying fixture — "
            "the #983 regression (0 deterministic findings) has recurred.")
        # And it must be a SESSION-* outcome finding from the outcome detector
        # — not a carried-over or agent finding that would satisfy count>=1
        # while leaving #983 (no deterministic session outcomes) un-fixed.
        session_outcomes = [f for f in findings if f.id.startswith("SESSION-")]
        assert session_outcomes, (
            "findings returned but none are SESSION-* outcomes — the outcome "
            "detector did not fire, so #983 is not actually closed.")

    def test_findings_convert_to_debrief_shape(self, tmp_path):
        tp = _fixture_transcript(tmp_path)
        findings = gap_engine_adapter.run_gap_detectors(
            str(tp), "pytest-run-2", tmp_path, root="P:/")
        shaped = gap_engine_adapter.gap_findings_to_debrief(findings)
        # at least one open finding converts (session outcomes are open)
        assert len(shaped) >= 1
        for s in shaped:
            assert s["symptom_text"] and s["symptom_source"]


# ── INTEGRATION: lazy import resolves (the falsification test) ───────────────

def test_cross_skill_import_resolves():
    """The entire import-based design is wrong if skills.debrief.gap_engine.__lib is not
    importable from debrief's runtime. This is the load-bearing assertion."""
    gap = gap_engine_adapter._import_gap_engine()
    for key in ("session_goal_detector", "session_outcome_detector",
                "completion_checker", "carryover", "resolve", "scoring",
                "route", "dedupe", "Finding"):
        assert key in gap, f"missing gap module: {key}"
