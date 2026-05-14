"""recap v2 — canonical domain models.

All dataclass definitions live here so they can be imported across modules
without creating circular dependencies. Conversion to dict/JSON happens only
at the renderer boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol

# ── Enumerations ────────────────────────────────────────────────────────────────


class ClaimType(Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    GAP = "GAP"


class ClaimStatus(Enum):
    CURRENT = "current"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


class WorkstreamStatus(Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    DONE = "done"
    UNCERTAIN = "uncertain"


class RiskSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskKind(Enum):
    VERIFICATION_GAP = "verification_gap"
    STALE_STATE = "stale_state"
    CONTRACT_GAP = "contract_gap"
    AMBIGUITY = "ambiguity"
    MISSING_EVIDENCE = "missing_evidence"


class EventKind(Enum):
    USER_INTENT_SET = "user_intent_set"
    ASSISTANT_PLAN_PROPOSED = "assistant_plan_proposed"
    TOOL_INVOKED = "tool_invoked"
    FILE_MODIFIED = "file_modified"
    DECISION_MADE = "decision_made"
    VERIFICATION_RUN = "verification_run"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    BLOCKER_DISCOVERED = "blocker_discovered"
    HANDOVER_WRITTEN = "handoff_written"
    HANDOVER_LOADED = "handoff_loaded"
    STATE_OBSERVED = "state_observed"
    CONTRADICTION_OBSERVED = "contradiction_observed"


class VerificationPriority(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DecisionStatus(Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    UNCERTAIN = "uncertain"


class EvidenceSourceType(Enum):
    TRANSCRIPT = "transcript"
    HANDOFF = "handoff"
    REGISTRY = "registry"
    SESSIONS_INDEX = "sessions_index"
    CODE_FILE = "code_file"


# ── Evidence anchors ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    """Provenance pointer for any derived object."""
    source_type: Literal[
        "transcript", "handoff", "registry", "sessions_index", "code_file"
    ]
    source_path: str
    locator: str
    excerpt: str | None = None


# ── Raw evidence records ────────────────────────────────────────────────────────


@dataclass(slots=True)
class TranscriptRecord:
    """Raw transcript file as evidence."""
    path: Path
    terminal_id: str | None
    project_root: Path | None
    loaded_at: datetime
    anchors: list[EvidenceAnchor] = field(default_factory=list)


@dataclass(slots=True)
class HandoffRecord:
    """Raw handoff file as evidence."""
    path: Path
    session_id: str | None
    terminal_id: str | None
    created_at: datetime | None
    payload: dict
    anchors: list[EvidenceAnchor] = field(default_factory=list)


# ── Sessions ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SessionSpan:
    """A single session as a span within a transcript."""
    session_id: str
    transcript_path: Path | None
    terminal_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    entry_count: int = 0
    user_message_count: int = 0
    assistant_message_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    last_goal_hint: str | None = None
    modified_files: list[str] = field(default_factory=list)
    anchors: list[EvidenceAnchor] = field(default_factory=list)


# ── Events ─────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Event:
    """Typed event derived from transcript entry analysis."""
    event_id: str
    session_id: str
    timestamp: datetime | None
    type: EventKind
    title: str
    detail: str
    file_paths: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    confidence: float = 1.0
    anchors: list[EvidenceAnchor] = field(default_factory=list)


# ── Claims ──────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Claim:
    """Typed claim: grounded (FACT), synthesized (INFERENCE), or uncertain (GAP)."""
    claim_id: str
    statement: str
    type: ClaimType
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    confidence: float = 0.5
    session_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    workstream_ids: list[str] = field(default_factory=list)
    anchors: list[EvidenceAnchor] = field(default_factory=list)
    supersedes_claim_id: str | None = None
    contradicted_by_claim_id: str | None = None
    verification_hint: str | None = None


# ── Decisions ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Decision:
    """A continuity-critical decision with rationale and revisit conditions."""
    decision_id: str
    statement: str
    rationale: str | None = None
    impact: Literal["low", "medium", "high"] = "medium"
    status: DecisionStatus = DecisionStatus.ACTIVE
    session_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    anchors: list[EvidenceAnchor] = field(default_factory=list)
    revisit_if: list[str] = field(default_factory=list)


# ── Risks ─────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Risk:
    """An explicit risk record."""
    risk_id: str
    title: str
    severity: RiskSeverity
    kind: RiskKind
    description: str = ""
    claim_ids: list[str] = field(default_factory=list)
    workstream_ids: list[str] = field(default_factory=list)
    mitigation: str | None = None
    blocking: bool = False


# ── Verification items ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class VerificationItem:
    """An executable verification backlog item."""
    verification_id: str
    priority: VerificationPriority = VerificationPriority.MEDIUM
    target_type: Literal["function", "file", "workflow", "contract", "state"] = "function"
    target: str = ""
    why: str = ""
    claim_ids: list[str] = field(default_factory=list)
    success_signal: str | None = None
    failure_signal: str | None = None
    suggested_method: str | None = None
    anchors: list[EvidenceAnchor] = field(default_factory=list)


# ── Workstreams ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Workstream:
    """A cross-session work thread, clustered by file/symbol/temporal continuity."""
    workstream_id: str
    title: str
    status: WorkstreamStatus = WorkstreamStatus.ACTIVE
    summary: str = ""
    session_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    decision_ids: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    next_action: str | None = None
    blocker_risk_ids: list[str] = field(default_factory=list)


# ── Resume packet ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ResumePacket:
    """The primary handoff artifact — first thing another LLM reads."""
    current_goal: str | None = None
    current_subgoal: str | None = None
    current_status: Literal["active", "blocked", "paused", "done", "unclear"] = "unclear"
    last_confirmed_good_state: str | None = None
    exact_next_action: str | None = None
    active_files: list[str] = field(default_factory=list)
    pending_decision_ids: list[str] = field(default_factory=list)
    blocking_risk_ids: list[str] = field(default_factory=list)
    top_workstream_ids: list[str] = field(default_factory=list)
    verification_status: Literal["unverified", "partially_verified", "verified"] = "unverified"
    resume_notes: list[str] = field(default_factory=list)


# ── Code structure provider ───────────────────────────────────────────────────


@dataclass(slots=True)
class CodeStructureSummary:
    """Output from a code structure provider for a single file."""
    path: str
    language: str | None = None
    symbols: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    summary: str | None = None
    anchors: list[EvidenceAnchor] = field(default_factory=list)


class StructureProvider(Protocol):
    """Pluggable code structure provider interface."""

    def summarize_file(self, path: Path) -> CodeStructureSummary | None:
        """Summarize a single file. Returns None if unavailable."""
        ...

    def summarize_project(self, root: Path) -> list[CodeStructureSummary]:
        """Summarize all relevant files under a project root."""
        ...


@dataclass(slots=True)
class NullStructureProvider:
    """No-op structure provider — always returns None / empty list."""

    def summarize_file(self, path: Path) -> CodeStructureSummary | None:
        return None

    def summarize_project(self, root: Path) -> list[CodeStructureSummary]:
        return []


# ── Canonical graph ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class RecapGraph:
    """The single canonical object every renderer consumes."""
    schema_version: str = "2.0.0"
    generated_at: datetime = field(default_factory=datetime.utcnow)
    project_root: Path | None = None
    terminal_id: str | None = None
    current_session_id: str | None = None
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)
    sessions: list[SessionSpan] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    verification_queue: list[VerificationItem] = field(default_factory=list)
    workstreams: list[Workstream] = field(default_factory=list)
    resume_packet: ResumePacket = field(default_factory=ResumePacket)

    def _next_id(self, prefix: str) -> str:
        """Generate a unique ID for a new entity (lives on graph to avoid global state)."""
        import itertools
        if not hasattr(self, "_id_counter"):
            object.__setattr__(self, "_id_counter", 0)
        counter = self._id_counter + 1
        object.__setattr__(self, "_id_counter", counter)
        return f"{prefix}-{counter}"
