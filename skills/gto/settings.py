from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class GTOPaths:
    root: Path
    artifacts_dir: Path
    state_dir: Path
    inputs_dir: Path
    outputs_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class GTOSettings:
    terminal_id: str
    session_id: str
    git_sha: str | None
    root: Path
    mode: str = "full"

    @property
    def paths(self) -> GTOPaths:
        override = os.environ.get("CLAUDE_ARTIFACTS_ROOT", "").strip()
        if override:
            artifacts_base = Path(override)
        else:
            artifacts_base = Path(self.root.anchor) / ".claude" / ".artifacts"
        base = artifacts_base / self.terminal_id / "gto"
        return GTOPaths(
            root=self.root,
            artifacts_dir=base,
            state_dir=base / "state",
            inputs_dir=base / "inputs",
            outputs_dir=base / "outputs",
            logs_dir=base / "logs",
        )
