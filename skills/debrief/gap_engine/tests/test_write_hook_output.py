"""Tests for write_hook_output normalization logic in common.py."""

from __future__ import annotations

import json

import pytest

from skills.debrief.gap_engine.hooks.common import write_hook_output


def _output(capsys: pytest.CaptureFixture[str]) -> dict:
    """Parse the JSON output from write_hook_output."""
    captured = capsys.readouterr()
    return json.loads(captured.out.strip())


# ─────────────────────────────────────────────────────────────────────────────
# Legacy decision synonyms
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyDecisionSynonyms:
    def test_allow_normalized_to_approve(self, capsys):
        write_hook_output({"decision": "allow"})
        assert _output(capsys)["decision"] == "approve"

    def test_deny_normalized_to_block(self, capsys):
        write_hook_output({"decision": "deny"})
        out = _output(capsys)
        assert out["decision"] == "block"
        assert "reason" in out

    def test_warn_normalized_to_approve(self, capsys):
        write_hook_output({"decision": "warn"})
        out = _output(capsys)
        assert out["decision"] == "approve"
        assert "reason" in out

    def test_warn_preserves_reason(self, capsys):
        write_hook_output({"decision": "warn", "reason": "check this"})
        out = _output(capsys)
        assert out["decision"] == "approve"
        assert out["reason"] == "check this"

    def test_approve_passes_through(self, capsys):
        write_hook_output({"decision": "approve"})
        assert _output(capsys)["decision"] == "approve"

    def test_block_passes_through(self, capsys):
        write_hook_output({"decision": "block", "reason": "nope"})
        out = _output(capsys)
        assert out["decision"] == "block"
        assert out["reason"] == "nope"


# ─────────────────────────────────────────────────────────────────────────────
# Field preservation (the spread-operator bug)
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldPreservation:
    def test_allow_false_preserves_extra_fields(self, capsys):
        write_hook_output({"allow": False, "blocking_hook": True, "hook_name": "test"})
        out = _output(capsys)
        assert out["decision"] == "block"
        assert out["blocking_hook"] is True
        assert out["hook_name"] == "test"

    def test_allow_true_preserves_extra_fields(self, capsys):
        write_hook_output({"allow": True, "blocking_hook": False, "source": "guard"})
        out = _output(capsys)
        assert out["decision"] == "approve"
        assert out["blocking_hook"] is False
        assert out["source"] == "guard"

    def test_continue_false_preserves_extra_fields(self, capsys):
        write_hook_output({"continue": False, "blocking_hook": True, "detail": "x"})
        out = _output(capsys)
        assert out["decision"] == "block"
        assert out["blocking_hook"] is True
        assert out["detail"] == "x"

    def test_continue_true_preserves_extra_fields(self, capsys):
        write_hook_output({"continue": True, "tag": "y"})
        out = _output(capsys)
        assert out["decision"] == "approve"
        assert out["tag"] == "y"

    def test_ok_preserves_extra_fields(self, capsys):
        write_hook_output({"ok": True, "meta": "z"})
        out = _output(capsys)
        assert out["decision"] == "approve"
        assert out["meta"] == "z"

    def test_legacy_deny_preserves_extra_fields(self, capsys):
        write_hook_output({"decision": "deny", "blocking_hook": True})
        out = _output(capsys)
        assert out["decision"] == "block"
        assert out["blocking_hook"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_dict(self, capsys):
        write_hook_output({})
        assert _output(capsys) == {}

    def test_decision_takes_priority_over_allow(self, capsys):
        write_hook_output({"decision": "block", "allow": True})
        assert _output(capsys)["decision"] == "block"

    def test_allow_false_with_reason(self, capsys):
        write_hook_output({"allow": False, "reason": "blocked by guard"})
        out = _output(capsys)
        assert out["decision"] == "block"
        assert out["reason"] == "blocked by guard"

    def test_output_is_valid_json(self, capsys):
        write_hook_output({"decision": "approve", "reason": "ok", "extra": [1, 2]})
        captured = capsys.readouterr()
        raw = captured.out.strip()
        parsed = json.loads(raw)
        assert parsed["extra"] == [1, 2]
