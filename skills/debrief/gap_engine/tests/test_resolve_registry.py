"""Tests for resolve.py: registry dispatch, terminal-status short-circuit, and
the GAP-SESSION --transcript resolution path (closes #901).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent  # skills/debrief/gap_engine/tests -> skills/debrief/gap_engine -> skills -> cc-skills-analysis
sys.path.insert(0, str(_PKG))

from skills.debrief.gap_engine.__lib.resolve import (  # noqa: E402
    RESOLUTION_STRATEGIES,
    ResolveCtx,
    resolve_findings,
)
from skills.debrief.gap_engine.models import Finding  # noqa: E402


def _finding(fid: str, **kw) -> Finding:
    base = dict(
        id=fid,
        title=fid,
        description="",
        source_type="detector",
        source_name="test",
        domain="other",
        gap_type="unknown",
        severity="medium",
        evidence_level="unverified",
    )
    base.update(kw)
    return Finding(**base)


def _ctx(root: Path, **kw) -> ResolveCtx:
    return ResolveCtx(edited_file_set=kw.pop("edited_file_set", set()), root=root, **kw)


class TestRegistryDocGitPreserved:
    def test_doc_resolves_when_readme_exists(self, tmp_path):
        (tmp_path / "README.md").write_text("hi", encoding="utf-8")
        out = resolve_findings([_finding("DOC-001")], _ctx(tmp_path))
        assert out[0].status == "resolved"
        assert any("README.md now exists" in e.value for e in out[0].evidence)

    def test_doc_unresolved_when_readme_absent(self, tmp_path):
        out = resolve_findings([_finding("DOC-001")], _ctx(tmp_path))
        assert out[0].status == "open"

    def test_git_resolves_when_dotgit_exists(self, tmp_path):
        (tmp_path / ".git").mkdir()
        out = resolve_findings([_finding("GIT-001")], _ctx(tmp_path))
        assert out[0].status == "resolved"

    def test_git_unresolved_when_dotgit_absent(self, tmp_path):
        out = resolve_findings([_finding("GIT-001")], _ctx(tmp_path))
        assert out[0].status == "open"


class TestUnknownIdUnresolved:
    def test_no_prefix_match_stays_open(self, tmp_path):
        out = resolve_findings([_finding("FOO-001")], _ctx(tmp_path))
        assert out[0].status == "open"


class TestLongestPrefixWins:
    def test_session_prefix_beats_hypothetical_gap_prefix(self, tmp_path, monkeypatch):
        # A shorter "GAP-" strategy is registered; GAP-SESSION-* must still dispatch
        # to the longer GAP-SESSION strategy, not the shorter one.
        calls: list[str] = []

        def shorter(_f, _ctx):
            calls.append("shorter")
            return "shorter"

        def longer(_f, _ctx):
            calls.append("longer")
            return "longer"

        monkeypatch.setitem(RESOLUTION_STRATEGIES, "GAP-", shorter)
        monkeypatch.setitem(RESOLUTION_STRATEGIES, "GAP-SESSION", longer)
        out = resolve_findings(
            [_finding("GAP-SESSION-UNRESOLVED")], _ctx(tmp_path, transcript_explicit=True)
        )
        assert calls == ["longer"]
        assert out[0].status == "resolved"


class TestSessionTranscriptResolution:
    """The #901 fix: a pre-existing GAP-SESSION-UNRESOLVED carryover finding must
    resolve on the next run when --transcript is supplied (transcript_explicit=True)."""

    def test_resolves_when_transcript_explicit(self, tmp_path):
        f = _finding("GAP-SESSION-UNRESOLVED", status="open")
        out = resolve_findings([f], _ctx(tmp_path, transcript_explicit=True))
        assert out[0].status == "resolved"
        assert any("--transcript" in e.value for e in out[0].evidence)

    def test_not_resolved_without_transcript(self, tmp_path):
        f = _finding("GAP-SESSION-UNRESOLVED", status="open")
        out = resolve_findings([f], _ctx(tmp_path, transcript_explicit=False))
        assert out[0].status == "open"


class TestTerminalStatusNotReresolved:
    """SM-002: a finding already in a terminal status must not be flipped to
    resolved by a later file edit or strategy match."""

    @pytest.mark.parametrize("status", ["resolved", "deferred", "rejected", "mapped"])
    def test_terminal_status_survives_file_edit(self, status, tmp_path):
        (tmp_path / "README.md").write_text("hi", encoding="utf-8")
        f = _finding("DOC-001", status=status, file="README.md")
        ctx = _ctx(tmp_path, edited_file_set={"README.md"})
        out = resolve_findings([f], ctx)
        assert out[0].status == status, f"{status} finding was re-resolved to {out[0].status}"
        assert not any(e.kind == "auto_resolved" for e in out[0].evidence)


class TestFileEditResolution:
    def test_file_edit_match_resolves(self, tmp_path):
        f = _finding("X-001", file="src/app.py")
        out = resolve_findings([f], _ctx(tmp_path, edited_file_set={"src/app.py"}))
        assert out[0].status == "resolved"
        assert any("file_edited" in e.value for e in out[0].evidence)

    def test_file_edit_normalizes_backslashes(self, tmp_path):
        f = _finding("X-001", file="src\\app.py")
        out = resolve_findings([f], _ctx(tmp_path, edited_file_set={"src/app.py"}))
        assert out[0].status == "resolved"
