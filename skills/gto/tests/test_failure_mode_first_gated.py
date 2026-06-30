r"""Regression: failure_mode_first must fire only on a structured task-close
marker, never on bare prose mentions of "fixed"/"resolved".

C-1 defect (verified 2026-06-30 on real transcript 5cb99096...): the prose
pattern ``(?:fixed|fixed\s+the|resolved)\s+(...)`` fired 14 times, every one a
false positive — captures included assistant meta-discussion of the word
"resolved" and DISPATCH-question prose. The gate keys off an explicit
``#<digits> (resolved|done|completed|fixed|closed)`` marker instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent
sys.path.insert(0, str(_PKG))

from skills.gto.__lib.chat_history_patterns import ChatHistoryPatterns


def _write_transcript(path: Path, lines: list[tuple[str, str]]) -> None:
    import json
    with path.open("w", encoding="utf-8") as f:
        for role, ln in lines:
            f.write(json.dumps({"role": role, "content": ln}) + "\n")


def _fmf(triggers: list) -> list:
    return [t for t in triggers if t.trigger_type == "failure_mode_first"]


def test_marker_fires_failure_mode_first(tmp_path: Path) -> None:
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, [("user", "shipped the fix — #900 resolved")])

    fmf = _fmf(ChatHistoryPatterns().detect_self_reflection_triggers(tp))

    assert len(fmf) == 1
    assert fmf[0].context == "task #900"
    assert fmf[0].priority == "high"


def test_bare_prose_fixed_does_not_fire(tmp_path: Path) -> None:
    # The exact FP shape from the real transcript: "resolved" appearing in
    # analysis/meta-discussion prose, no task marker.
    tp = tmp_path / "t.jsonl"
    _write_transcript(
        tp,
        [("assistant", "DISPATCH QUESTION: SessionStart is registered to the resolved path")],
    )

    fmf = _fmf(ChatHistoryPatterns().detect_self_reflection_triggers(tp))

    assert fmf == [], f"bare-prose 'resolved' fired failure_mode_first: {fmf}"


def test_marker_dedupes_per_task(tmp_path: Path) -> None:
    # Same task closed twice (#900 resolved + #900 done) -> one trigger.
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp, [("user", "#900 resolved"), ("assistant", "#900 done")])

    fmf = _fmf(ChatHistoryPatterns().detect_self_reflection_triggers(tp))

    assert len(fmf) == 1
    assert fmf[0].context == "task #900"
