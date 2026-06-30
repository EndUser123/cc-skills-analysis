r"""Regression: detect_dependency_chain must emit human labels, never raw regex.

C-2 defect (verified 2026-06-30 on real transcript 5cb99096...): the missing
field interpolated the DEPENDENCY_PATTERNS regex string, producing output like
``Missing: (?:test|test\s+for|tests?\s+for) for X``. The fix keys output off
``_DEPENDENCY_LABELS`` instead. This test locks that in: no ``(?:`` may appear
in any user-facing field of a DependencyGap.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent
sys.path.insert(0, str(_PKG))

from skills.gto.__lib.chat_history_patterns import ChatHistoryPatterns


def _write_transcript(path: Path, lines: list[str]) -> None:
    import json
    with path.open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps({"role": "assistant", "content": ln}) + "\n")


def test_dependency_gap_uses_human_label_not_regex(tmp_path: Path) -> None:
    # "created X" triggers DEPENDENCY_PATTERNS[0]; no "test" mention -> gap fires.
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, ["I created the payment module this morning"])

    gaps = ChatHistoryPatterns().detect_dependency_chain(tp)

    assert gaps, "expected at least one dependency gap"
    g = gaps[0]
    # Human label, not the regex source.
    assert g.missing_dependency.startswith("Missing: tests ")
    # No raw regex may leak into any user-facing field.
    for field in (g.completed_action, g.missing_dependency, g.evidence):
        assert "(?:" not in field, f"raw regex leaked into: {field!r}"


def test_dependency_gap_priority_matches_label(tmp_path: Path) -> None:
    # "refactored X" triggers DEPENDENCY_PATTERNS[3] -> "regression tests" -> high.
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, ["I refactored the auth service completely"])

    gaps = ChatHistoryPatterns().detect_dependency_chain(tp)
    matches = [g for g in gaps if "regression tests" in g.missing_dependency]
    assert matches, "expected a regression-tests gap"
    assert matches[0].priority == "high"


def test_structured_edits_emit_tests_gap_for_source_module(tmp_path: Path) -> None:
    # file_edits present -> structured path. A source module with no co-edited
    # test file yields exactly one high-confidence "missing tests" gap.
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, ["edited some files"])

    gaps = ChatHistoryPatterns().detect_dependency_chain(
        tp, file_edits=["src/payment.py"]
    )

    assert len(gaps) == 1, f"expected 1 gap, got {gaps}"
    g = gaps[0]
    assert g.missing_dependency == "Missing: tests for payment"
    assert g.priority == "high"
    assert g.confidence == 0.8
    assert "(?:" not in g.evidence


def test_structured_edits_skip_when_test_file_coedited(tmp_path: Path) -> None:
    # A module edited alongside its test file -> no gap (tests structurally present).
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, ["edited payment module and its test"])

    gaps = ChatHistoryPatterns().detect_dependency_chain(
        tp, file_edits=["src/payment.py", "tests/test_payment.py"]
    )

    assert gaps == [], f"expected no gaps when test co-edited, got {gaps}"


def test_structured_edits_skip_non_source_files(tmp_path: Path) -> None:
    # Docs/config edits must NOT fire "missing tests".
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, ["updated docs"])

    gaps = ChatHistoryPatterns().detect_dependency_chain(
        tp, file_edits=["README.md", "pyproject.toml", "config.json"]
    )

    assert gaps == [], f"non-source edits fired gaps: {gaps}"
