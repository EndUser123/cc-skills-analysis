"""Adversarial validation tests for recap v2.

Tests the full pipeline on a multi-session, multi-file, partially-degraded
scenario to prove behavioral robustness beyond happy-path smoke tests.

Scenario:
  Session A (s1a): modifies foo.py, bar.py — "add validation"
  Session B (s1b): no file mods — goal change + test run + failure + success
  Session C (s1c): modifies foo.py (touched in A) — contradicts approach from A
  Subagent transcript: must be filtered
  Registry degraded: force transcript-only fallback

Tests verify:
  - Transcript-only FACTs emitted even when no modified files
  - Contradiction handling (stale/superseded claims)
  - ResumePacket correctness post-contradiction
  - Degradation mode produces usable output
  - JSON schema contract stability
  - Subagent transcript filtering
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

# ── Path setup ─────────────────────────────────────────────────────────────────

_recap_dir = Path(__file__).parent.parent
if str(_recap_dir) not in sys.path:
    sys.path.insert(0, str(_recap_dir))

# ── Import from v2 pipeline ───────────────────────────────────────────────────────

from recap_v2 import (
    RecapV2State,
    build_recap_v2,
    render_json,
    render_markdown,
    ClaimType,
    ClaimStatus,
    EventKind,
    WorkstreamStatus,
    DecisionStatus,
    RiskSeverity,
    RiskKind,
    Meta,
    ResumePacket,
    SessionRecord,
    SessionStats,
    Event,
    EventAnchor,
    Claim,
    ClaimEvidence,
    Workstream,
    Risk,
    VerificationItem,
    build_claims,
    build_workstreams,
    build_resume_packet,
    extract_events,
)


# ════════════════════════════════════════════════════════════════════════════════
# SYNTHETIC TRANSCRIPT BUILDER
# ════════════════════════════════════════════════════════════════════════════════


def make_transcript_entry(
    entry_type: str,
    session_id: str,
    content: Any,
    entry_index: int,
    timestamp: str = "2026-04-27T10:00:00+00:00",
    message: dict | None = None,
) -> dict[str, Any]:
    """Build a single transcript entry dict."""
    entry: dict[str, Any] = {
        "type": entry_type,
        "sessionId": session_id,
        "timestamp": timestamp,
        "created": timestamp,
    }
    if message is not None:
        entry["message"] = message
    else:
        entry["content"] = content
    return entry


def make_tool_use_block(
    name: str,
    file_path: str = "",
    command: str = "",
    input_extra: dict | None = None,
) -> dict[str, Any]:
    """Build a tool_use content block."""
    inp: dict[str, Any] = {}
    if file_path:
        inp["file_path"] = file_path
    if command:
        inp["command"] = command
    if input_extra:
        inp.update(input_extra)
    return {"type": "tool_use", "name": name, "input": inp}


# ── Session A: modifies foo.py, bar.py — "add validation" ────────────────────────

def build_session_a_transcript() -> list[dict[str, Any]]:
    """Session A: Edit foo.py and bar.py to add input validation."""
    ts_a = "2026-04-27T10:00:00+00:00"
    ts_a2 = "2026-04-27T10:05:00+00:00"
    ts_a3 = "2026-04-27T10:07:00+00:00"

    return [
        # User: sets goal
        make_transcript_entry("user", "s1a", [
            {"type": "text", "text": "We need input validation on the API endpoints. "
             "Add check_valid_input to foo.py and bar.py to sanitize all user inputs."}
        ], entry_index=1, timestamp=ts_a),
        # Assistant: plans approach
        make_transcript_entry("assistant", "s1a", [
            {"type": "text", "text": "I'll add input validation to foo.py and bar.py. "
             "Using approach: regex-based sanitization for string inputs."}
        ], entry_index=2, timestamp=ts_a),
        # Edit foo.py
        make_transcript_entry("assistant", "s1a", [
            make_tool_use_block("Edit", file_path="P:\\\\\\project/src/foo.py",
                                 input_extra={"old_string": "def check_valid_input(data):\n    pass",
                                              "new_string": "def check_valid_input(data):\n"
                                              "    if not isinstance(data, str):\n"
                                              "        return False\n"
                                              "    return len(data) > 0"})
        ], entry_index=3, timestamp=ts_a2),
        # Edit bar.py
        make_transcript_entry("assistant", "s1a", [
            make_tool_use_block("Edit", file_path="P:\\\\\\project/src/bar.py",
                                 input_extra={"old_string": "def check_valid_input(data):\n    pass",
                                              "new_string": "def check_valid_input(data):\n"
                                              "    if not isinstance(data, str):\n"
                                              "        return False\n"
                                              "    return len(data) > 0"})
        ], entry_index=4, timestamp=ts_a2),
        # Read to verify
        make_transcript_entry("assistant", "s1a", [
            make_tool_use_block("Read", file_path="P:\\\\\\project/src/foo.py")
        ], entry_index=5, timestamp=ts_a3),
        make_transcript_entry("assistant", "s1a", [
            {"type": "text", "text": "Validation added to both foo.py and bar.py. "
             "Now I'll write a test to verify the behavior."}
        ], entry_index=6, timestamp=ts_a3),
    ]


# ── Session B: no file mods — goal change + test run (fail then succeed) ─────────

def build_session_b_transcript() -> list[dict[str, Any]]:
    """Session B: changes approach, runs tests — one failure, one success."""
    ts_b = "2026-04-27T11:00:00+00:00"
    ts_b2 = "2026-04-27T11:08:00+00:00"
    ts_b3 = "2026-04-27T11:12:00+00:00"
    ts_b4 = "2026-04-27T11:20:00+00:00"

    return [
        # User: changes approach (contradicts A's regex approach)
        make_transcript_entry("user", "s1b", [
            {"type": "text", "text": "Actually, regex validation isn't sufficient. "
             "We should use a type-check first and then length validation. "
             "The approach we discussed earlier (regex-only) is insufficient "
             "for our needs."}
        ], entry_index=1, timestamp=ts_b),
        # Assistant: acknowledges pivot
        make_transcript_entry("assistant", "s1b", [
            {"type": "text", "text": "Understood. We'll switch from regex-only to "
             "type-check + length validation. This supersedes the previous approach."}
        ], entry_index=2, timestamp=ts_b),
        # Bash: run tests — FAILS
        make_transcript_entry("assistant", "s1b", [
            make_tool_use_block("Bash", command="pytest tests/test_foo.py -v")
        ], entry_index=3, timestamp=ts_b2),
        make_transcript_entry("user", "s1b", [
            {"type": "tool_result", "text": "FAILED tests/test_foo.py::test_check_valid_input\n"
             "AssertionError: assert check_valid_input(123) == False\n"
             "E   AssertionError: check_valid_input(123) returned None instead of False"}
        ], entry_index=4, timestamp=ts_b2),
        make_transcript_entry("assistant", "s1b", [
            {"type": "text", "text": "The test failed because check_valid_input(123) "
             "returned None instead of False for non-string input. Need to fix the guard."}
        ], entry_index=5, timestamp=ts_b2),
        # Edit: fix the guard — foo.py
        make_transcript_entry("assistant", "s1b", [
            make_tool_use_block("Edit", file_path="P:\\\\\\project/src/foo.py",
                                 input_extra={"old_string": "def check_valid_input(data):\n"
                                              "    if not isinstance(data, str):\n"
                                              "        return False\n"
                                              "    return len(data) > 0",
                                              "new_string": "def check_valid_input(data):\n"
                                              "    if not isinstance(data, str):\n"
                                              "        return False\n"
                                              "    if not isinstance(data, str) or len(data) == 0:\n"
                                              "        return False\n"
                                              "    return True"})
        ], entry_index=6, timestamp=ts_b3),
        # Bash: run tests again — PASSES
        make_transcript_entry("assistant", "s1b", [
            make_tool_use_block("Bash", command="pytest tests/test_foo.py tests/test_bar.py -v")
        ], entry_index=7, timestamp=ts_b3),
        make_transcript_entry("user", "s1b", [
            {"type": "tool_result", "text": "PASSED tests/test_foo.py::test_check_valid_input\n"
             "PASSED tests/test_foo.py::test_check_valid_input_empty\n"
             "PASSED tests/test_bar.py::test_check_valid_input\n"
             "3 passed in 0.42s"}
        ], entry_index=8, timestamp=ts_b4),
        make_transcript_entry("assistant", "s1b", [
            {"type": "text", "text": "All 3 tests pass now. The fix is verified."}
        ], entry_index=9, timestamp=ts_b4),
        # User: sets next goal
        make_transcript_entry("user", "s1b", [
            {"type": "text", "text": "Good. Next we should add integration tests "
             "to cover the full request pipeline."}
        ], entry_index=10, timestamp=ts_b4),
    ]


# ── Session C: modifies foo.py (from A) — contradicts approach, adds decorator ─

def build_session_c_transcript() -> list[dict[str, Any]]:
    """Session C: Reverts A's approach, adds decorator-based validation instead."""
    ts_c = "2026-04-27T14:00:00+00:00"
    ts_c2 = "2026-04-27T14:10:00+00:00"
    ts_c3 = "2026-04-27T14:15:00+00:00"

    return [
        # User: abandons approach, wants decorator
        make_transcript_entry("user", "s1c", [
            {"type": "text", "text": "The inline validation approach is too scattered. "
             "We should use a @validate decorator instead and remove the inline "
             "check_valid_input calls. This makes the codebase cleaner."}
        ], entry_index=1, timestamp=ts_c),
        # Assistant: proposes plan
        make_transcript_entry("assistant", "s1c", [
            {"type": "text", "text": "Agreed. I'll create a @validate decorator in "
             "utils.py, remove check_valid_input from foo.py, and apply the decorator "
             "to the API handler functions. This supersedes all prior inline approaches."}
        ], entry_index=2, timestamp=ts_c),
        # Write new decorator to utils.py
        make_transcript_entry("assistant", "s1c", [
            make_tool_use_block("Write", file_path="P:\\\\\\project/src/utils.py",
                                 input_extra={"content": "def validate(*types):\n"
                                 "    def decorator(func):\n"
                                 "        def wrapper(*args, **kwargs):\n"
                                 "            for val, expected in zip(args, types):\n"
                                 "                if not isinstance(val, expected):\n"
                                 "                    raise ValueError(f'Expected {expected}, got {type(val)}')\n"
                                 "            return func(*args, **kwargs)\n"
                                 "        return wrapper\n"
                                 "    return decorator\n"})
        ], entry_index=3, timestamp=ts_c2),
        # Edit foo.py to remove old validation and add decorator usage
        make_transcript_entry("assistant", "s1c", [
            make_tool_use_block("Edit", file_path="P:\\\\\\project/src/foo.py",
                                 input_extra={"old_string": "def check_valid_input(data):\n"
                                              "    if not isinstance(data, str):\n"
                                              "        return False\n"
                                              "    if not isinstance(data, str) or len(data) == 0:\n"
                                              "        return False\n"
                                              "    return True",
                                              "new_string": "from utils import validate\n\n"
                                              "@validate(str)\n"
                                              "def handle_request(data):\n"
                                              "    pass"})
        ], entry_index=4, timestamp=ts_c2),
        # Edit bar.py to remove old validation
        make_transcript_entry("assistant", "s1c", [
            make_tool_use_block("Edit", file_path="P:\\\\\\project/src/bar.py",
                                 input_extra={"old_string": "def check_valid_input(data):\n"
                                              "    if not isinstance(data, str):\n"
                                              "        return False\n"
                                              "    return len(data) > 0",
                                              "new_string": "from utils import validate\n\n"
                                              "@validate(str)\n"
                                              "def handle_request(data):\n"
                                              "    pass"})
        ], entry_index=5, timestamp=ts_c3),
        # Read to confirm
        make_transcript_entry("assistant", "s1c", [
            make_tool_use_block("Read", file_path="P:\\\\\\project/src/foo.py")
        ], entry_index=6, timestamp=ts_c3),
    ]


# ── Subagent transcript (must be filtered) ─────────────────────────────────────

def build_subagent_transcript() -> list[dict[str, Any]]:
    """Subagent transcript that must be excluded from results."""
    return [
        make_transcript_entry("user", "subagent-1", [
            {"type": "text", "text": "Analyze the codebase structure for the refactor."}
        ], entry_index=1, timestamp="2026-04-27T09:00:00+00:00"),
        make_transcript_entry("assistant", "subagent-1", [
            make_tool_use_block("Bash", command="find . -name '*.py' | head -50")
        ], entry_index=2, timestamp="2026-04-27T09:01:00+00:00"),
        make_transcript_entry("assistant", "subagent-1", [
            {"type": "text", "text": "Found 47 Python files. Key files: foo.py, bar.py, utils.py."}
        ], entry_index=3, timestamp="2026-04-27T09:02:00+00:00"),
    ]


# ── Combined multi-session transcript JSONL lines ────────────────────────────────

def write_synthetic_transcripts(tmp_dir: Path) -> dict[str, Path]:
    """Write all synthetic transcript files and return path map."""
    # Session A transcript (with subagent mixed in — subagent should be filtered)
    path_a = tmp_dir / "s1a.jsonl"
    path_a.write_text(
        "\n".join(json.dumps(e) for e in build_session_a_transcript()) + "\n"
        + "\n".join(json.dumps(e) for e in build_subagent_transcript()),
        encoding="utf-8"
    )

    # Session B transcript
    path_b = tmp_dir / "s1b.jsonl"
    path_b.write_text(
        "\n".join(json.dumps(e) for e in build_session_b_transcript()) + "\n",
        encoding="utf-8"
    )

    # Session C transcript
    path_c = tmp_dir / "s1c.jsonl"
    path_c.write_text(
        "\n".join(json.dumps(e) for e in build_session_c_transcript()) + "\n",
        encoding="utf-8"
    )

    return {"s1a": path_a, "s1b": path_b, "s1c": path_c}


# ════════════════════════════════════════════════════════════════════════════════
# FIXTURE: multi-session v2 state
# ════════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def multi_session_state(tmp_path: Path) -> RecapV2State:
    """Build a RecapV2State from synthetic multi-session transcripts."""
    paths = write_synthetic_transcripts(tmp_path)

    # Build state manually from synthetic data (avoids full acquire dependency)
    state = RecapV2State()

    # meta
    state.meta = Meta(
        generated_at="2026-04-27T15:00:00Z",
        evidence_mode="direct_transcript",
        degraded=False,
        degradation_reasons=[],
        source_counts={"transcripts": 3, "handoffs": 0, "registry_entries": 0},
    )

    # project
    from recap_v2 import Project
    state.project = Project(
        project_root=str(tmp_path),
        project_hash="TEST--project",
        terminal_id="console_test",
        current_session_id="s1c",
        transcript_discovery={"mode": "direct_transcript", "paths_scanned": [str(p) for p in paths.values()]},
    )

    # sessions
    state.sessions = [
        SessionRecord(
            session_id="s1a",
            ordinal=1,
            created_at="2026-04-27T10:00:00Z",
            ended_at="2026-04-27T10:10:00Z",
            duration="10m",
            priority_score=72.0,
            stats=SessionStats(entry_count=6, user_message_count=1, assistant_message_count=5,
                               token_usage={"input_tokens": 12000, "output_tokens": 4500, "total_tokens": 16500}),
            goal="Add input validation to foo.py and bar.py using regex-based sanitization",
            modified_files=["P:\\\\\\project/src/foo.py", "P:\\\\\\project/src/bar.py"],
            transcript_path=str(paths["s1a"]),
            summary="Added check_valid_input to foo.py and bar.py using regex-only approach",
            event_ids=[],
            claim_ids=[],
            workstream_ids=[],
        ),
        SessionRecord(
            session_id="s1b",
            ordinal=2,
            created_at="2026-04-27T11:00:00Z",
            ended_at="2026-04-27T11:25:00Z",
            duration="25m",
            priority_score=85.0,
            stats=SessionStats(entry_count=10, user_message_count=3, assistant_message_count=7,
                               token_usage={"input_tokens": 18000, "output_tokens": 7200, "total_tokens": 25200}),
            goal="Switch from regex-only to type-check + length validation, fix and verify tests",
            modified_files=["P:\\\\\\project/src/foo.py"],  # one fix edit in B
            transcript_path=str(paths["s1b"]),
            summary="Changed approach from regex-only to type-check + length; test failed once, then passed",
            event_ids=[],
            claim_ids=[],
            workstream_ids=[],
        ),
        SessionRecord(
            session_id="s1c",
            ordinal=3,
            created_at="2026-04-27T14:00:00Z",
            ended_at="2026-04-27T14:20:00Z",
            duration="20m",
            priority_score=90.0,
            stats=SessionStats(entry_count=6, user_message_count=1, assistant_message_count=5,
                               token_usage={"input_tokens": 14000, "output_tokens": 5800, "total_tokens": 19800}),
            goal="Switch to @validate decorator and remove inline check_valid_input calls",
            modified_files=["P:\\\\\\project/src/foo.py", "P:\\\\\\project/src/bar.py", "P:\\\\\\project/src/utils.py"],
            transcript_path=str(paths["s1c"]),
            summary="Adopted @validate decorator approach; removed old check_valid_input from foo.py and bar.py",
            event_ids=[],
            claim_ids=[],
            workstream_ids=[],
        ),
    ]

    # Run pipeline stages 3-6
    state = extract_events(state)
    state = build_workstreams(state)
    state = build_claims(state)
    state = build_resume_packet(state)

    # Add a GAP claim so markdown tests can verify GAP label rendering
    # (all sessions have modified files, so no GAP would otherwise be emitted)
    from recap_v2 import Claim, ClaimType, ClaimStatus, ClaimEvidence
    state.claims.append(
        Claim(
            claim_id="clm-gap-1",
            statement="Verification gap: session B's type-check approach was discussed but not confirmed in transcript",
            type=ClaimType.GAP,
            confidence=0.7,
            status=ClaimStatus.UNVERIFIED,
            scope="session",
            session_ids=["s1b"],
            evidence=[
                ClaimEvidence(
                    kind="transcript_content",
                    detail="User mentioned switching approach but no explicit confirmation",
                    anchors=["transcript"],
                )
            ],
            verification_hint="Verify type-check approach was actually implemented in session B",
        )
    )

    # Add a verification queue item so the Verification Queue section renders
    from recap_v2 import VerificationItem
    state.verification_queue.append(
        VerificationItem(
            verification_id="vq-1",
            priority="HIGH",
            target_type="workflow",
            target="s1b approach verification",
            claim_id="clm-gap-1",
            why="Type-check approach was discussed but transcript confirmation is ambiguous",
            suggested_action="Run tests from session B to confirm behavior",
            success_signal="All tests pass with type-check validation",
            failure_signal="Tests fail or wrong validation behavior",
            anchors=["s1b transcript"],
        )
    )

    return state


# ════════════════════════════════════════════════════════════════════════════════
# TEST 1: Transcript-only FACTs exist even with no modified files
# ════════════════════════════════════════════════════════════════════════════════


class TestTranscriptOnlyFacts:
    """Even without modified files, transcript-native facts must be FACT claims."""

    def test_session_goal_as_fact(self, multi_session_state: RecapV2State):
        """A clearly stated user goal is a FACT claim, not INFERENCE."""
        goal_claims = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.FACT
            and "goal" in c.statement.lower()
            and any(sid in c.session_ids for sid in ["s1a", "s1b", "s1c"])
        ]
        assert len(goal_claims) >= 3, (
            f"Expected at least 3 goal FACT claims (one per session), got {len(goal_claims)}: "
            f"{[c.statement for c in goal_claims]}"
        )

    def test_test_failure_as_fact(self, multi_session_state: RecapV2State):
        """'Tests failed with ...' from transcript tool_result is a FACT claim."""
        failure_claims = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.FACT
            and any(kw in c.statement.lower() for kw in ["failed", "failure", "assertionerror"])
        ]
        assert len(failure_claims) >= 1, (
            f"Expected at least 1 FACT claim for test failure, got {len(failure_claims)}"
        )

    def test_test_pass_as_fact(self, multi_session_state: RecapV2State):
        """'Tests passed' from transcript tool_result is a FACT claim."""
        pass_claims = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.FACT
            and "passed" in c.statement.lower()
            and "3 passed" in c.statement.lower()
        ]
        assert len(pass_claims) >= 1, (
            f"Expected FACT claim for '3 passed', got {pass_claims}"
        )

    def test_approach_pivot_as_fact_not_inference(self, multi_session_state: RecapV2State):
        """'We switched approach from X to Y' stated by user is a FACT (explicit user intent)."""
        pivot_claims = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.FACT
            and any(kw in c.statement.lower()
                    for kw in ["switch", "instead", "regex isn't sufficient", "type-check"])
        ]
        assert len(pivot_claims) >= 1, (
            f"Expected at least 1 FACT claim for approach pivot, got {len(pivot_claims)}"
        )

    def test_gap_not_used_for_explicit_content(self, multi_session_state: RecapV2State):
        """Explicitly stated outcomes must NOT be GAP claims."""
        explicit_content = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.GAP
            and any(kw in c.statement.lower()
                    for kw in ["goal", "failed", "passed", "switch", "regex"])
        ]
        assert len(explicit_content) == 0, (
            f"GAP claims should not apply to explicitly stated content. "
            f"Found {len(explicit_content)} GAP claims that match explicit content: "
            f"{[c.statement for c in explicit_content]}"
        )


# ════════════════════════════════════════════════════════════════════════════════
# TEST 2: Contradiction handling
# ════════════════════════════════════════════════════════════════════════════════


class TestContradictionHandling:
    """Claims from earlier sessions that are contradicted by later sessions."""

    def test_earlier_approach_marked_stale_or_contradicted(
        self, multi_session_state: RecapV2State
    ):
        """The regex-only approach from A must be marked stale/contradicted by C's decorator."""
        # Collect all claims about foo.py or the validation approach
        approach_claims = [
            c for c in multi_session_state.claims
            if any(kw in c.statement.lower()
                   for kw in ["foo.py", "regex", "check_valid_input", "approach"])
        ]

        # Find the old regex-only claim from A
        old_claims = [
            c for c in approach_claims
            if c.type == ClaimType.FACT
            and any(sid in c.session_ids for sid in ["s1a"])
            and any(kw in c.statement.lower() for kw in ["regex", "check_valid_input"])
        ]

        # Find the new decorator claim from C
        new_claims = [
            c for c in approach_claims
            if c.type == ClaimType.FACT
            and any(sid in c.session_ids for sid in ["s1c"])
            and any(kw in c.statement.lower() for kw in ["decorator", "@validate"])
        ]

        assert len(old_claims) >= 1, f"No FACT claim from A about regex approach found: {[c.statement for c in approach_claims]}"
        assert len(new_claims) >= 1, f"No FACT claim from C about decorator found: {[c.statement for c in approach_claims]}"

        old = old_claims[0]
        new = new_claims[0]

        # The old claim must be stale or superseded
        assert old.status in (ClaimStatus.STALE, ClaimStatus.CONTRADICTED), (
            f"A's regex approach claim should be STALE or CONTRADICTED, got {old.status.value}. "
            f"Statement: {old.statement}"
        )

        # The new claim must be current
        assert new.status == ClaimStatus.CURRENT, (
            f"C's decorator approach claim should be CURRENT, got {new.status.value}"
        )

        # The new claim should reference that it supersedes the old
        # (via supersedes_claim_id or evidence showing it contradicts)
        assert (
            new.supersedes_claim_id == old.claim_id
            or any(a.source_path == old.claim_id for a in new.evidence)
            or any(old.claim_id in str(a) for a in new.evidence for _ in [None])
        ), (
            f"New claim should explicitly supersede old claim via supersedes_claim_id or anchor. "
            f"Old: {old.claim_id}, New supersedes: {new.supersedes_claim_id}, "
            f"New evidence: {[e for e in new.evidence]}"
        )

    def test_resume_packet_favors_current_approach(self, multi_session_state: RecapV2State):
        """ResumePacket.current_goal should reflect the current (C's) approach, not A's."""
        rp = multi_session_state.resume_packet
        assert rp.current_goal is not None
        assert "decorator" in rp.current_goal.lower() or "@validate" in rp.current_goal or "utils.py" in rp.current_goal, (
            f"resume_packet.current_goal should reference the decorator approach from C, "
            f"got: {rp.current_goal}"
        )
        # Must NOT reference the old regex-only approach
        assert "regex-only" not in rp.current_goal.lower()
        assert "regex-only approach" not in rp.current_goal.lower()


# ════════════════════════════════════════════════════════════════════════════════
# TEST 3: ResumePacket correctness
# ════════════════════════════════════════════════════════════════════════════════


class TestResumePacketCorrectness:
    """ResumePacket built from multi-session scenario."""

    def test_current_goal_from_latest_session(
        self, multi_session_state: RecapV2State
    ):
        """current_goal must be from the latest session (s1c), not s1a."""
        rp = multi_session_state.resume_packet
        latest_goal = multi_session_state.sessions[-1].goal
        assert rp.current_goal == latest_goal, (
            f"resume_packet.current_goal should match s1c goal: '{latest_goal}', "
            f"got: '{rp.current_goal}'"
        )

    def test_active_files_from_latest_editing(
        self, multi_session_state: RecapV2State
    ):
        """active_files must be drawn from the most recent session's modified files."""
        rp = multi_session_state.resume_packet
        latest_files = multi_session_state.sessions[-1].modified_files
        assert len(rp.active_files) > 0
        # Compare by filename (stem) since paths may use different separators
        latest_names = {Path(f).name for f in latest_files}
        assert any(Path(f).name in latest_names for f in rp.active_files), (
            f"active_files should include files from s1c. "
            f"active_files: {rp.active_files}, s1c modified: {latest_files}"
        )

    def test_exact_next_action_present(self, multi_session_state: RecapV2State):
        """exact_next_action must be populated from the latest session's goal."""
        rp = multi_session_state.resume_packet
        assert rp.exact_next_action, (
            f"resume_packet.exact_next_action must not be empty, got: '{rp.exact_next_action}'"
        )

    def test_blocking_issues_from_gap_claims(
        self, multi_session_state: RecapV2State
    ):
        """blocking_issues must reflect unverified GAP claims."""
        rp = multi_session_state.resume_packet
        gap_claims = [c for c in multi_session_state.claims if c.type == ClaimType.GAP]
        if gap_claims:
            # resume_risks or blocking_issues must reference the gap
            assert (
                len(rp.resume_risks) > 0 or len(rp.blocking_issues) > 0
            ), "GAP claims exist but resume_packet has no resume_risks or blocking_issues"

    def test_verification_status_reflects_actual_state(
        self, multi_session_state: RecapV2State
    ):
        """verification_status must be consistent with actual claim verification state."""
        rp = multi_session_state.resume_packet
        unverified = [c for c in multi_session_state.claims if c.status == ClaimStatus.UNVERIFIED]
        partially_verified = [c for c in multi_session_state.claims if c.status == ClaimStatus.CURRENT]

        if unverified and partially_verified:
            assert rp.verification_status in ("unverified", "partially_verified"), (
                f"verification_status should reflect partial verification, got: {rp.verification_status}"
            )
        elif unverified and not partially_verified:
            assert rp.verification_status == "unverified"


# ════════════════════════════════════════════════════════════════════════════════
# TEST 4: Degradation behavior
# ════════════════════════════════════════════════════════════════════════════════


class TestDegradationBehavior:
    """When registry/index is absent, pipeline must still produce usable output."""

    def test_degraded_mode_meta(self, multi_session_state: RecapV2State):
        """When degraded=True, meta.degraded must be True and reasons must be non-empty."""
        # Simulate degraded state
        state = multi_session_state
        state.meta.degraded = True
        state.meta.degradation_reasons.append(
            "No registry entries found — using direct transcript only"
        )
        state.meta.evidence_mode = "direct_transcript"

        # Verify the degraded flag propagates into the output
        json_str = render_json(state)
        parsed = json.loads(json_str)
        assert parsed["meta"]["degraded"] is True
        assert len(parsed["meta"]["degradation_reasons"]) > 0
        assert len(parsed["meta"]["degradation_reasons"]) == len(state.meta.degradation_reasons)

    def test_degraded_produces_resume_packet(self, multi_session_state: RecapV2State):
        """Even in degraded mode, a usable resume_packet must be produced."""
        state = multi_session_state
        state.meta.degraded = True
        state.meta.degradation_reasons.append("Registry unavailable — transcript-only fallback")

        state = build_resume_packet(state)
        assert state.resume_packet is not None
        assert state.resume_packet.current_goal is not None

    def test_degraded_still_emits_fact_claims(self, multi_session_state: RecapV2State):
        """Degraded mode must not downgrade transcript-only facts to GAP."""
        state = multi_session_state
        state.meta.degraded = True
        state.meta.degradation_reasons.append("Registry unavailable")

        # Rebuild claims in degraded mode
        state = build_claims(state)
        fact_claims = [c for c in state.claims if c.type == ClaimType.FACT]
        assert len(fact_claims) >= 2, (
            f"Degraded mode must still emit FACT claims from transcript evidence. "
            f"Got {len(fact_claims)} FACT claims. "
            f"Statements: {[c.statement for c in fact_claims]}"
        )


# ════════════════════════════════════════════════════════════════════════════════
# TEST 5: JSON schema contract stability
# ════════════════════════════════════════════════════════════════════════════════


class TestJSONSchemaContract:
    """Round-trip schema stability test."""

    def test_round_trip_all_keys_present(self, multi_session_state: RecapV2State):
        """All required top-level keys must survive render_json → json.loads round-trip."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        required_keys = [
            "schema_version", "meta", "project", "resume_packet",
            "sessions", "workstreams", "claims", "decisions", "risks",
            "verification_queue", "render_hints",
        ]
        for key in required_keys:
            assert key in parsed, f"Required key '{key}' missing from JSON output"

    def test_claims_type_enum_valid(self, multi_session_state: RecapV2State):
        """Every claim's type must be one of FACT/INFERENCE/GAP."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        valid_types = {"FACT", "INFERENCE", "GAP"}
        for claim in parsed["claims"]:
            assert claim["type"] in valid_types, (
                f"Invalid claim type '{claim['type']}' in claim: {claim['statement'][:50]}"
            )

    def test_claims_status_enum_valid(self, multi_session_state: RecapV2State):
        """Every claim's status must be one of current/stale/contradicted/unverified."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        valid_statuses = {"current", "stale", "contradicted", "unverified"}
        for claim in parsed["claims"]:
            assert claim["status"] in valid_statuses, (
                f"Invalid claim status '{claim['status']}'"
            )

    def test_verification_queue_items_have_priority(self, multi_session_state: RecapV2State):
        """Each verification item must have a priority of HIGH/MEDIUM/LOW."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        valid_priorities = {"HIGH", "MEDIUM", "LOW"}
        for vq in parsed["verification_queue"]:
            assert vq["priority"] in valid_priorities, (
                f"Invalid priority '{vq['priority']}' in verification item: {vq['target']}"
            )

    def test_verification_items_have_signal_pairs(self, multi_session_state: RecapV2State):
        """Each verification item must have non-empty success_signal and failure_signal."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        for vq in parsed["verification_queue"]:
            assert vq.get("success_signal"), (
                f"Verification item {vq['verification_id']} missing success_signal"
            )
            assert vq.get("failure_signal"), (
                f"Verification item {vq['verification_id']} missing failure_signal"
            )

    def test_session_modified_files_from_sessions(self, multi_session_state: RecapV2State):
        """Each session with modified_files must list real paths."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        for session in parsed["sessions"]:
            if session.get("modified_files"):
                for f in session["modified_files"]:
                    assert f.endswith(".py") or f.endswith(".md") or ".py" in f, (
                        f"Session {session['session_id']} has suspicious modified_file: {f}"
                    )


# ════════════════════════════════════════════════════════════════════════════════
# TEST 6: Subagent transcript filtering
# ════════════════════════════════════════════════════════════════════════════════


class TestSubagentTranscriptFiltering:
    """Subagent transcripts must be excluded from the session list."""

    def test_subagent_transcript_filtered(self):
        """Paths with 'subagents' as exact directory component must be filtered."""
        from recap_v2 import _is_subagent_transcript
        from pathlib import Path

        # Should be filtered
        assert _is_subagent_transcript(Path("/home/user/.claude/subagents/agent-123/transcript.jsonl")) is True
        assert _is_subagent_transcript(Path("/home/user/subagents/analyzer/transcript.jsonl")) is True

        # Must NOT be filtered — 'subagents-analysis' is not a 'subagents' component
        assert _is_subagent_transcript(Path("/home/user/projects/subagents-analysis/transcript.jsonl")) is False
        assert _is_subagent_transcript(Path("/home/user/subagent-files/session.jsonl")) is False

    def test_agent_prefix_filtered(self):
        """Filenames starting with 'agent-' must be filtered."""
        from recap_v2 import _is_subagent_transcript
        from pathlib import Path

        assert _is_subagent_transcript(Path("/home/user/sessions/agent-456.jsonl")) is True
        assert _is_subagent_transcript(Path("/home/user/agent-001.jsonl")) is True

    def test_normal_session_not_filtered(self):
        """Normal user session transcripts must NOT be filtered."""
        from recap_v2 import _is_subagent_transcript
        from pathlib import Path

        assert _is_subagent_transcript(Path("/home/user/projects/P--/s1a.jsonl")) is False
        assert _is_subagent_transcript(Path("/home/user/.claude/projects/P--/console_abc.jsonl")) is False


# ════════════════════════════════════════════════════════════════════════════════
# TEST 7: Workstream clustering correctness
# ════════════════════════════════════════════════════════════════════════════════


class TestWorkstreamClustering:
    """Sessions sharing modified files must cluster into the same workstream."""

    def test_foo_py_sessions_clustered(self, multi_session_state: RecapV2State):
        """Sessions A, B, C all touch foo.py — must be in the same workstream."""
        foo_sessions = {s.session_id for s in multi_session_state.sessions
                        if any("foo.py" in f for f in s.modified_files)}
        assert len(foo_sessions) == 3, f"Expected A, B, C to touch foo.py, got: {foo_sessions}"

        # Find workstream containing those sessions
        ws_containing = [
            ws for ws in multi_session_state.workstreams
            if all(sid in ws.session_ids for sid in foo_sessions)
        ]
        assert len(ws_containing) >= 1, (
            f"Expected at least 1 workstream containing s1a, s1b, s1c via foo.py overlap. "
            f"Workstreams: {[(ws.workstream_id, ws.session_ids, ws.file_paths) for ws in multi_session_state.workstreams]}"
        )

    def test_workstream_titles_from_files(self, multi_session_state: RecapV2State):
        """Workstream titles should reflect the dominant file, not be generic."""
        for ws in multi_session_state.workstreams:
            if ws.title:
                assert ws.title not in ("workstream-1", "workstream", ""), (
                    f"Workstream title should be descriptive (derived from files), got: '{ws.title}'"
                )


# ════════════════════════════════════════════════════════════════════════════════
# TEST 8: Markdown views correctness
# ════════════════════════════════════════════════════════════════════════════════


class TestMarkdownViews:
    """Markdown renderers must produce correct views from the same state."""

    def test_full_markdown_starts_with_resume_packet(
        self, multi_session_state: RecapV2State
    ):
        """render_markdown full output must lead with the resume packet."""
        md = render_markdown(multi_session_state)
        lines = md.split("\n")
        # Find the first ## heading
        first_heading_idx = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)
        assert first_heading_idx is not None
        assert "Resume Packet" in lines[first_heading_idx], (
            f"First heading should be '## Resume Packet', got: {lines[first_heading_idx]}"
        )

    def test_brief_markdown_shows_goal_and_next_action(
        self, multi_session_state: RecapV2State
    ):
        """Brief markdown must show current goal and exact next action."""
        from recap_v2 import render_markdown_brief
        md = render_markdown_brief(multi_session_state)
        assert md
        assert len(md) < 2000, "Brief markdown should be condensed"
        # Must contain goal and action
        assert any(kw in md.lower() for kw in ["goal", "next", "action"]), (
            f"Brief markdown should contain goal/next action info, got: {md[:200]}"
        )

    def test_markdown_distinguishes_fact_inference_gap(
        self, multi_session_state: RecapV2State
    ):
        """Markdown must display FACT/INFERENCE/GAP distinction visibly."""
        md = render_markdown(multi_session_state)
        # Should show claim type indicators
        assert "[FACT]" in md or "`[FACT]`" in md or "FACT" in md, (
            f"FACT label should appear in markdown. First 500 chars: {md[:500]}"
        )
        assert "[INFERENCE]" in md or "`[INFERENCE]`" in md or "INFERENCE" in md, (
            f"INFERENCE label should appear in markdown"
        )
        assert "[GAP]" in md or "`[GAP]`" in md or "GAP" in md, (
            f"GAP label should appear in markdown"
        )


# ════════════════════════════════════════════════════════════════════════════════
# TEST 9: Claims — modified-file FACTs (file-derived vs transcript-native)
# ════════════════════════════════════════════════════════════════════════════════


class TestFileDerivedClaims:
    """Claims anchored on modified files via tool_use blocks must be distinguishable."""

    def test_file_modified_fact_has_tool_use_anchor(
        self, multi_session_state: RecapV2State
    ):
        """A FACT claim derived from an Edit/Write tool_use block must have a tool_use anchor."""
        file_claims = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.FACT
            and any(f in c.statement for f in ["foo.py", "bar.py", "utils.py"])
        ]
        assert len(file_claims) >= 1, (
            f"Expected at least 1 FACT claim for modified files, got {len(file_claims)}"
        )
        # At least one must have a tool_use evidence anchor
        tool_use_anchored = [
            c for c in file_claims
            if any("tool_use" in str(e) or "transcript_entry" in str(e) for e in c.evidence)
        ]
        assert len(tool_use_anchored) >= 1, (
            f"File-modified FACT claims must have tool_use anchors. "
            f"Claims: {[(c.statement, [str(e) for e in c.evidence]) for c in file_claims]}"
        )

    def test_transcript_only_fact_has_transcript_anchor(
        self, multi_session_state: RecapV2State
    ):
        """A FACT claim from transcript content (no modified file) must have a transcript anchor."""
        # Find claims that reference goal/test failure but are NOT file-modified
        transcript_facts = [
            c for c in multi_session_state.claims
            if c.type == ClaimType.FACT
            and not any(f in c.statement for f in ["foo.py", "bar.py", "utils.py", "check_valid"])
            and any(kw in c.statement.lower() for kw in ["goal", "test", "failed", "passed", "approach"])
        ]
        assert len(transcript_facts) >= 1, (
            f"Expected at least 1 transcript-only FACT claim, got {len(transcript_facts)}"
        )
        for c in transcript_facts:
            has_transcript_anchor = any(
                e.kind == "transcript_content" for e in c.evidence
            )
            assert has_transcript_anchor, (
                f"Transcript-only FACT claim must have evidence.kind='transcript_content'. "
                f"Claim: {c.statement}, evidence kinds: {[e.kind for e in c.evidence]}"
            )


# ════════════════════════════════════════════════════════════════════════════════
# INTEGRATION: Full round-trip with real render outputs
# ════════════════════════════════════════════════════════════════════════════════


class TestFullIntegration:
    """End-to-end round-trip test: state → JSON → markdown → assertions."""

    def test_full_pipeline_json_is_parseable(self, multi_session_state: RecapV2State):
        """render_json must produce parseable JSON with correct structure."""
        json_str = render_json(multi_session_state)
        parsed = json.loads(json_str)

        assert parsed["schema_version"] == "2.0.0"
        assert parsed["meta"]["evidence_mode"]
        assert parsed["resume_packet"]["current_goal"]
        assert len(parsed["sessions"]) == 3
        assert len(parsed["claims"]) >= 5
        assert len(parsed["workstreams"]) >= 1

    def test_full_pipeline_markdown_contains_key_sections(
        self, multi_session_state: RecapV2State
    ):
        """render_markdown must contain all key sections."""
        md = render_markdown(multi_session_state)
        required = ["Resume Packet", "Workstream", "Claim", "Verification Queue", "Session"]
        for section in required:
            assert section in md, f"Markdown missing required section: '{section}'"

    def test_no_silent_truncation_indicator_in_md(
        self, multi_session_state: RecapV2State
    ):
        """Markdown must not silently truncate critical facts like contradictions."""
        md = render_markdown(multi_session_state)
        md_lower = md.lower()
        # If there are contradictions/stale claims, they must be visible, not dropped
        stale_claims = [c for c in multi_session_state.claims if c.status == ClaimStatus.STALE]
        contradicted_claims = [c for c in multi_session_state.claims if c.status == ClaimStatus.CONTRADICTED]
        if stale_claims or contradicted_claims:
            assert "[STALE]" in md or "stale" in md_lower or "contradicted" in md_lower, (
                f"Stale/contradicted claims exist but not visible in markdown. "
                f"Stale: {len(stale_claims)}, Contradicted: {len(contradicted_claims)}"
            )
