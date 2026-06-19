from __future__ import annotations

import json
import os
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
    # Suppress DOC-001 when CLAUDE.md is present at the project root: the
    # project's documented convention is CLAUDE.md (not README.md), and emitting
    # a false-positive README-missing finding for every run pollutes the artifact.
    # The orchestrator convention proof: every Claude Code project in this monorepo
    # uses CLAUDE.md as its canonical project doc (see /packages/CLAUDE.md).
    has_project_doc = (root / "CLAUDE.md").exists()
    if not readme.exists() and not has_project_doc:
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


def detect_marker_staleness(
    root: Path, terminal_id: str, session_id: str, git_sha: str | None
) -> list[Finding]:
    """Detect stale session markers persisting from previous runs.

    Checks:
    - carryover.json git_sha mismatches current git_sha
    - handoff JSON entries with mismatched terminal_id or session_id
    - identity.json session_id mismatches actual session
    """
    findings: list[Finding] = []
    artifacts_root = Path(os.environ.get("CLAUDE_ARTIFACTS_ROOT", root / ".claude/.artifacts"))
    term_dir = artifacts_root / terminal_id / "gto"

    # Check carryover.json for git_sha staleness
    carryover_path = term_dir / "carryover.json"
    if carryover_path.exists():
        try:
            with open(carryover_path, encoding="utf-8") as f:
                data = json.load(f)
            entries = data if isinstance(data, list) else data.get("findings", [])
            for entry in entries:
                stored_sha = entry.get("git_sha") or entry.get("metadata", {}).get("git_sha")
                if stored_sha and git_sha and stored_sha != git_sha:
                    finding_id = entry.get("id", "CARRYOVER-001")
                    findings.append(
                        Finding(
                            id=f"QUALITY-marker_staleness-{finding_id[:16]}",
                            title="Carryover finding has stale git_sha",
                            description=f"Carryover entry '{finding_id}' references git_sha '{stored_sha}' which differs from current run's '{git_sha}'. This indicates the finding was captured in a prior session and may not reflect current codebase state.",
                            source_type="detector",
                            source_name="marker_staleness_detector",
                            domain="quality",
                            gap_type="marker_staleness",
                            severity="medium",
                            evidence_level="verified",
                            action="recover",
                            priority="medium",
                            terminal_id=terminal_id,
                            session_id=session_id,
                            git_sha=git_sha,
                            evidence=[
                                EvidenceRef(kind="artifact", value=str(carryover_path), detail=f"entry_id={finding_id}, stored_sha={stored_sha}, current_sha={git_sha}"),
                            ],
                        )
                    )
        except (json.JSONDecodeError, OSError):
            pass

    # Check gap_reviewer_handoff.json for terminal_id / session_id mismatches
    handoff_path = term_dir / "gap_reviewer_handoff.json"
    if handoff_path.exists():
        try:
            with open(handoff_path, encoding="utf-8") as f:
                hdata = json.load(f)
            ctx = hdata.get("session_context", {})
            h_terminal_id = ctx.get("terminal_id")
            h_git_sha = ctx.get("git_sha")
            if h_terminal_id and h_terminal_id != terminal_id:
                findings.append(
                    Finding(
                        id="QUALITY-marker_staleness-handoff-terminal",
                        title="Gap reviewer handoff has mismatched terminal_id",
                        description=f"Handoff references terminal_id '{h_terminal_id}' but current terminal is '{terminal_id}'. This suggests the handoff was generated for a different terminal session.",
                        source_type="detector",
                        source_name="marker_staleness_detector",
                        domain="quality",
                        gap_type="marker_staleness",
                        severity="high",
                        evidence_level="verified",
                        action="recover",
                        priority="high",
                        terminal_id=terminal_id,
                        session_id=session_id,
                        git_sha=git_sha,
                        evidence=[
                            EvidenceRef(kind="artifact", value=str(handoff_path), detail=f"handoff_terminal={h_terminal_id}, current_terminal={terminal_id}"),
                        ],
                    )
                )
            if h_git_sha and git_sha and h_git_sha != git_sha:
                findings.append(
                    Finding(
                        id="QUALITY-marker_staleness-handoff-sha",
                        title="Gap reviewer handoff has stale git_sha",
                        description=f"Handoff references git_sha '{h_git_sha}' which differs from current run's '{git_sha}'. Detector evidence may be stale.",
                        source_type="detector",
                        source_name="marker_staleness_detector",
                        domain="quality",
                        gap_type="marker_staleness",
                        severity="medium",
                        evidence_level="verified",
                        action="recover",
                        priority="medium",
                        terminal_id=terminal_id,
                        session_id=session_id,
                        git_sha=git_sha,
                        evidence=[
                            EvidenceRef(kind="artifact", value=str(handoff_path), detail=f"handoff_sha={h_git_sha}, current_sha={git_sha}"),
                        ],
                    )
                )
        except (json.JSONDecodeError, OSError):
            pass

    return findings


def detect_missing_verification_evidence(
    root: Path, terminal_id: str, session_id: str, git_sha: str | None
) -> list[Finding]:
    """Detect when findings cite hooks/telemetry mechanisms without supporting evidence.

    Checks:
    - Findings citing hook paths → verify the hook script exists and has test coverage
    - Findings citing telemetry → verify telemetry event traces exist in session artifacts
    - Findings citing session state → verify the state file exists
    """
    findings: list[Finding] = []
    artifacts_root = Path(os.environ.get("CLAUDE_ARTIFACTS_ROOT", root / ".claude/.artifacts"))
    term_dir = artifacts_root / terminal_id / "gto"

    # Read current run's artifact to get finding evidence references
    artifact_path = term_dir / "outputs" / "artifact.json"
    if not artifact_path.exists():
        return findings

    try:
        with open(artifact_path, encoding="utf-8") as f:
            artifact = json.load(f)
    except (json.JSONDecodeError, OSError):
        return findings

    findings_data = artifact.get("findings", [])

    for f in findings_data:
        evidence_list = f.get("evidence", [])
        for ev in evidence_list:
            kind = ev.get("kind", "")
            value = ev.get("value", "")

            # Check hook path references for test coverage
            if kind == "path" and ("hook" in value.lower() or "stop" in value.lower() or "pretool" in value.lower()):
                hook_path = root / value if not Path(value).is_absolute() else Path(value)
                if hook_path.exists():
                    # Check for corresponding test file
                    test_variants = [
                        hook_path.parent / "tests" / f"test_{hook_path.name}",
                        hook_path.parent / f"test_{hook_path.name}",
                        hook_path.parent.parent / "tests" / f"test_{hook_path.stem}_py",
                    ]
                    has_test = any(t.exists() for t in test_variants)
                    if not has_test:
                        findings.append(
                            Finding(
                                id=f"QUALITY-unverified_implementation_claim-{f.get('id', 'FINDING')[:16]}",
                                title="Finding cites hook without test coverage",
                                description=f"Finding '{f.get('id')}' references hook '{value}' but no test file was found. The implementation claim (hook fires correctly, handles all cases) is unverified.",
                                source_type="detector",
                                source_name="missing_verification_detector",
                                domain="quality",
                                gap_type="unverified_implementation_claim",
                                severity="medium",
                                evidence_level="unverified",
                                action="recover",
                                priority="medium",
                                terminal_id=terminal_id,
                                session_id=session_id,
                                git_sha=git_sha,
                                evidence=[
                                    EvidenceRef(kind="path", value=value, detail="hook cited without test coverage"),
                                    EvidenceRef(kind="path", value=str(test_variants[0].parent / "tests"), detail="checked test locations, none found"),
                                ],
                            )
                        )

            # Check telemetry references
            if kind == "telemetry" or "telemetry" in value.lower():
                telemetry_marker = term_dir / "telemetry_events.jsonl"
                if not telemetry_marker.exists():
                    findings.append(
                        Finding(
                            id=f"QUALITY-unverified_implementation_claim-telemetry-{f.get('id', 'FINDING')[:16]}",
                            title="Finding cites telemetry without event traces",
                            description=f"Finding '{f.get('id')}' references telemetry mechanism but no telemetry event log was found in this session. The behavioral claim is unverified.",
                            source_type="detector",
                            source_name="missing_verification_detector",
                            domain="quality",
                            gap_type="unverified_implementation_claim",
                            severity="low",
                            evidence_level="unverified",
                            action="recover",
                            priority="low",
                            terminal_id=terminal_id,
                            session_id=session_id,
                            git_sha=git_sha,
                            evidence=[
                                EvidenceRef(kind="artifact", value=str(telemetry_marker), detail="telemetry event log not found"),
                            ],
                        )
                    )

    return findings


# Export all detectors for orchestrator use
DETECTOR_REGISTRY = {
    "basic_detectors": run_basic_detectors,
    "marker_staleness_detector": detect_marker_staleness,
    "missing_verification_detector": detect_missing_verification_evidence,
}
