"""Changelog detector — maps session-edited files to skill recommendations.

Uses transcript-extracted file lists (terminal-scoped) instead of git diffs.
Maps edited files to skills that may need re-running based on what changed.
"""
from __future__ import annotations

from ..models import EvidenceRef, Finding

# File pattern → skill recommendations for changed files.
# Each entry is (path_prefix, extension, skill, reason).
# A file matches if it starts with path_prefix and ends with extension.
FILE_SKILL_MAP: list[tuple[str, str, str, str]] = [
    ("skills/", "SKILL.md", "/sqa", "skill definition changed — quality check may find new issues"),
    ("skills/", ".py", "/sqa", "skill implementation changed — semantic layer may find defects"),
    (".claude/hooks/", ".py", "/sqa --layer=L7", "hook changed — operational verification needed"),
    ("tests/", ".py", "pytest", "test files changed — run test suite to verify"),
    ("", ".md", "/docs", "documentation changed — validate consistency"),
    ("", "pyproject.toml", "/deps", "dependency config changed — check for stale deps"),
    ("", "requirements", "/deps", "dependencies changed — check for CVEs and updates"),
]


def _matches_entry(path: str, prefix: str, extension: str) -> bool:
    """Check if path starts with prefix and ends with extension."""
    if prefix and not path.startswith(prefix):
        return False
    if extension and not path.endswith(extension):
        return False
    return True

# Domain for changelog findings
CHANGELOG_DOMAIN = "session"

# Staleness wave thresholds
WAVE_THRESHOLDS = (
    (10, "significant"),   # 10+ files changed
    (3, "moderate"),       # 3-9 files changed
    (0, "incremental"),    # 1-2 files changed
)


def classify_change_wave(file_count: int, commit_count: int) -> str:
    """Classify changelog volume for staleness wave reporting."""
    for threshold, label in WAVE_THRESHOLDS:
        if file_count >= threshold:
            return label
    return "incremental"


# Skill categories that can be anti-recommended (not needed)
# Maps a skill category to a descriptive label for anti-recommendations
SKILL_CATEGORIES: dict[str, str] = {
    "/sqa": "code quality checks",
    "pytest": "test suite",
    "/docs": "documentation validation",
    "/deps": "dependency auditing",
    "/sqa --layer=L7": "hook verification",
}


def _base_skill(skill: str) -> str:
    """Normalize skill variants to base skill for category comparison."""
    if skill.startswith("/sqa"):
        return "/sqa"
    return skill



def map_changed_files_to_skills(
    changed_files: list[str],
) -> dict[str, list[tuple[str, str]]]:
    """Map changed files to affected skills.

    Returns: {skill: [(file_path, reason), ...]}
    """
    skill_files: dict[str, list[tuple[str, str]]] = {}
    for fp in changed_files:
        for prefix, extension, skill, reason in FILE_SKILL_MAP:
            if _matches_entry(str(fp), prefix, extension):
                skill_files.setdefault(skill, []).append((fp, reason))
    return skill_files


def _matches_pattern(path: str, pattern: str) -> bool:
    """Match path against a glob pattern supporting ** (any depth)."""
    from pathlib import PurePosixPath
    return PurePosixPath(path).match(pattern)


def detect_changelog_findings(
    edited_files: list[str],
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Map session-edited files to skill recommendations.

    Uses transcript-extracted file lists instead of git diffs.
    Returns findings recommending skill re-runs for affected files.
    """
    if not edited_files:
        return []

    unique_files = sorted(set(edited_files))
    skill_map = map_changed_files_to_skills(unique_files)
    wave = classify_change_wave(len(unique_files), 0)

    findings: list[Finding] = []

    for idx, (skill, file_reasons) in enumerate(sorted(skill_map.items()), start=1):
        files = list({f for f, _ in file_reasons})
        reasons = list({r for _, r in file_reasons})
        description = (
            f"{len(files)} file(s) edited this session affect {skill}: "
            f"{', '.join(reasons[:3])}"
        )

        base_severity = "medium"
        base_priority = "medium"
        if wave == "significant":
            base_severity = "high"
            base_priority = "high"

        findings.append(
            Finding(
                id=f"CHANGELOG-{idx:03d}",
                title=f"Edits affect {skill} — consider re-running",
                description=description,
                source_type="detector",
                source_name="changelog_detector",
                domain=CHANGELOG_DOMAIN,
                gap_type="stale_skill",
                severity=base_severity,
                evidence_level="verified",
                action="realize",
                priority=base_priority,
                owner_skill=skill,
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(
                        kind="transcript_edits",
                        value=f"{len(unique_files)} files",
                        detail=f"{len(files)} relevant to {skill}, wave={wave}",
                    ),
                ],
            )
        )

    # Unmatched files
    unmatched = [
        fp for fp in unique_files
        if not any(_matches_entry(str(fp), prefix, ext) for prefix, ext, _, _ in FILE_SKILL_MAP)
    ]
    if unmatched and len(unmatched) <= 10:
        findings.append(
            Finding(
                id="CHANGELOG-UNMATCHED-001",
                title=f"{len(unmatched)} edited files not covered by skill patterns",
                description=f"Files not mapping to known skill patterns: {', '.join(str(fp) for fp in unmatched[:10])}",
                source_type="detector",
                source_name="changelog_detector",
                domain=CHANGELOG_DOMAIN,
                gap_type="untracked_changes",
                severity="low",
                evidence_level="verified",
                action="realize",
                priority="low",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(kind="transcript_edits", value=f"{len(unmatched)} unmatched files", detail=""),
                ],
            )
        )

    # Anti-recommendations
    triggered_skills = {_base_skill(s) for s in skill_map}
    all_skills = {_base_skill(s) for _, _, s, _ in FILE_SKILL_MAP}
    untriggered = all_skills - triggered_skills

    if untriggered and wave in ("incremental", "moderate"):
        skipped = sorted(untriggered)
        skipped_labels = [SKILL_CATEGORIES.get(s, s) for s in skipped]
        findings.append(
            Finding(
                id="CHANGELOG-ANTI-001",
                title=f"Change wave '{wave}' — {len(skipped)} skill categories not needed",
                description=(
                    f"Session edits only affect {sorted(triggered_skills)}. "
                    f"Unlikely to find new issues: {', '.join(skipped_labels)}"
                ),
                source_type="detector",
                source_name="changelog_detector",
                domain=CHANGELOG_DOMAIN,
                gap_type="no_action_needed",
                severity="low",
                evidence_level="verified",
                action="skip",
                priority="low",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(
                        kind="anti_recommendation",
                        value=", ".join(skipped),
                        detail=f"wave={wave}, {len(unique_files)} files, {len(skipped)} skills unaffected",
                    ),
                ],
            )
        )

    return findings
