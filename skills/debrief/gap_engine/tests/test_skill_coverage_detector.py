from __future__ import annotations

import json

from skills.debrief.gap_engine.__lib import skill_coverage_detector as detector


def test_append_skill_coverage_preserves_jsonl_event_contract(tmp_path, monkeypatch):
    path = tmp_path / "coverage.jsonl"
    monkeypatch.setattr(detector, "_coverage_path", lambda _target: path)

    assert detector._append_skill_coverage(
        target_key="skills/trace",
        skill="/trace",
        terminal_id="term-1",
        git_sha="abc123",
    ) is True

    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["skill"] == "/trace"
    assert event["target"] == "skills/trace"
    assert event["terminal_id"] == "term-1"
    assert event["git_sha"] == "abc123"
    assert event["gap_ids_targeted"] == []
    assert event["timestamp"]
