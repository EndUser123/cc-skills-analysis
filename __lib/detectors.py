from __future__ import annotations

from pathlib import Path

from ..models import EvidenceRef, Finding


def run_basic_detectors(
    root: Path, terminal_id: str, session_id: str, git_sha: str | None
) -> list[Finding]:
    findings: list[Finding] = []

    if not (root / ".git").exists():
        findings.append(
            Finding(
                id="GIT-001",
                title="Repository metadata missing",
                description="Target directory does not contain a .git directory.",
                source_type="detector",
                source_name="basic_detectors",
                domain="git",
                gap_type="invalidrepo",
                severity="high",
                evidence_level="verified",
                scope="systemic",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[EvidenceRef(kind="path", value=str(root / ".git"))],
            )
        )

    readme = root / "README.md"
    if not readme.exists():
        findings.append(
            Finding(
                id="DOC-001",
                title="README missing",
                description="Project root does not contain a README.md.",
                source_type="detector",
                source_name="basic_detectors",
                domain="docs",
                gap_type="missingdocs",
                severity="medium",
                evidence_level="verified",
                scope="local",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[EvidenceRef(kind="path", value=str(readme))],
            )
        )

    return findings
