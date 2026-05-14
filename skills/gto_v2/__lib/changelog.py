"""Changelog detector — reads git log since previous GTO run.

Compares current git_sha against the previous run's git_sha to identify
changed files, then emits findings for skills that may need re-running
based on those changes.
"""
from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

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


def get_changed_files(root: Path, prev_sha: str, curr_sha: str) -> list[str]:
    """Return list of files changed between two git SHAs, relative to root."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "diff", "--name-only", f"{prev_sha}..{curr_sha}"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in out.strip().splitlines() if line.strip()]


def get_commit_count(root: Path, prev_sha: str, curr_sha: str) -> int:
    """Return number of commits between two SHAs."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "rev-list", "--count", f"{prev_sha}..{curr_sha}"],
            text=True,
        )
        return int(out.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0


def map_changed_files_to_skills(
    changed_files: list[str],
) -> dict[str, list[tuple[str, str]]]:
    """Map changed files to affected skills.

    Returns: {skill: [(file_path, reason), ...]}
    """
    skill_files: dict[str, list[tuple[str, str]]] = {}
    for fp in changed_files:
        for prefix, extension, skill, reason in FILE_SKILL_MAP:
            if _matches_entry(fp, prefix, extension):
                skill_files.setdefault(skill, []).append((fp, reason))
    return skill_files


def _matches_pattern(path: str, pattern: str) -> bool:
    """Match path against a glob pattern supporting ** (any depth)."""
    from pathlib import PurePosixPath
    return PurePosixPath(path).match(pattern)


def detect_changelog_findings(
    root: Path,
    prev_sha: str | None,
    curr_sha: str | None,
    terminal_id: str,
    session_id: str,
    git_sha: str | None,
) -> list[Finding]:
    """Detect findings from git changelog since previous GTO run.

    Returns findings recommending skill re-runs for changed files.
    Returns empty list if no previous SHA available or no changes detected.
    """
    if not prev_sha or not curr_sha or prev_sha == curr_sha:
        return []

    # Verify both SHAs exist in the repo
    for sha in (prev_sha, curr_sha):
        try:
            subprocess.check_output(
                ["git", "-C", str(root), "cat-file", "-t", sha],
                text=True,
            )
        except subprocess.CalledProcessError:
            return []

    changed = get_changed_files(root, prev_sha, curr_sha)
    if not changed:
        return []

    commit_count = get_commit_count(root, prev_sha, curr_sha)
    skill_map = map_changed_files_to_skills(changed)
    wave = classify_change_wave(len(changed), commit_count)

    findings: list[Finding] = []

    # One finding per affected skill
    for idx, (skill, file_reasons) in enumerate(
        sorted(skill_map.items()), start=1
    ):
        files = list({f for f, _ in file_reasons})
        reasons = list({r for _, r in file_reasons})
        description = (
            f"{commit_count} commits with {len(files)} files changed since last GTO run "
            f"affect {skill}: {', '.join(reasons[:3])}"
        )

        # Staleness wave: significant changes elevate severity
        base_severity = "medium"
        base_priority = "medium"
        if wave == "significant":
            base_severity = "high"
            base_priority = "high"

        findings.append(
            Finding(
                id=f"CHANGELOG-{idx:03d}",
                title=f"Changes affect {skill} — consider re-running",
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
                        kind="git_diff",
                        value=f"{prev_sha[:12]}..{curr_sha[:12]}",
                        detail=f"{commit_count} commits, {len(changed)} files, {len(files)} relevant, wave={wave}",
                    ),
                ],
            )
        )

    # If there are changed files that don't match any skill pattern,
    # emit a generic finding
    unmatched = []
    for fp in changed:
        if not any(_matches_entry(fp, prefix, ext) for prefix, ext, _, _ in FILE_SKILL_MAP):
            unmatched.append(fp)

    if unmatched and len(unmatched) <= 10:
        findings.append(
            Finding(
                id="CHANGELOG-UNMATCHED-001",
                title=f"{len(unmatched)} changed files not covered by skill patterns",
                description=(
                    f"Files changed since last run that don't map to known skill patterns: "
                    f"{', '.join(unmatched[:10])}"
                ),
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
                    EvidenceRef(
                        kind="git_diff",
                        value=f"{prev_sha[:12]}..{curr_sha[:12]}",
                        detail=f"{len(unmatched)} unmatched files",
                    ),
                ],
            )
        )

    # Anti-recommendations: skills NOT affected by the changes.
    # Only emit when the change set is narrow enough to be confident.
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
                    f"Changes since last run only affect {sorted(triggered_skills)}. "
                    f"The following are unlikely to find new issues: {', '.join(skipped_labels)}"
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
                        detail=f"wave={wave}, {len(changed)} files, {len(skipped)} skills unaffected",
                    ),
                ],
            )
        )

    return findings
