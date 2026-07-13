from __future__ import annotations


def classify_freshness(
    *,
    artifact_git_sha: str | None,
    current_git_sha: str | None,
    artifact_target: str | None,
    current_target: str | None,
) -> str:
    # If either target is missing, we can't determine freshness reliably
    if artifact_target is None or current_target is None:
        return "unknown"
    if artifact_target != current_target:
        return "stale-target"
    # Targets match — check git SHA
    if artifact_git_sha is not None and current_git_sha is not None:
        if artifact_git_sha != current_git_sha:
            return "stale-git"
        return "fresh"
    # Targets match but git SHA unavailable
    return "unknown"
