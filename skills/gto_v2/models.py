from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal

EvidenceLevel = Literal["verified", "unverified", "derived"]
FindingStatus = Literal["open", "mapped", "rejected", "deferred", "resolved", "stale"]
FindingScope = Literal["local", "systemic", "architectural"]
FindingSourceType = Literal["detector", "agent", "hook", "artifact", "carryover", "user"]


@dataclass
class EvidenceRef:
    kind: str
    value: str
    detail: str | None = None


@dataclass
class Finding:
    id: str
    title: str
    description: str
    source_type: FindingSourceType
    source_name: str
    domain: str
    gap_type: str
    severity: str
    evidence_level: EvidenceLevel
    action: str = "recover"
    priority: str = "medium"
    status: FindingStatus = "open"
    scope: FindingScope = "local"
    owner_skill: str | None = None
    owner_reason: str | None = None
    file: str | None = None
    line: int | None = None
    symbol: str | None = None
    reversibility: float | None = None
    effort: str | None = None
    target: str | None = None
    depends_on: list[str] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    terminal_id: str | None = None
    session_id: str | None = None
    git_sha: str | None = None
    freshness: str | None = None
    unverified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResult:
    agent: str
    findings: list[Finding]
    raw_notes: str = ""
    success: bool = True


@dataclass
class GTOArtifact:
    artifact_version: str
    mode: str
    created_at: str
    terminal_id: str
    session_id: str
    target: str
    git_sha: str | None
    health_score: int | None
    freshness: str
    findings: list[Finding]
    summary: dict[str, Any]
    machine_output: list[str]
    human_output: str
    verification: dict[str, Any]
    coverage: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(
        cls,
        mode: str,
        terminal_id: str,
        session_id: str,
        target: str,
        git_sha: str | None,
    ) -> GTOArtifact:
        return cls(
            artifact_version="1.0.0",
            mode=mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=terminal_id,
            session_id=session_id,
            target=target,
            git_sha=git_sha,
            health_score=None,
            freshness="unknown",
            findings=[],
            summary={},
            machine_output=[],
            human_output="",
            verification={},
            coverage={},
            metadata={},
        )
