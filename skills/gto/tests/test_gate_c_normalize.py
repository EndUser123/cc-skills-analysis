"""CHANGE-007 e2e: Gate C (absence-signal respect) was inert because
write_handoff emits signals_absent as list[dict] but the gate checks str
membership. _load_handoff_context now normalizes at the read boundary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent
sys.path.insert(0, str(_PKG))

from skills.gto.agents._quality_gates import apply_quality_gates  # noqa: E402
from skills.gto.agents.gap_reviewer import _load_handoff_context  # noqa: E402
from skills.gto.models import Finding  # noqa: E402


def _finding(**kw) -> Finding:
    base = dict(
        id="Q-001",
        title="missing tests",
        description="module X has no tests",
        source_type="agent",
        source_name="gap_reviewer",
        domain="quality",
        gap_type="missingtests",
        severity="high",
        evidence_level="unverified",
    )
    base.update(kw)
    return Finding(**base)


def test_load_normalizes_dict_signals_to_strings(tmp_path):
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "signals_absent": [
                    {"detector": "verification_debt_detector", "result": "no findings"},
                    {"detector": "hook_health_detector", "result": "no findings"},
                ],
                "detectors_ran": ["verification_debt_detector"],
            }
        ),
        encoding="utf-8",
    )
    signals_absent, detectors_ran = _load_handoff_context(handoff)
    assert signals_absent == ["verification_debt_detector", "hook_health_detector"]
    assert detectors_ran == ["verification_debt_detector"]


def test_load_passes_through_plain_string_entries(tmp_path):
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps({"signals_absent": ["verification_debt_detector"]}),
        encoding="utf-8",
    )
    signals_absent, _ = _load_handoff_context(handoff)
    assert signals_absent == ["verification_debt_detector"]


def test_load_drops_malformed_entries(tmp_path, capsys):
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "signals_absent": [
                    {"detector": "verification_debt_detector"},
                    {"result": "no detector key"},
                    42,
                    "plain_string",
                    None,
                ]
            }
        ),
        encoding="utf-8",
    )
    signals_absent, _ = _load_handoff_context(handoff)
    # Only the dict-with-detector and plain_string survive; others dropped with warning.
    assert signals_absent == ["verification_debt_detector", "plain_string"]
    err = capsys.readouterr().err
    assert "GATE_C_NORMALIZE_DROPPED" in err


def test_gate_c_fires_after_normalization_e2e(tmp_path):
    """Before CHANGE-007: dict-shaped signals_absent made `det in signals_absent`
    always False, so Gate C never down-ranked. After normalization it fires."""
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "signals_absent": [
                    {"detector": "verification_debt_detector", "result": "no findings"}
                ],
                "detectors_ran": ["verification_debt_detector"],
            }
        ),
        encoding="utf-8",
    )
    signals_absent, detectors_ran = _load_handoff_context(handoff)

    f = _finding(severity="high", priority="high")
    out = apply_quality_gates([f], signals_absent=signals_absent, detectors_ran=detectors_ran)
    assert out[0].metadata.get("downgraded_absent_signal") is True
    assert out[0].priority == "low"
    assert out[0].metadata.get("conflicting_absent_detector") == "verification_debt_detector"


def test_gate_c_inert_when_signals_absent_empty(tmp_path):
    """Gate C early-returns when signals_absent is empty (no absence evidence)."""
    handoff = tmp_path / "handoff.json"
    handoff.write_text(json.dumps({"signals_absent": []}), encoding="utf-8")
    signals_absent, detectors_ran = _load_handoff_context(handoff)
    f = _finding(severity="high", priority="high")
    out = apply_quality_gates([f], signals_absent=signals_absent, detectors_ran=detectors_ran)
    assert out[0].metadata.get("downgraded_absent_signal") is None
