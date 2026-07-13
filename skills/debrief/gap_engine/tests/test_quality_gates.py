"""Tests for quality gates — deterministic enforcement of reasoning patterns."""

from __future__ import annotations

import pytest

from skills.debrief.gap_engine.models import Finding, EvidenceRef
from skills.debrief.gap_engine.agents._quality_gates import (
    validate_escape_hatches,
    validate_evidence_structure,
    validate_absence_signal_respect,
    validate_mixed_substance_unverified,
    apply_quality_gates,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_finding(
    id="TEST-1",
    title="Test finding",
    description="",
    action="recover",
    effort=None,
    severity="high",
    unverified=False,
    metadata=None,
    evidence=None,
    domain="quality",
    gap_type="unknown",
    evidence_level: str = "unverified",
    **kwargs,
) -> Finding:
    """Create a Finding with sensible defaults for testing."""
    return Finding(
        id=id,
        title=title,
        description=description,
        source_type="agent",
        source_name="gap_reviewer",
        domain=domain,
        gap_type=gap_type,
        severity=severity,
        evidence_level=evidence_level,
        action=action,
        priority="medium",
        effort=effort,
        unverified=unverified,
        evidence=evidence or [],
        metadata=metadata or {},
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gate A — Escape hatches
# ─────────────────────────────────────────────────────────────────────────────

class TestGateA_EscapeHatches:
    def test_rejects_defer_without_followup(self):
        """defer action without followup_condition → down-rank to low."""
        f = make_finding(
            id="GAPR-TEST-1",
            title="Consider adding tests later",
            action="defer",
            effort=None,
            severity="high",
        )
        result = validate_escape_hatches([f])
        assert len(result) == 1
        assert result[0].severity == "low"
        assert result[0].priority == "low"
        assert result[0].metadata.get("escape_hatch") is True
        assert "action='defer' without followup_condition" in result[0].metadata.get(
            "escape_hatch_reason", ""
        )

    def test_allows_defer_with_followup_condition(self):
        """defer action WITH followup_condition → preserved."""
        f = make_finding(
            id="GAPR-TEST-2",
            title="Add tests after API stabilises",
            action="defer",
            effort=None,
            severity="high",
            metadata={"followup_condition": "API v2 released"},
        )
        result = validate_escape_hatches([f])
        assert len(result) == 1
        assert result[0].priority == "medium"
        assert result[0].metadata.get("escape_hatch") is None

    def test_rejects_critical_severity_missing_effort(self):
        """critical severity with missing effort → marked escape hatch."""
        f = make_finding(
            id="GAPR-TEST-3",
            title="Critical gap without cost estimate",
            action="recover",
            effort="",
            severity="critical",
        )
        result = validate_escape_hatches([f])
        assert len(result) == 1
        assert result[0].metadata.get("escape_hatch") is True
        assert "severity=critical with missing effort" in result[0].metadata.get(
            "escape_hatch_reason", ""
        )

    def test_downrank_medium_unspecified_effort_with_soft_language(self):
        """medium + unspecified effort + soft language → down-rank to low."""
        f = make_finding(
            id="GAPR-TEST-4",
            title="Optionally add validation",
            action="recover",
            effort="unknown",
            severity="medium",
            description="We could optionally add validation here if low risk.",
        )
        result = validate_escape_hatches([f])
        assert len(result) == 1
        assert result[0].priority == "low"
        assert result[0].metadata.get("escape_hatch") is True

    def test_preserves_proper_finding(self):
        """A properly specified finding passes Gate A unchanged."""
        f = make_finding(
            id="GAPR-TEST-5",
            title="Add authentication",
            action="prevent",
            effort="2h",
            severity="high",
            description="Add auth token validation to API calls.",
        )
        result = validate_escape_hatches([f])
        assert len(result) == 1
        assert result[0].priority == "medium"
        assert result[0].metadata.get("escape_hatch") is None


# ─────────────────────────────────────────────────────────────────────────────
# Gate B — Evidence structure
# ─────────────────────────────────────────────────────────────────────────────

class TestGateB_EvidenceStructure:
    def test_unverified_hook_reference_without_concrete_evidence(self):
        """hook/telemetry description without concrete evidence → unverified flag."""
        f = make_finding(
            id="GAPR-TEST-10",
            title="Hook telemetry not wired",
            description="The stop hook telemetry is not connected to the metrics pipeline.",
            unverified=True,
            evidence=[],
        )
        result = validate_evidence_structure([f])
        assert len(result) == 1
        assert result[0].metadata.get("unverified_implementation_claim") is True

    def test_unverified_with_verification_gap_preserved(self):
        """unverified finding WITH verification_gap → passes unchanged."""
        f = make_finding(
            id="GAPR-TEST-11",
            title="Potential hook gap",
            description="Some hook wiring may be missing.",
            unverified=True,
            metadata={"verification_gap": "Need runtime trace to confirm hook fires"},
            evidence=[
                EvidenceRef(kind="path", value=".claude/hooks/Stop.py"),
            ],
        )
        result = validate_evidence_structure([f])
        assert len(result) == 1
        assert result[0].metadata.get("unverified_implementation_claim") is None
        assert result[0].metadata.get("verification_gap_missing") is None

    def test_unverified_without_verification_gap_downranked(self):
        """unverified critical finding without verification_gap → downgraded."""
        f = make_finding(
            id="GAPR-TEST-12",
            title="Critical gap",
            description="Something may be wrong.",
            unverified=True,
            severity="critical",
            evidence=[],
        )
        result = validate_evidence_structure([f])
        assert len(result) == 1
        assert result[0].severity == "medium"
        assert result[0].metadata.get("verification_gap_missing") is True


# ─────────────────────────────────────────────────────────────────────────────
# Gate C — Absence signal respect
# ─────────────────────────────────────────────────────────────────────────────

class TestGateC_AbsenceSignalRespect:
    def test_downranks_absent_detector_conflict(self):
        """High/critical finding conflicts with absent detector without explanation → down-rank."""
        f = make_finding(
            id="GAPR-TEST-20",
            title="Missing test coverage",
            domain="quality",
            gap_type="missingtests",
            severity="high",
            metadata={},
        )
        result = validate_absence_signal_respect(
            [f],
            signals_absent=["verification_debt_detector"],
            detectors_ran=["verification_debt_detector"],
        )
        assert len(result) == 1
        assert result[0].priority == "low"
        assert result[0].metadata.get("downgraded_absent_signal") is True
        assert result[0].metadata.get("conflicting_absent_detector") == "verification_debt_detector"

    def test_allows_explicit_acknowledgment(self):
        """Finding with absent_signal_explained=True → preserved despite conflict."""
        f = make_finding(
            id="GAPR-TEST-21",
            title="Missing coverage despite detector running",
            domain="quality",
            gap_type="missingtests",
            severity="high",
            metadata={"absent_signal_explained": True},
        )
        result = validate_absence_signal_respect(
            [f],
            signals_absent=["verification_debt_detector"],
            detectors_ran=["verification_debt_detector"],
        )
        assert len(result) == 1
        assert result[0].priority == "medium"
        assert result[0].metadata.get("downgraded_absent_signal") is None

    def test_no_absent_signal_preserved(self):
        """No conflict → finding preserved."""
        f = make_finding(
            id="GAPR-TEST-22",
            title="Unrelated gap",
            domain="performance",
            gap_type="slow",
            severity="high",
        )
        result = validate_absence_signal_respect(
            [f],
            signals_absent=["verification_debt_detector"],
            detectors_ran=["verification_debt_detector"],
        )
        assert len(result) == 1
        assert result[0].priority == "medium"


# ─────────────────────────────────────────────────────────────────────────────
# Gate D — Mixed substance
# ─────────────────────────────────────────────────────────────────────────────

class TestGateD_MixedSubstance:
    def test_detects_mixed_substance_concrete_plus_hedging(self):
        """Unverified with concrete markers + hedging terms + no verification_gap → down-ranked."""
        f = make_finding(
            id="GAPR-TEST-30",
            title="Possible file gap",
            description="The file at line 42 might not be handling errors correctly.",
            unverified=True,
            severity="high",
            evidence=[],
        )
        result = validate_mixed_substance_unverified([f])
        assert len(result) == 1
        assert result[0].metadata.get("mixed_substance") is True
        assert result[0].priority in ("medium", "low")

    def test_preserves_verified(self):
        """Verified finding → passes unchanged."""
        f = make_finding(
            id="GAPR-TEST-31",
            title="Verified gap",
            description="The file at line 42 does not handle errors.",
            unverified=False,
            severity="high",
            evidence=[EvidenceRef(kind="path", value=".claude/hooks/Stop.py")],
        )
        result = validate_mixed_substance_unverified([f])
        assert len(result) == 1
        assert result[0].metadata.get("mixed_substance") is None

    def test_preserves_with_verification_gap(self):
        """Unverified + concrete + hedging WITH verification_gap → preserved."""
        f = make_finding(
            id="GAPR-TEST-32",
            title="Possible gap",
            description="The hook at file:44 could fail.",
            unverified=True,
            severity="high",
            metadata={"verification_gap": "Run session and check telemetry events"},
            evidence=[],
        )
        result = validate_mixed_substance_unverified([f])
        assert len(result) == 1
        assert result[0].metadata.get("mixed_substance") is None


# ─────────────────────────────────────────────────────────────────────────────
# apply_quality_gates — integration
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyQualityGates:
    def test_all_gates_applied_in_sequence(self):
        """apply_quality_gates applies all four gates in order."""
        f = make_finding(
            id="GAPR-TEST-40",
            title="Possible hook gap",
            description="The hook at file:10 might not be wired, optionally.",
            unverified=True,
            action="defer",
            effort=None,
            severity="critical",
            domain="quality",
            gap_type="missingtests",
            evidence=[],
        )
        # Gate A: defer without followup → low
        # Gate B: unverified without verification_gap → downgraded
        # Gate C: conflicts with absent detector → downgraded
        # Gate D: concrete + hedging → mixed_substance
        result = apply_quality_gates(
            [f],
            signals_absent=["verification_debt_detector"],
            detectors_ran=["verification_debt_detector"],
        )
        assert len(result) == 1
        assert result[0].metadata.get("escape_hatch") is True
        assert result[0].metadata.get("mixed_substance") is True

    def test_no_gates_triggered_for_clean_finding(self):
        """A properly specified finding passes all gates cleanly."""
        f = make_finding(
            id="GAPR-TEST-41",
            title="Add error handling",
            description="Add error handling to the API client.",
            action="prevent",
            effort="1h",
            severity="high",
            unverified=False,
            domain="quality",
            gap_type="techdebt",
            metadata={"followup_condition": "API v2 released"},
            evidence=[EvidenceRef(kind="path", value=".claude/hooks/Stop.py")],
        )
        result = apply_quality_gates([f], signals_absent=[], detectors_ran=[])
        assert len(result) == 1
        assert not any(
            result[0].metadata.get(k) for k in [
                "escape_hatch", "unverified_implementation_claim",
                "downgraded_absent_signal", "mixed_substance",
            ]
        )

# ─────────────────────────────────────────────────────────────────────────────
# read_verdicts — findings reviewer verdict parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestReadVerdicts:
    def test_parses_verdict_format(self, tmp_path):
        """read_verdicts extracts rejected IDs and reasons from verdict format."""
        import json
        from skills.debrief.gap_engine.agents.findings_reviewer import read_verdicts

        result_file = tmp_path / "findings_reviewer_result.json"
        result_file.write_text(json.dumps({
            "verdicts": [
                {"finding_id": "CHANGELOG-001", "action": "reject", "reason": "False positive"},
                {"finding_id": "CHANGELOG-002", "action": "keep", "reason": "Legitimate"},
                {"finding_id": "WORKFLOW-001", "action": "reject", "reason": "Stale"},
            ],
            "summary": {"total": 3, "kept": 1, "rejected": 2},
        }))

        rejected, reasons = read_verdicts(result_file)
        assert rejected == {"CHANGELOG-001", "WORKFLOW-001"}
        assert reasons["CHANGELOG-001"] == "False positive"
        assert "CHANGELOG-002" not in rejected

    def test_returns_empty_for_missing_file(self, tmp_path):
        """read_verdicts returns empty sets when file doesn't exist."""
        from skills.debrief.gap_engine.agents.findings_reviewer import read_verdicts

        rejected, reasons = read_verdicts(tmp_path / "nonexistent.json")
        assert rejected == set()
        assert reasons == {}

    def test_returns_empty_for_invalid_json(self, tmp_path):
        """read_verdicts returns empty sets for malformed JSON."""
        from skills.debrief.gap_engine.agents.findings_reviewer import read_verdicts

        result_file = tmp_path / "findings_reviewer_result.json"
        result_file.write_text("not json")
        rejected, reasons = read_verdicts(result_file)
        assert rejected == set()

    def test_returns_empty_for_no_verdicts_key(self, tmp_path):
        """read_verdicts handles dict without verdicts key."""
        import json
        from skills.debrief.gap_engine.agents.findings_reviewer import read_verdicts

        result_file = tmp_path / "findings_reviewer_result.json"
        result_file.write_text(json.dumps({"findings": [], "notes": "empty"}))
        rejected, reasons = read_verdicts(result_file)
        assert rejected == set()
