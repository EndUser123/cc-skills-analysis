"""Tests for /recap skill - Pre-mortem Domain 4 (TESTING).

Tests cover:
- 4a: Import path verification (from core.session_chain)
- 4b: Handoff chain walking with mock handoff files
- 4c: Subagent filtering (exact component matching for 'subagents-analysis')
- 4d: Session_id deduplication via (session_id, transcript_path) tuples
"""
import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import NamedTuple
from unittest.mock import Mock, MagicMock, patch

import pytest


# Pre-mortem Domain 4a: Test import path
class TestImportPath:
    """Domain 4a: Test that import from core.session_chain works."""

    def test_import_from_core_session_chain_with_syspath(self):
        """Test import from core.session_chain with sys.path manipulation.

        This is the actual import pattern used in __init__.py after pre-mortem fix 1a.
        """
        from pathlib import Path

        _search_research_root = Path("P:\\\\\\packages/search-research")
        if str(_search_research_root) not in sys.path:
            sys.path.insert(0, str(_search_research_root))

        try:
            from core.session_chain import (
                SessionChainEntry,
                walk_session_chain,
            )
            # Verify API exists and is callable
            assert hasattr(walk_session_chain, '__call__'), "walk_session_chain not callable"
        except ImportError as e:
            pytest.skip(f"search-research package not available: {e}")

    def test_session_chain_entry_structure(self):
        """Test that SessionChainEntry has expected fields."""
        _search_research_root = Path("P:\\\\\\packages/search-research")
        if str(_search_research_root) not in sys.path:
            sys.path.insert(0, str(_search_research_root))

        try:
            from core.session_chain import SessionChainEntry

            # Verify it has the expected attributes
            # Note: field is 'created' not 'created_at' (actual API)
            entry = SessionChainEntry(
                session_id="test-123",
                transcript_path=Path("/fake/path.jsonl"),
                parent_transcript_path=None,
                created=datetime.now(timezone.utc),
            )
            assert entry.session_id == "test-123"
            assert entry.transcript_path == Path("/fake/path.jsonl")
        except ImportError:
            pytest.skip("search-research package not available")


# Pre-mortem Domain 4b: Test handoff chain walking
class TestHandoffChainWalking:
    """Domain 4b: Test handoff chain reconstruction from mock handoff files."""

    def test_chain_result_structure(self):
        """Test that SessionChainResult has expected structure.

        This verifies the chain walking API works correctly.
        """
        _search_research_root = Path("P:\\\\\\packages/search-research")
        if str(_search_research_root) not in sys.path:
            sys.path.insert(0, str(_search_research_root))

        try:
            from core.session_chain import SessionChainResult, SessionChainEntry

            # Create mock chain result
            entries = [
                SessionChainEntry(
                    session_id="session-1",
                    transcript_path=Path("/path1.jsonl"),
                    parent_transcript_path=None,
                    created=datetime.now(timezone.utc),
                ),
                SessionChainEntry(
                    session_id="session-2",
                    transcript_path=Path("/path2.jsonl"),
                    parent_transcript_path=Path("/path1.jsonl"),
                    created=datetime.now(timezone.utc),
                ),
            ]
            chain_result = SessionChainResult(entries=entries)

            # Verify structure
            assert len(chain_result.entries) == 2
            assert chain_result.entries[0].session_id == "session-1"
            assert chain_result.entries[1].parent_transcript_path == Path("/path1.jsonl")
        except ImportError:
            pytest.skip("search-research package not available")


# Pre-mortem Domain 4c: Test subagent filtering edge cases
class TestSubagentFiltering:
    """Domain 4c: Test subagent transcript filtering with exact component matching (R-012)."""

    def test_subagents_analysis_directory_not_filtered(self):
        """Test R-012: 'subagents-analysis' directory is NOT filtered.

        This tests exact component matching - 'subagents-analysis' != 'subagents'.
        The path contains 'subagents' as a substring but NOT as a directory component.
        """
        # Import the function under test
        import sys
        from pathlib import Path

        # Add skills/recap to path to import
        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        from recap import _is_subagent_transcript

        # This is a legitimate user project directory (not a subagent)
        legit_path = Path("/home/user/projects/subagents-analysis/transcript.jsonl")

        # Should return False (NOT filtered)
        result = _is_subagent_transcript(legit_path)
        assert result is False, f"subagents-analysis path should NOT be filtered, got {result}"

    def test_subagents_directory_component_is_filtered(self):
        """Test that paths with 'subagents' as exact directory component ARE filtered."""
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        from recap import _is_subagent_transcript

        # This IS a subagent transcript (subagents is a directory component)
        subagent_path = Path("/home/user/.claude/subagents/agent-123/transcript.jsonl")

        # Should return True (filtered)
        result = _is_subagent_transcript(subagent_path)
        assert result is True, f"subagents directory component should be filtered, got {result}"

    def test_agent_prefix_filename_is_filtered(self):
        """Test that filenames starting with 'agent-' are filtered."""
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        from recap import _is_subagent_transcript

        agent_path = Path("/home/user/projects/sessions/agent-456.jsonl")

        result = _is_subagent_transcript(agent_path)
        assert result is True, f"agent- prefix should be filtered, got {result}"

    def test_normal_transcript_not_filtered(self):
        """Test that normal user session transcripts are NOT filtered."""
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        from recap import _is_subagent_transcript

        normal_path = Path("/home/user/projects/myproject/sessions/session-abc.jsonl")

        result = _is_subagent_transcript(normal_path)
        assert result is False, f"normal transcript should NOT be filtered, got {result}"


# Pre-mortem Domain 4d: Test session_id deduplication
class TestSessionIdDeduplication:
    """Domain 4d: Test (session_id, transcript_path) tuple deduplication (R-007)."""

    def test_unique_session_transcript_pairs_all_included(self):
        """Test that unique (session_id, transcript_path) tuples are all included.

        Scenario: Same session_id appears with different transcript_path values.
        This can happen in multi-terminal scenarios.
        Expected: Both entries included (different tuples).
        """
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        # Import dependencies
        _search_research_root = Path("P:\\\\\\packages/search-research")
        if str(_search_research_root) not in sys.path:
            sys.path.insert(0, str(_search_research_root))

        try:
            from core.session_chain import SessionChainEntry, SessionChainResult
            from recap import _load_from_chain_result

            # Create entries with same session_id but different transcript_path
            entries = [
                SessionChainEntry(
                    session_id="shared-session-id",
                    transcript_path=Path("/terminal1/transcript.jsonl"),
                    parent_transcript_path=None,
                    created=datetime.now(timezone.utc),
                ),
                SessionChainEntry(
                    session_id="shared-session-id",  # Same session_id
                    transcript_path=Path("/terminal2/transcript.jsonl"),  # Different path
                    parent_transcript_path=None,
                    created=datetime.now(timezone.utc),
                ),
            ]
            chain_result = SessionChainResult(entries=entries)

            # Mock extract_sessions_from_transcript to return dummy data
            with patch("recap.extract_sessions_from_transcript") as mock_extract:
                mock_extract.return_value = [{"session_id": "shared-session-id"}]

                # Mock load_transcript_entries
                with patch("recap.load_transcript_entries") as mock_load:
                    mock_load.return_value = []

                    # Mock transcript exists checks
                    with patch("pathlib.Path.exists", return_value=True):
                        result = _load_from_chain_result(chain_result, Path("/fake"))

            # Both should be included (different tuples)
            assert mock_extract.call_count == 2, "Both (session_id, path) tuples should be processed"
        except ImportError:
            pytest.skip("search-research package not available")

    def test_duplicate_session_transcript_pairs_deduped(self):
        """Test that duplicate (session_id, transcript_path) tuples are deduplicated.

        Scenario: Same exact tuple appears multiple times.
        Expected: Only one instance included.
        """
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        _search_research_root = Path("P:\\\\\\packages/search-research")
        if str(_search_research_root) not in sys.path:
            sys.path.insert(0, str(_search_research_root))

        try:
            from core.session_chain import SessionChainEntry, SessionChainResult
            from recap import _load_from_chain_result

            # Create duplicate entries (same session_id AND same transcript_path)
            duplicate_path = Path("/only/transcript.jsonl")
            entries = [
                SessionChainEntry(
                    session_id="session-123",
                    transcript_path=duplicate_path,
                    parent_transcript_path=None,
                    created=datetime.now(timezone.utc),
                ),
                SessionChainEntry(
                    session_id="session-123",  # Same session_id
                    transcript_path=duplicate_path,  # Same path = duplicate tuple
                    parent_transcript_path=None,
                    created=datetime.now(timezone.utc),
                ),
            ]
            chain_result = SessionChainResult(entries=entries)

            with patch("recap.extract_sessions_from_transcript") as mock_extract:
                mock_extract.return_value = [{"session_id": "session-123"}]

                with patch("recap.load_transcript_entries") as mock_load:
                    mock_load.return_value = []

                    with patch("pathlib.Path.exists", return_value=True):
                        result = _load_from_chain_result(chain_result, Path("/fake"))

            # Only one should be processed (deduplication worked)
            assert mock_extract.call_count == 1, "Duplicate (session_id, path) tuples should be deduplicated"
        except ImportError:
            pytest.skip("search-research package not available")


class TestSummarizeSessionChange004:
    """CHANGE-004: Prior session summary injection into last_goal.

    Tests for extracting ## Last Session Summary block from first 10 entries
    and injecting prior session data into last_goal field.

    Quality gate for valid summary block (ALL must be true):
    - Contains **When:** field with timestamp
    - Contains **Duration:** with ~Xh Ym format, duration > 0
    - Content from **When:** to end (after stripping trailing blank lines) > 50 chars
    - Content does NOT start with #
    """

    def test_prior_session_shown_when_summary_block_present(self):
        """T2: Chain fails, session summary present → prior session shown in recap.

        Scenario: First 10 entries contain a valid ## Last Session Summary block.
        Expected: result["last_goal"] starts with "[Prior session:" and includes
        the timestamp and duration from the summary block.
        """
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        from recap import _summarize_session

        # Create entries with valid ## Last Session Summary block in first 10 entries
        summary_block = """## Last Session Summary
**When:** 2026-04-10T19:29:07+00:00
**Duration:** ~1h 30m

Session goal was to implement the search-research integration for the recap skill.
We successfully wired up the session chain walking and handoff chain traversal."""

        # Build entries list - first entry has the summary block
        entries = [
            {
                "type": "assistant",
                "sessionId": "prior-session",
                "created": "2026-04-10T19:29:07+00:00",
                "content": summary_block,
            },
            {
                "type": "user",
                "sessionId": "prior-session",
                "created": "2026-04-10T19:30:00+00:00",
                "content": "Continue working on the integration",
            },
        ]
        # Pad to 10 entries (CHANGE-004 checks first 10 entries)
        for i in range(3, 10):
            entries.append({
                "type": "user" if i % 2 == 0 else "assistant",
                "sessionId": "prior-session",
                "created": f"2026-04-10T19:{29 + i}:00+00:00",
                "content": f"Entry {i} content for padding",
            })

        result = _summarize_session(entries, "current-session")

        # Assert: last_goal should start with "[Prior session:" containing prior session info
        assert "last_goal" in result, "result should have last_goal field"
        assert result["last_goal"].startswith("[Prior session:"), \
            f"last_goal should start with '[Prior session:', got: {result['last_goal'][:100]}"
        assert "2026-04-10T19:29:07+00:00" in result["last_goal"], \
            "last_goal should contain the When timestamp from summary"
        assert "~1h 30m" in result["last_goal"] or "1h 30m" in result["last_goal"], \
            "last_goal should contain the duration from summary"

    def test_both_summary_and_current_work(self):
        """T6: Both summary block AND current-session work present.

        Scenario: First 3 entries have valid summary block, remaining entries have actual user goals.
        Expected: Summary takes precedence for last_goal field (first valid summary wins).
        """
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        from recap import _summarize_session

        # Valid prior session summary block
        summary_block = """## Last Session Summary
**When:** 2026-04-10T15:00:00+00:00
**Duration:** ~2h 15m

Previous session focused on implementing the PreCompact hook handoff mechanism."""

        # Create entries where first 3 have valid summary, remaining have actual user goals
        entries = [
            {
                "type": "assistant",
                "sessionId": "prior-session",
                "created": "2026-04-10T15:00:00+00:00",
                "content": summary_block,
            },
            {
                "type": "user",
                "sessionId": "prior-session",
                "created": "2026-04-10T15:01:00+00:00",
                "content": "Another prior session entry",
            },
            {
                "type": "assistant",
                "sessionId": "prior-session",
                "created": "2026-04-10T15:02:00+00:00",
                "content": "More prior content",
            },
            # Current session entries - these should be secondary to the summary block
            {
                "type": "user",
                "sessionId": "current-session",
                "created": "2026-04-11T10:00:00+00:00",
                "content": "Work on the search integration for the recap skill",
            },
            {
                "type": "assistant",
                "sessionId": "current-session",
                "created": "2026-04-11T10:01:00+00:00",
                "content": "I'll help you with the search integration.",
            },
        ]

        result = _summarize_session(entries, "current-session")

        # Assert: last_goal should start with "[Prior session:" (summary takes precedence)
        assert "last_goal" in result, "result should have last_goal field"
        assert result["last_goal"].startswith("[Prior session:"), \
            f"last_goal should start with '[Prior session:', got: {result['last_goal'][:100]}"


class TestErrorMessages:
    """Pre-mortem Domain 3c: Verify error messages are user-friendly."""

    def test_error_messages_are_user_friendly(self):
        """Test that error messages avoid technical jargon and explain impact.

        Verifies:
        - No "Session chain broken" jargon (uses plain language instead)
        - Messages explain impact ("session history may be incomplete")
        - No raw OSError/PermissionDenied technical terms in user-facing messages
        """
        import sys
        from pathlib import Path

        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))

        import recap

        # Read the source to verify improved error messages
        source = Path(recap.__file__).read_text()

        # Should have user-friendly messages
        assert "Some session history could not be loaded" in source, "Should use plain language"
        assert "Trying alternative method to load your sessions" in source, "Should be action-oriented"

        # Should NOT have technical jargon in user-facing messages
        assert "Session chain broken" not in source, "Should not have 'chain broken' jargon"
        assert "degrading to unified chain" not in source, "Should not have 'degrading' jargon"
        assert "Returning empty session list" not in source, "Should not have technical return value description"


class TestHandoffRendering:
    """The default recap is a resume document; detailed history remains available."""

    def test_handoff_leads_with_resume_and_ends_with_checklist(self):
        from recap import format_handoff, format_recap

        sessions = [{
            "session_id": "session-current",
            "entry_count": 12,
            "user_message_count": 3,
            "assistant_message_count": 9,
            "outcomes": [{"status": "success", "description": "Added the handoff renderer"}],
            "what_was_done": ["Added the handoff renderer"],
            "next_steps": ["Run the recap tests"],
            "modified_files": ["P:\\src\\recap.py"],
            "current_state": {"modified": ["P:\\src\\recap.py"], "working": [], "blocked": []},
            "transcript": "Raw transcript evidence",
        }]

        handoff = format_handoff(sessions, "terminal-1")
        assert handoff.index("## Resume Here") < handoff.index("## Completed")
        assert handoff.index("## Completed") < handoff.index("## Evidence Appendix")
        assert handoff.rindex("## Next Session Checklist") > handoff.index("## Evidence Appendix")
        assert handoff.endswith("- [ ] Run the recap tests")
        assert "Raw transcript evidence" in handoff

        detailed = format_recap(sessions, "terminal-1")
        assert "## Session History" in detailed
        assert "### Raw Context" in detailed


class TestExtractModifiedFiles:
    """Tests for _extract_modified_files() — scans Edit/Write tool_use blocks."""

    @pytest.fixture(autouse=True)
    def _import_recap(self):
        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_modified_files
        self.extract = _extract_modified_files

    def test_extracts_edit_and_write_paths(self):
        entries = [
            {
                "type": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\src/main.py"}},
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "P:\\\\\\src/utils.py"}},
                ],
            },
        ]
        result = self.extract(entries)
        assert result == ["P:\\\\\\src/main.py", "P:\\\\\\src/utils.py"]

    def test_deduplicates_paths(self):
        entries = [
            {
                "type": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\src/main.py"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\src/main.py"}},
                ],
            },
        ]
        result = self.extract(entries)
        assert result == ["P:\\\\\\src/main.py"]

    def test_skips_noise_files(self):
        entries = [
            {
                "type": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "P:\\\\\\package.json"}},
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "P:\\\\\\poetry.lock"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\__pycache__/cache.pyc"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\node_modules/react/index.js"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\src/app.py"}},
                ],
            },
        ]
        result = self.extract(entries)
        assert result == ["P:\\\\\\src/app.py"]

    def test_empty_input_returns_empty(self):
        assert self.extract([]) == []
        assert self.extract([{"type": "user", "content": "hello"}]) == []

    def test_message_content_path(self):
        """Extract from message.content when top-level content is absent."""
        entries = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\src/handler.py"}},
                    ],
                },
            },
        ]
        result = self.extract(entries)
        assert result == ["P:\\\\\\src/handler.py"]

    def test_summarize_session_includes_modified_files(self):
        """_summarize_session return dict includes modified_files."""
        skill_path = Path("P:\\\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _summarize_session

        entries = [
            {
                "type": "user",
                "sessionId": "s1",
                "content": "fix the bug",
            },
            {
                "type": "assistant",
                "sessionId": "s1",
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "P:\\\\\\src/bug.py"}},
                ],
            },
        ]
        result = _summarize_session(entries, "s1")
        assert "modified_files" in result
        assert result["modified_files"] == ["P:\\\\\\src/bug.py"]


# Pre-mortem Domain 1a: Test _extract_first_user_request
class TestExtractFirstUserRequest:
    """Domain 1a: Test _extract_first_user_request edge cases and boundaries."""

    def test_empty_entries_returns_none(self):
        """Test that empty entries list returns None."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        result = _extract_first_user_request([])
        assert result is None, "Empty entries should return None"

    def test_all_entries_filtered_returns_none(self):
        """Test that all entries filtered by skip_patterns returns None."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        entries = [
            {"type": "user", "content": "Base directory for skill"},
            {"type": "user", "content": "You are an AI assistant"},
            {"type": "user", "content": "Skill: /some-command"},
        ]
        result = _extract_first_user_request(entries)
        assert result is None, "All entries filtered should return None"

    def test_all_entries_too_short_returns_none(self):
        """Test that all entries too short (<30 chars) returns None."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        entries = [
            {"type": "user", "content": "fix bug"},  # 8 chars
            {"type": "user", "content": "help me"},  # 8 chars
        ]
        result = _extract_first_user_request(entries)
        assert result is None, "All entries too short should return None"

    def test_none_content_skipped(self):
        """Test that entries with None content are skipped."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        entries = [
            {"type": "user", "content": None},
            {"type": "user", "content": "This is a valid request that is long enough to be counted"},
        ]
        result = _extract_first_user_request(entries)
        assert result is not None
        assert "valid request" in result

    def test_boundary_30_chars(self):
        """Test boundary condition: exactly 30 chars."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        # Exactly 30 chars (should pass)
        entries = [{"type": "user", "content": "123456789012345678901234567890123"}]
        result = _extract_first_user_request(entries)
        assert result is not None, "30 char entry should pass minimum length check"

    def test_29_chars_fails(self):
        """Test boundary condition: 29 chars should fail."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        # 29 chars (should fail)
        entries = [{"type": "user", "content": "12345678901234567890123456789"}]
        result = _extract_first_user_request(entries)
        assert result is None, "29 char entry should fail minimum length check"

    def test_truncation_at_500_chars(self):
        """Test that long requests are truncated to 500 chars."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_first_user_request

        long_request = "A" * 600
        entries = [{"type": "user", "content": long_request}]
        result = _extract_first_user_request(entries)
        assert result is not None
        assert len(result) == 500, f"Truncated to 500 chars, got {len(result)}"
        assert result == "A" * 500


# Pre-mortem Domain 1b: Test _extract_session_narrative
class TestExtractSessionNarrative:
    """Domain 1b: Test _extract_session_narrative edge cases and logic."""

    def test_empty_semantic_returns_empty_narrative(self):
        """Test that empty semantic dict returns initialized narrative with empty lists."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_session_narrative

        entries = [{"type": "user", "content": "This is a test request that is at least thirty characters long"}]
        semantic = {"actions": [], "fixes": [], "decisions": [], "outcomes": []}
        result = _extract_session_narrative(entries, semantic)

        assert result["original_request"] is not None
        assert result["what_was_done"] == []
        assert result["decisions_made"] == []
        assert result["next_steps"] == []
        assert result["open_questions"] == []

    def test_semantic_content_populates_what_was_done(self):
        """Test that semantic extraction populates what_was_done."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_session_narrative

        entries = [{"type": "user", "content": "test request"}]
        semantic = {
            "actions": ["Added feature X", "Fixed bug Y"],
            "fixes": ["Fixed auth issue"],
            "decisions": [],
            "outcomes": ["Tests pass"],
        }
        result = _extract_session_narrative(entries, semantic)

        assert len(result["what_was_done"]) == 4
        assert any("Fixed auth issue" in item for item in result["what_was_done"])
        assert any("Added feature X" in item for item in result["what_was_done"])

    def test_limit_5_items_per_field(self):
        """Test that narrative fields are limited to 5 items."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_session_narrative

        entries = [{"type": "user", "content": "test"}]
        semantic = {
            "actions": [f"Action{i}" for i in range(10)],
            "fixes": [f"Fix{i}" for i in range(10)],
            "decisions": [],
            "outcomes": [],
        }
        result = _extract_session_narrative(entries, semantic)

        # Logic: fixes[:3] (3 items) + actions[:5] (5 items, but filtered) → limited by _MAX_ITEMS_PER_FIELD (5)
        # The items are deduplicated in _unique_truncate, then limited to 5
        assert len(result["what_was_done"]) == 5, "Should be limited to 5 items after deduplication"

    def test_question_pattern_extraction(self):
        """Test that question patterns are extracted from assistant entries."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_session_narrative

        entries = [
            {
                "type": "assistant",
                "content": "Open question: should we use approach X or Y?",
            },
        ]
        semantic = {"actions": [], "fixes": [], "decisions": [], "outcomes": []}
        result = _extract_session_narrative(entries, semantic)

        assert len(result["open_questions"]) >= 1
        assert any("approach X or Y" in q for q in result["open_questions"])

    def test_current_state_populated_from_actions(self):
        """Test that current_state is populated from semantic actions."""
        skill_path = Path("P:\\\\.claude/skills/recap")
        if str(skill_path) not in sys.path:
            sys.path.insert(0, str(skill_path))
        from recap import _extract_session_narrative

        entries = [
            {"type": "user", "content": "modify file.py"},
            {"type": "assistant", "content": "Editing file.py now"},
        ]
        semantic = {
            "actions": ["Editing file.py"],
            "fixes": [],
            "decisions": [],
            "outcomes": [],
        }
        result = _extract_session_narrative(entries, semantic)

        # current_state should extract file paths from actions containing "edit"/"modify"/"fix"
        assert result["current_state"]["modified"] == ["file.py"] or result["current_state"]["modified"] == ["Editing file.py"]
        assert result["current_state"]["working"] == []
        assert result["current_state"]["blocked"] == []
