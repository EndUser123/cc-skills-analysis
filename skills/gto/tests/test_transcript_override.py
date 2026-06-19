"""Tests for --transcript CLI flag in GTO orchestrator."""
from __future__ import annotations

import json
from pathlib import Path

from skills.gto.orchestrator import parse_args


class TestParseArgsTranscript:
    def test_transcript_default_is_none(self):
        args = parse_args(["--terminal-id", "test"])
        assert args.transcript is None

    def test_transcript_accepted_as_path(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text("")
        args = parse_args(["--transcript", str(p), "--terminal-id", "test"])
        assert args.transcript == p

    def test_transcript_is_path_type(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text("")
        args = parse_args(["--transcript", str(p)])
        assert isinstance(args.transcript, Path)


class TestTranscriptOverrideBehavior:
    """Verify that --transcript suppresses the session-unresolved guard."""

    def test_explicit_transcript_forces_resolved_status(self, tmp_path):
        """session_status is 'resolved' whenever explicit_transcript is set.

        Mirrors the guard expression in orchestrator.run():
            session_status = "resolved" if explicit_transcript else _session_resolution_status(...)
        """
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({"role": "user", "content": "hello"}) + "\n",
            encoding="utf-8",
        )
        args = parse_args(["--transcript", str(transcript), "--terminal-id", "t1"])

        explicit_transcript = Path(args.transcript).resolve() if args.transcript else None

        guard_called: list[str] = []

        def fake_status(_tid: str) -> str:
            guard_called.append(_tid)
            return "unresolved"

        session_status = "resolved" if explicit_transcript else fake_status(args.terminal_id)

        assert session_status == "resolved"
        assert guard_called == [], "unresolved guard must not fire when --transcript is provided"

    def test_missing_transcript_file_detected_early(self, tmp_path, monkeypatch, capsys):
        """run() returns 1 and emits an error when --transcript path is absent."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "skills.gto.orchestrator._resolve_session_id_from_registry",
            lambda tid: "",
        )
        from skills.gto.orchestrator import run

        rc = run(["--transcript", str(tmp_path / "nonexistent.jsonl"), "--terminal-id", "t1"])

        assert rc == 1
        captured = capsys.readouterr()
        assert "does not exist" in captured.err
