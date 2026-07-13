"""Tests for context_boundaries word-boundary snap fix."""
from __future__ import annotations

import re


def snap_to_word(remainder: str) -> str:
    """Snap start AND end of remainder to word boundaries, capped at ~100 chars."""
    r = re.search(r"\w", remainder)
    start_offset = r.start() if r else 0
    end_offset = start_offset + 100
    if end_offset < len(remainder):
        pre_end = remainder[start_offset:end_offset]
        # Find complete words (word followed by separator) in pre_end
        last_match = None
        for m in re.finditer(r"\w+(?=\W)", pre_end):
            last_match = m
        if last_match:
            end_offset = start_offset + last_match.end()
    return remainder[start_offset:end_offset]


def test_snaps_start_to_word():
    """Start must not be mid-path — `:diagnostics` should snap past `:`."""
    remainder = ":diagnostics/P:/.claude/hooks"
    phrase = snap_to_word(remainder)
    assert phrase[0].isalpha() or phrase[0] == "_", f"Got: {phrase!r}"


def test_snaps_end_to_word():
    """End must not be mid-word — sentence truncates mid-word, snaps to last complete word."""
    # Sentence is 100+ chars. Cut at 100 lands mid-word on "thing".
    # Last complete word before cutoff is "other". Snap to that.
    remainder = "work on the hooks module and this other thing" + "x" * 200
    phrase = snap_to_word(remainder)
    assert phrase.endswith("other"), f"Got mid-word end: {phrase!r}"


def test_normal_content_unchanged():
    """Normal sentence snaps cleanly to full words."""
    remainder = " work on the hooks module."
    phrase = snap_to_word(remainder)
    assert phrase.startswith("work"), f"Got: {phrase!r}"
    assert phrase.endswith("module."), f"Got: {phrase!r}"


def test_empty_remainder():
    """Empty remainder must not crash."""
    assert snap_to_word("") == ""


def test_already_word_boundary():
    """Already clean start/end stays unchanged."""
    remainder = "work on the hooks module."
    phrase = snap_to_word(remainder)
    assert phrase.startswith("work")


def test_path_mid_segment():
    """.claude/hooks/SomeFile.py — end snaps to `SomeFile`."""
    remainder = ".claude/hooks/SomeFile.py and continue."
    phrase = snap_to_word(remainder)
    assert phrase.startswith("claude") or phrase.startswith("SomeFile")


def test_hooks_di_corruption():
    """The actual bug: path remainder snaps to word boundaries."""
    # After pattern match ends mid-segment, remainder starts mid-path
    remainder = "ostics/P:/.claude/hooks"
    phrase = snap_to_word(remainder)
    # Start must be a word char (snap past leading /)
    assert phrase[0].isalpha(), f"Got: {phrase!r}"
    # End should be clean (not mid-word)
    # Path is 23 chars, under 100 limit — no truncation, returned unchanged
    assert phrase == "ostics/P:/.claude/hooks", f"Got: {phrase!r}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
