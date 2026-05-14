from __future__ import annotations


def resolve_target(
    explicit_target: str | None,
    conversation_hint: str | None,
    artifact_target: str | None,
) -> str:
    for candidate in (explicit_target, conversation_hint, artifact_target):
        if candidate and candidate.strip():
            return candidate.strip()
    return "current-project"
