from __future__ import annotations

import json
from pathlib import Path

from ..models import GTOArtifact, Finding
from .machine_render import render_machine_format
from .render import render_findings
from .util import atomic_write_json


def write_artifact(
    artifact_path: Path,
    artifact: GTOArtifact,
    findings: list[Finding],
) -> Path:
    """Write the GTO artifact JSON file with machine and human output.

    Returns the path written.
    """
    machine_lines = render_machine_format(findings).splitlines()
    human_output = render_findings(findings)

    artifact.findings = findings
    artifact.machine_output = machine_lines
    artifact.human_output = human_output

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(artifact_path, _artifact_to_dict(artifact))
    return artifact_path


def _artifact_to_dict(artifact: GTOArtifact) -> dict:
    return {
        "artifact_version": artifact.artifact_version,
        "mode": artifact.mode,
        "created_at": artifact.created_at,
        "terminal_id": artifact.terminal_id,
        "session_id": artifact.session_id,
        "target": artifact.target,
        "git_sha": artifact.git_sha,
        "health_score": artifact.health_score,
        "freshness": artifact.freshness,
        "findings": [f.to_dict() for f in artifact.findings],
        "summary": artifact.summary,
        "machine_output": artifact.machine_output,
        "human_output": artifact.human_output,
        "verification": artifact.verification,
        "coverage": artifact.coverage,
        "metadata": artifact.metadata,
    }
