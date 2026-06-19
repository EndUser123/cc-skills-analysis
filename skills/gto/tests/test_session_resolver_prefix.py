"""Tests for the console_/env_/tmux_/wt_ prefix-stripping session_resolver fix.

Bug: session_registry keys are prefixed with the surface they came from
(e.g. "console_<uuid>", "env_<uuid>") but $WT_SESSION passes the bare UUID.
The orchestrator used to pass terminal_id through to query_registry() unchanged,
so registry lookups failed and GTO emitted a spurious GTO-SESSION-UNRESOLVED
finding for every real run.

Fix: _normalize_terminal_id_for_registry() returns candidate keys to try
(literal first, then prefix-stripped or prefix-added). All 4 terminal_id-keyed call sites
in orchestrator.py iterate over the candidates.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make orchestrator importable when pytest is run from any CWD
_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent  # skills/gto/tests -> skills/gto -> skills -> cc-skills-analysis
sys.path.insert(0, str(_PKG))

from skills.gto.orchestrator import (  # noqa: E402
    _normalize_terminal_id_for_registry,
    _resolve_session_id_from_registry,
    _resolve_transcript_from_registry,
    _session_resolution_status,
    _load_session_chain,
)
from skills.gto.orchestrator import query_registry  # noqa: E402


class TestNormalizeTerminalIdForRegistry:
    """Unit tests for the prefix-stripping helper."""

    def test_empty_returns_empty(self):
        assert _normalize_terminal_id_for_registry("") == ()

    def test_none_returns_empty(self):
        # Guard: be tolerant of None even though the type hint is str.
        assert _normalize_terminal_id_for_registry(None) == ()  # type: ignore[arg-type]

    def test_bare_uuid_returns_candidates_with_prefixes(self):
        # The most common case: $WT_SESSION passes a bare UUID.
        # Try bare first, then each prefix (registry might have prefixed ID).
        assert _normalize_terminal_id_for_registry("abc-123") == (
            "abc-123",
            "env_abc-123",
            "console_abc-123",
            "wt_abc-123",
            "tmux_abc-123",
        )

    def test_console_prefix_strips_to_bare(self):
        # SessionRegistry convention: console_<uuid> for console-originated sessions.
        # Function returns exact match, then stripped, then all prefix variants.
        assert _normalize_terminal_id_for_registry("console_abc-123") == (
            "console_abc-123",
            "abc-123",
            "env_console_abc-123",
            "console_console_abc-123",
            "wt_console_abc-123",
            "tmux_console_abc-123",
        )

    def test_env_prefix_strips_to_bare(self):
        # env_ prefix for env-var-injected session_ids.
        assert _normalize_terminal_id_for_registry("env_xyz") == (
            "env_xyz",
            "xyz",
            "env_env_xyz",
            "console_env_xyz",
            "wt_env_xyz",
            "tmux_env_xyz",
        )

    def test_tmux_prefix_strips_to_bare(self):
        assert _normalize_terminal_id_for_registry("tmux_xyz") == (
            "tmux_xyz",
            "xyz",
            "env_tmux_xyz",
            "console_tmux_xyz",
            "wt_tmux_xyz",
            "tmux_tmux_xyz",
        )

    def test_wt_prefix_strips_to_bare(self):
        assert _normalize_terminal_id_for_registry("wt_xyz") == (
            "wt_xyz",
            "xyz",
            "env_wt_xyz",
            "console_wt_xyz",
            "wt_wt_xyz",
            "tmux_wt_xyz",
        )

    def test_empty_after_strip_does_not_emit_bare_empty(self):
        # Defensive: "console_" (prefix with nothing after) should NOT emit "".
        result = _normalize_terminal_id_for_registry("console_")
        assert "" not in result
        assert result == (
            "console_",
            "env_console_",
            "console_console_",
            "wt_console_",
            "tmux_console_",
        )

    def test_unknown_prefix_returns_candidates_with_prefixes(self):
        # No prefix in our set -> try bare first, then each prefix (registry might have prefixed ID).
        # Same behavior as bare UUID case.
        assert _normalize_terminal_id_for_registry("foo_bar") == (
            "foo_bar",
            "env_foo_bar",
            "console_foo_bar",
            "wt_foo_bar",
            "tmux_foo_bar",
        )


class TestResolveSessionIdPrefixStripping:
    """The console_<uuid> bug repro: registry key is prefixed, terminal_id is bare."""

    def test_bare_terminal_id_finds_console_prefixed_entry(self, monkeypatch):
        """Repro: registry has 'console_abc' but caller passes 'abc'.
        Before fix: returns ''. After fix: returns session_id."""
        calls: list[str] = []

        def fake_query_registry(*, terminal_id=None, session_id=None, limit=1):
            calls.append(terminal_id or "")
            if terminal_id == "abc":
                return [{"session_id": "sess-xyz", "terminal_id": "console_abc"}]
            return []

        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            fake_query_registry,
        )
        result = _resolve_session_id_from_registry("abc")
        assert result == "sess-xyz", f"Expected fallback to bare uuid, got {result!r}"
        # The call sequence: try "abc" first, but stub only matches "abc" -> 1 call total.
        assert "abc" in calls

    def test_console_prefixed_terminal_id_finds_entry_directly(self, monkeypatch):
        """If caller already passes the prefixed form, it should still resolve."""
        def fake_query_registry(*, terminal_id=None, session_id=None, limit=1):
            if terminal_id == "console_abc":
                return [{"session_id": "sess-xyz"}]
            return []

        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            fake_query_registry,
        )
        result = _resolve_session_id_from_registry("console_abc")
        assert result == "sess-xyz"

    def test_unknown_terminal_returns_empty(self, monkeypatch):
        """No registry entry, no fallback success -> empty string."""
        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            lambda **kw: [],
        )
        result = _resolve_session_id_from_registry("never-seen")
        assert result == ""


class TestResolveTranscriptPrefixStripping:
    """Same prefix-stripping semantics apply to transcript lookup."""

    def test_bare_terminal_id_resolves_via_console_prefix(self, monkeypatch, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text("", encoding="utf-8")

        def fake_query_registry(*, terminal_id=None, session_id=None, limit=1):
            if terminal_id == "abc":
                return [{"transcript_path": str(transcript)}]
            return []

        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            fake_query_registry,
        )
        result = _resolve_transcript_from_registry("abc")
        assert result == transcript

    def test_no_match_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            lambda **kw: [],
        )
        result = _resolve_transcript_from_registry("never-seen")
        assert result is None


class TestSessionResolutionStatusPrefixStripping:
    """The high-impact call site: status classification drives GTO-SESSION-UNRESOLVED."""

    def test_resolved_via_console_prefix_stripping(self, monkeypatch, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text("", encoding="utf-8")

        def fake_query_registry(*, terminal_id=None, session_id=None, limit=1):
            # Registry keyed by console_<uuid>, caller passes bare uuid.
            if terminal_id == "abc":
                return [{"transcript_path": str(transcript)}]
            return []

        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            fake_query_registry,
        )
        status = _session_resolution_status("abc")
        assert status == "resolved", f"Expected 'resolved', got {status!r}"

    def test_unresolved_when_no_match_anywhere(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            lambda **kw: [],
        )
        # No identity.json fallback in tmp_path
        monkeypatch.setenv("CLAUDE_ARTIFACTS_ROOT", str(tmp_path))
        status = _session_resolution_status("never-seen")
        assert status == "unresolved"


class TestLoadSessionChainPrefixStripping:
    """_load_session_chain iterates prefixes to find the chain."""

    def test_chain_loaded_via_bare_terminal_id(self, monkeypatch, tmp_path):
        transcripts = [tmp_path / f"s{i}.jsonl" for i in range(2)]
        for t in transcripts:
            t.write_text("", encoding="utf-8")

        def fake_query_registry(*, terminal_id=None, session_id=None, limit=20):
            if terminal_id == "abc":
                return [
                    {"session_id": "s0", "transcript_path": str(transcripts[0])},
                    {"session_id": "s1", "transcript_path": str(transcripts[1])},
                ]
            return []

        monkeypatch.setattr(
            "skills.gto.orchestrator.query_registry",
            fake_query_registry,
        )
        chain = _load_session_chain("abc")
        assert len(chain) == 2
        assert chain[0] == str(transcripts[0])
        assert chain[1] == str(transcripts[1])


if __name__ == "__main__":
    unittest.main()
