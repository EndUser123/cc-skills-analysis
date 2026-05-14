from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
import json

from .util import atomic_write_json


@dataclass
class RunState:
    skill: str = "gto"
    run_id: str = ""
    phase: str = "initialized"
    verification_required: bool = False
    verification_status: str = "pending"
    current_target: str | None = None
    git_sha: str | None = None
    last_artifact: str | None = None
    expected_artifacts: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "run_id": self.run_id,
            "phase": self.phase,
            "verification_required": self.verification_required,
            "verification_status": self.verification_status,
            "current_target": self.current_target,
            "git_sha": self.git_sha,
            "last_artifact": self.last_artifact,
            "expected_artifacts": self.expected_artifacts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


def load_state(path: Path) -> RunState:
    if not path.exists():
        return RunState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RunState(
            skill=data.get("skill", "gto"),
            run_id=data.get("run_id", ""),
            phase=data.get("phase", "initialized"),
            verification_required=data.get("verification_required", False),
            verification_status=data.get("verification_status", "pending"),
            current_target=data.get("current_target"),
            git_sha=data.get("git_sha"),
            last_artifact=data.get("last_artifact"),
            expected_artifacts=data.get("expected_artifacts", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
    except (json.JSONDecodeError, KeyError):
        return RunState()


def save_state(path: Path, state: RunState) -> None:
    state.touch()
    atomic_write_json(path, state.to_dict())
