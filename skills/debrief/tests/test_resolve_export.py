#!/usr/bin/env python3
"""Tests for resolve_export.py pure helpers + CLI flag handling.

Pure-logic tests cover parse_export_session_id, find_export, is_stale.
The subprocess re-export path is exercised as a smoke test, not mocked
(TEST STRATEGY CONTRACT: unit tests for pure logic; integration for boundary).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Mirror the recap/conftest syspath pattern so this test file is runnable
# both as part of the full /go pytest suite and standalone.
SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import resolve_export as re_mod  # noqa: E402


# ---------- fixtures ----------

SAMPLE_SID = "f6917a23-7f0b-4215-94cf-e026ceec54ae"


def _write_with_frontmatter(path: Path, sid: str = SAMPLE_SID) -> None:
    path.write_text(
        "---\n"
        f'session_id: "{sid}"\n'
        'exported_at: "2026-07-10T14:27:29"\n'
        "session_count: 1\n"
        "chain_depth: 1\n"
        "---\n\n"
        "# Session Chain Export\n\n"
        f"**Root session:** {sid}\n\n",
        encoding="utf-8",
    )


def _write_legacy_no_frontmatter(path: Path, sid: str = SAMPLE_SID) -> None:
    """Export from before frontmatter shipped: only the prose Root session line."""
    path.write_text(
        "# Session Chain Export\n\n"
        f"**Root session:** {sid}  \n"
        "**Exported:** 2026-07-10 14:27:29  \n"
        "**Sessions in chain:** 1\n\n",
        encoding="utf-8",
    )


# ---------- parse_export_session_id ----------

class TestParseExportSessionId:
    def test_frontmatter_happy(self, tmp_path: Path):
        p = tmp_path / "chain_frontmatter.md"
        _write_with_frontmatter(p)
        assert re_mod.parse_export_session_id(p) == SAMPLE_SID

    def test_legacy_fallback_no_frontmatter(self, tmp_path: Path):
        p = tmp_path / "chain_legacy.md"
        _write_legacy_no_frontmatter(p)
        assert re_mod.parse_export_session_id(p) == SAMPLE_SID

    def test_frontmatter_takes_precedence_over_prose(self, tmp_path: Path):
        """Disagreement case: frontmatter and prose differ. Frontmatter wins."""
        p = tmp_path / "chain_mismatch.md"
        _write_with_frontmatter(p, sid=SAMPLE_SID)
        # Append a stale prose line that doesn't match frontmatter.
        with p.open("a", encoding="utf-8") as f:
            f.write("\n**Root session:** some-other-id\n")
        assert re_mod.parse_export_session_id(p) == SAMPLE_SID

    def test_missing_file_returns_none(self, tmp_path: Path):
        assert re_mod.parse_export_session_id(tmp_path / "nope.md") is None

    def test_empty_file_returns_none(self, tmp_path: Path):
        p = tmp_path / "empty.md"
        p.write_text("", encoding="utf-8")
        assert re_mod.parse_export_session_id(p) is None

    def test_only_frontmatter_marker_no_keys(self, tmp_path: Path):
        p = tmp_path / "no_keys.md"
        p.write_text("---\nother_key: 1\n---\n", encoding="utf-8")
        # No session_id key in frontmatter, no legacy line -> None.
        assert re_mod.parse_export_session_id(p) is None

    def test_rejects_obvious_garbage(self, tmp_path: Path):
        p = tmp_path / "garbage.md"
        p.write_text("not an export, just prose\n", encoding="utf-8")
        assert re_mod.parse_export_session_id(p) is None


# ---------- find_export ----------

class TestFindExport:
    def test_finds_match_in_exports_dir(self, tmp_path, monkeypatch):
        # Redirect the search roots.
        monkeypatch.setattr(re_mod, "EXPORTS_DIR", tmp_path / "exports")
        (tmp_path / "exports").mkdir()
        p1 = tmp_path / "exports" / f"chain_{SAMPLE_SID}_20260710.md"
        p2 = tmp_path / "exports" / f"chain_OTHER_20260710.md"
        _write_with_frontmatter(p1)
        _write_with_frontmatter(p2, sid="OTHER-aaaa-bbbb")
        assert re_mod.find_export(SAMPLE_SID) == p1

    def test_returns_most_recent_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr(re_mod, "EXPORTS_DIR", tmp_path / "exports")
        (tmp_path / "exports").mkdir()
        old = tmp_path / "exports" / f"chain_{SAMPLE_SID}_20260701.md"
        new = tmp_path / "exports" / f"chain_{SAMPLE_SID}_20260710.md"
        _write_with_frontmatter(old)
        _write_with_frontmatter(new)
        # Touch old to be older, new to be newer.
        import os
        os.utime(old, (datetime(2026, 7, 1).timestamp(),) * 2)
        os.utime(new, (datetime(2026, 7, 10).timestamp(),) * 2)
        assert re_mod.find_export(SAMPLE_SID) == new

    def test_no_match_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(re_mod, "EXPORTS_DIR", tmp_path / "exports")
        monkeypatch.setattr(re_mod, "DOWNLOADS_DIR", tmp_path / "downloads")
        (tmp_path / "exports").mkdir()
        (tmp_path / "downloads").mkdir()
        p = tmp_path / "exports" / "chain_OTHER_id.md"
        _write_with_frontmatter(p, sid="not-it")
        assert re_mod.find_export(SAMPLE_SID) is None

    def test_searches_downloads_after_exports(self, tmp_path, monkeypatch):
        monkeypatch.setattr(re_mod, "EXPORTS_DIR", tmp_path / "exports")
        monkeypatch.setattr(re_mod, "DOWNLOADS_DIR", tmp_path / "downloads")
        (tmp_path / "exports").mkdir()
        (tmp_path / "downloads").mkdir()
        # Only a Downloads hit.
        dl = tmp_path / "downloads" / f"chain_{SAMPLE_SID}_20260710.md"
        _write_with_frontmatter(dl)
        assert re_mod.find_export(SAMPLE_SID) == dl


# ---------- is_stale ----------

class TestIsStale:
    def test_transcript_newer_than_export_is_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(re_mod, "PROJECTS_DIR", tmp_path / "projects" / "P--")
        (tmp_path / "projects" / "P--").mkdir(parents=True)
        export = tmp_path / "export.md"
        transcript = tmp_path / "projects" / "P--" / f"{SAMPLE_SID}.jsonl"
        _write_with_frontmatter(export)
        transcript.write_text("[user]\nhello", encoding="utf-8")
        import os
        past = (datetime(2026, 7, 1, 12).timestamp(),) * 2
        future = (datetime(2026, 7, 10, 12).timestamp(),) * 2
        os.utime(export, past)
        os.utime(transcript, future)
        assert re_mod.is_stale(export, SAMPLE_SID) is True

    def test_export_newer_than_transcript_not_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(re_mod, "PROJECTS_DIR", tmp_path / "projects" / "P--")
        (tmp_path / "projects" / "P--").mkdir(parents=True)
        export = tmp_path / "export.md"
        transcript = tmp_path / "projects" / "P--" / f"{SAMPLE_SID}.jsonl"
        _write_with_frontmatter(export)
        transcript.write_text("[user]\nhello", encoding="utf-8")
        import os
        future = (datetime(2026, 7, 10, 12).timestamp(),) * 2
        past = (datetime(2026, 7, 1, 12).timestamp(),) * 2
        os.utime(export, future)
        os.utime(transcript, past)
        assert re_mod.is_stale(export, SAMPLE_SID) is False

    def test_missing_transcript_returns_stale(self, tmp_path, monkeypatch):
        """No live transcript -> conservatively stale so re-export rebuilds
        a known-good snapshot (no silent reuse of a phantom export)."""
        monkeypatch.setattr(re_mod, "PROJECTS_DIR", tmp_path / "projects" / "P--")
        (tmp_path / "projects" / "P--").mkdir(parents=True)
        export = tmp_path / "export.md"
        _write_with_frontmatter(export)
        assert re_mod.is_stale(export, SAMPLE_SID) is True


# ---------- CLI ----------

class TestCLI:
    def test_invalid_session_id_rejected(self, capsys):
        """Bad shape (contains spaces) — must exit 2 with invalid_session_id on stderr."""
        rc = re_mod.main(["--session-id", "bad id with spaces"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "invalid_session_id" in err

    def test_session_id_validation_regex(self):
        # chs_cli accepts whatever session_id string it receives, so the
        # validator only rejects shell-unsafe characters (spaces, slashes,
        # quotes, backticks, semicolons). Anything else passes.
        assert re_mod.SESSION_ID_RE.match(SAMPLE_SID)
        assert re_mod.SESSION_ID_RE.match("IC-MAN-test-fixture-001")
        assert re_mod.SESSION_ID_RE.match("a-b-c-d-e")
        assert re_mod.SESSION_ID_RE.match("abc123")
        # Rejections: shell-unsafe.
        assert not re_mod.SESSION_ID_RE.match("bad id")        # space
        assert not re_mod.SESSION_ID_RE.match("")              # empty
        assert not re_mod.SESSION_ID_RE.match("foo;bar")       # semicolon
        assert not re_mod.SESSION_ID_RE.match("foo/bar")       # slash
        assert not re_mod.SESSION_ID_RE.match("foo'bar")       # single-quote
        assert not re_mod.SESSION_ID_RE.match('foo"bar')       # double-quote
        assert not re_mod.SESSION_ID_RE.match("foo`bar")       # backtick