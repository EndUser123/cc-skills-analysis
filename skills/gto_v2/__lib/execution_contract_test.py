"""Tests for gto_v2 execution-contract integration.

Mechanical tests for:
- RNS marker verification in artifacts
- path isolation (gto_v2 vs gto)
- sync_to_execution_state output shape
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from skills.gto_v2.__lib.state import RunState, sync_to_execution_state
from skills.gto_v2.__lib.verify import verify_artifact


def test_verify_artifact_with_rns_markers_valid():
    """Artifact with both RNS|D| and RNS|Z| markers passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "artifact.json"
        path.write_text(json.dumps({
            "artifact_version": "1.0.0",
            "mode": "full",
            "terminal_id": "test",
            "session_id": "test",
            "target": "test",
            "findings": [{"id": "TEST-001"}],
            "machine_output": [
                "RNS|D|test",
                "TEST-001 [low] some finding",
                "RNS|Z|",
            ],
            "human_output": "",
            "verification": {},
            "coverage": {},
        }), encoding="utf-8")

        result = verify_artifact(path)
        assert result["valid"] is True
        assert result["errors"] == []


def test_verify_artifact_missing_rns_d_marker_fails():
    """Artifact missing RNS|D| marker fails if it has findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "artifact.json"
        path.write_text(json.dumps({
            "artifact_version": "1.0.0",
            "mode": "full",
            "terminal_id": "test",
            "session_id": "test",
            "target": "test",
            "findings": [{"id": "TEST-001"}],
            "machine_output": [
                "some line",
                "RNS|Z|",
            ],
            "human_output": "",
            "verification": {},
            "coverage": {},
        }), encoding="utf-8")

        result = verify_artifact(path)
        assert result["valid"] is False
        assert any("RNS|D|" in e for e in result["errors"])


def test_verify_artifact_missing_rns_z_marker_fails():
    """Artifact missing RNS|Z| marker fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "artifact.json"
        path.write_text(json.dumps({
            "artifact_version": "1.0.0",
            "mode": "full",
            "terminal_id": "test",
            "session_id": "test",
            "target": "test",
            "findings": [{"id": "TEST-001"}],
            "machine_output": [
                "RNS|D|test",
                "TEST-001 [low] some finding",
            ],
            "human_output": "",
            "verification": {},
            "coverage": {},
        }), encoding="utf-8")

        result = verify_artifact(path)
        assert result["valid"] is False
        assert any("RNS|Z|" in e for e in result["errors"])


def test_verify_artifact_invalid_json_fails():
    """Artifact with invalid JSON fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "artifact.json"
        path.write_text("not valid json {{{", encoding="utf-8")

        result = verify_artifact(path)
        assert result["valid"] is False
        assert any("Cannot parse" in e for e in result["errors"])


def test_verify_artifact_missing_file_fails():
    """Artifact file that does not exist fails."""
    path = Path("/tmp/does_not_exist_12345.json")

    result = verify_artifact(path)
    assert result["valid"] is False
    assert any("not found" in e for e in result["errors"])


def test_sync_to_execution_state_writes_correct_shape():
    """sync_to_execution_state produces the expected execution-state.json structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "console_test" / "gto_v2"
        base.mkdir(parents=True)
        (base / "outputs").mkdir()

        state = RunState(
            skill="gto_v2",
            run_id="test-run-001",
            phase="completed",
            current_target="P:\\\\\\test",
            git_sha="abc123",
            last_artifact=str(base / "outputs" / "artifact.json"),
            expected_artifacts=[],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )

        sync_to_execution_state(state, base)

        exec_path = base.parent / "execution-state.json"
        assert exec_path.exists(), "execution-state.json not written"

        data = json.loads(exec_path.read_text(encoding="utf-8"))

        assert data["run_id"] == "test-run-001"
        assert data["skill_name"] == "gto_v2"
        assert data["contract_type"] == "workflow-execution"
        assert data["phase"] == "completed"
        assert data["status"] == "complete"
        assert str(base / "outputs" / "artifact.json") in data["required_artifacts"]
        assert data["completed_artifacts"] == [str(base / "outputs" / "artifact.json")]
        assert data["missing_requirements"] == []
        assert "Bash" in data["allowed_tools_now"]
        assert "Read" in data["allowed_tools_now"]


def test_sync_to_execution_state_active_phase():
    """sync_to_execution_state sets status=active when phase is not completed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "console_test" / "gto_v2"
        base.mkdir(parents=True)

        state = RunState(
            skill="gto_v2",
            run_id="test-run-002",
            phase="running",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:30Z",
        )

        sync_to_execution_state(state, base)

        exec_path = base.parent / "execution-state.json"
        data = json.loads(exec_path.read_text(encoding="utf-8"))

        assert data["phase"] == "running"
        assert data["status"] == "active"


def test_run_state_skill_default_is_gto_v2():
    """RunState defaults skill to gto_v2."""
    state = RunState()
    assert state.skill == "gto_v2"
