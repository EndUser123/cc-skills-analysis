"""Tests for leverage scoring, ordering, triage, dependency fields, and trend."""
from __future__ import annotations

from skills.debrief.gap_engine.models import Finding
from skills.debrief.gap_engine.__lib.scoring import (
    parse_effort_hours,
    compute_score,
    score_findings,
    MIN_EFFORT_HOURS,
    DEFAULT_EFFORT_HOURS,
)
from skills.debrief.gap_engine.__lib.dependency_order import order_findings
from skills.debrief.gap_engine.__lib.machine_render import build_triage, render_machine_format
from skills.debrief.gap_engine.__lib.coverage import compute_health_score


def mk(
    id="F1", severity="high", action="recover", evidence_level="verified",
    effort=None, root_cause="unknown", radius=0, domain="other",
    depends_on=None, status="open",
):
    f = Finding(
        id=id, title=f"T-{id}", description="d", source_type="detector",
        source_name="x", domain=domain, gap_type="g", severity=severity,
        evidence_level=evidence_level, action=action, priority=severity,
        effort=effort, root_cause=root_cause, depends_on=depends_on or [],
        status=status,
    )
    if radius:
        f.metadata["impact_radius"] = radius
    return f


class TestParseEffort:
    def test_minutes(self):
        # 5 min = 0.083h, floored to MIN_EFFORT_HOURS
        assert parse_effort_hours("~5min") == MIN_EFFORT_HOURS
        assert parse_effort_hours("30min") == 0.5

    def test_hours_and_days(self):
        assert parse_effort_hours("2h") == 2.0
        assert parse_effort_hours("1 day") == 8.0

    def test_missing_and_unknown(self):
        assert parse_effort_hours(None) == DEFAULT_EFFORT_HOURS
        assert parse_effort_hours("") == DEFAULT_EFFORT_HOURS
        assert parse_effort_hours("unknown") == DEFAULT_EFFORT_HOURS

    def test_unparseable_defaults(self):
        assert parse_effort_hours("soon-ish") == DEFAULT_EFFORT_HOURS


class TestComputeScore:
    def test_cheap_high_beats_expensive_critical(self):
        crit, _ = compute_score(mk("A", "critical", effort="2h"))
        cheap, _ = compute_score(mk("B", "high", effort="5min"))
        assert cheap > crit  # leverage = value / effort

    def test_unverified_discounted(self):
        verified, _ = compute_score(mk("V", "medium", evidence_level="verified"))
        unverified, _ = compute_score(mk("U", "high", evidence_level="unverified"))
        # a verified medium can outrank an unverified high
        assert verified > unverified

    def test_impact_radius_raises_score(self):
        low, _ = compute_score(mk("L", "high", effort="1h", radius=0))
        high, _ = compute_score(mk("H", "high", effort="1h", radius=20))
        assert high > low

    def test_components_recorded(self):
        _, comps = compute_score(mk("C", "high", effort="1h"))
        assert {"severity_w", "action_w", "confidence_w", "impact_factor",
                "effort_hours", "value"} <= comps.keys()


class TestOrdering:
    def test_security_not_buried(self):
        q = mk("Q", "high", domain="quality", effort="1h")
        s = mk("S", "critical", domain="security", effort="1h")
        ordered = order_findings(score_findings([q, s]))
        assert ordered[0].id == "S"

    def test_leverage_drives_order(self):
        crit = mk("A", "critical", effort="2h")
        cheap = mk("B", "high", effort="5min")
        low = mk("C", "low")
        ordered = order_findings(score_findings([crit, cheap, low]))
        assert ordered[0].id == "B"  # cheap high-leverage first

    def test_stable_by_id_when_unscored(self):
        # Unscored findings (no metadata score) all get 0.0; order falls back.
        a = mk("Z", "high")
        b = mk("A", "high")
        ordered = order_findings([a, b])
        assert [f.id for f in ordered] == ["A", "Z"]


class TestTriage:
    def test_root_cause_collapse(self):
        g1 = mk("G1", "high", root_cause="missing_context")
        g2 = mk("G2", "high", root_cause="missing_context")
        g3 = mk("G3", "medium")
        entries = build_triage(score_findings([g1, g2, g3]), 3)
        assert any("resolves 2 findings" in e for e in entries)

    def test_top_n_limit(self):
        findings = score_findings([mk(f"F{i}", "high") for i in range(10)])
        assert len(build_triage(findings, 3)) == 3

    def test_zero_disables(self):
        assert build_triage(score_findings([mk("A", "high")]), 0) == []

    def test_resolved_excluded(self):
        resolved = mk("R", "critical", status="resolved")
        assert build_triage(score_findings([resolved]), 3) == []


class TestMachineFormatDependencyFields:
    def test_caused_by_and_blocks_populated(self):
        base = mk("D0", "high")
        dependent = mk("D1", "high", depends_on=["D0"])
        out = render_machine_format(score_findings([base, dependent]))
        assert "caused_by=D0" in out  # D1 waits on D0
        assert "blocks=D1" in out     # D0 blocks D1

    def test_score_field_appended(self):
        out = render_machine_format(score_findings([mk("A", "high")]))
        assert "score=" in out

    def test_terminator_preserved(self):
        out = render_machine_format(score_findings([mk("A", "high")]))
        assert "RNS|Z|0|NONE" in out
        assert "RNS|D|" in out


class TestHealthTrend:
    def test_improving(self):
        h = compute_health_score([mk("A", "low")], "fresh", prev_score=10)
        assert h["trend"] == "improving"
        assert h["delta"] == h["score"] - 10

    def test_declining(self):
        h = compute_health_score([mk("A", "critical")], "fresh", prev_score=95)
        assert h["trend"] == "declining"

    def test_no_prev_score_omits_trend(self):
        h = compute_health_score([mk("A", "low")], "fresh")
        assert "trend" not in h
        assert "delta" not in h

    def test_empty_findings_with_trend(self):
        h = compute_health_score([], "fresh", prev_score=80)
        assert h["score"] == 100
        assert h["trend"] == "improving"
