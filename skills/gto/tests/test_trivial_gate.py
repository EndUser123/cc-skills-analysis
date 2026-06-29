"""CHANGE-005/006: the trivial-run predicate gates handoff writes and the FP marker.

Boundary (from plan acceptance):
  - <3 findings AND all low severity -> trivial (skip handoffs, exempt from marker)
  - exactly 3 findings -> non-trivial (writes handoffs)
  - any non-low severity among <3 -> non-trivial (writes handoffs)
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent
sys.path.insert(0, str(_PKG))

from skills.gto.orchestrator import _is_trivial_run  # noqa: E402
from skills.gto.models import Finding  # noqa: E402


def _f(severity: str = "low") -> Finding:
    return Finding(
        id="X",
        title="x",
        description="",
        source_type="detector",
        source_name="test",
        domain="other",
        gap_type="unknown",
        severity=severity,
        evidence_level="unverified",
    )


def test_empty_is_trivial():
    assert _is_trivial_run([]) is True


def test_one_low_is_trivial():
    assert _is_trivial_run([_f("low")]) is True


def test_two_low_is_trivial():
    assert _is_trivial_run([_f("low"), _f("low")]) is True


def test_three_low_is_non_trivial_boundary():
    assert _is_trivial_run([_f("low"), _f("low"), _f("low")]) is False


def test_two_with_one_non_low_is_non_trivial():
    assert _is_trivial_run([_f("low"), _f("high")]) is False


def test_single_non_low_is_non_trivial():
    assert _is_trivial_run([_f("critical")]) is False


def test_missing_severity_treated_as_non_low():
    # A finding with no severity should not count as low (defensive).
    f = Finding(
        id="X", title="x", description="", source_type="detector", source_name="test",
        domain="other", gap_type="unknown", severity=None,  # type: ignore[arg-type]
        evidence_level="unverified",
    )
    assert _is_trivial_run([f]) is False
