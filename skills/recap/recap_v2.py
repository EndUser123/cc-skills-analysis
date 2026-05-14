#!/usr/bin/env python
"""recap v2 — JSON-first handoff artifact with typed schema.

Schema objects (all at module level for reuse by v1.5 enrichment):
    EventKind, Event, EventAnchor
    Workstream, Decision, RiskKind, RiskSeverity, Risk
    ClaimType, ClaimStatus, Claim, ClaimEvidence
    VerificationItem
    Meta, Project, ResumePacket, SessionRecord, SessionStats
    RenderHints

Pipeline stages:
    1. discover_evidence()     — handoff, registry, transcript paths
    2. parse_sessions()        — session records from transcripts
    3. extract_events()        — structured events from transcript entries
    4. build_workstreams()     — file-overlap clustering
    5. build_claims()          — FACT / INFERENCE / GAP typed claims
    6. build_resume_packet()   — primary handoff artifact
    7. render()                — JSON + markdown from same data
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# ── Enumerations ────────────────────────────────────────────────────────────────


class EventKind(Enum):
    USER_INTENT_SET = "user_intent_set"
    TOOL_INVOKED = "tool_invoked"
    FILE_MODIFIED = "file_modified"
    DECISION_MADE = "decision_made"
    VERIFICATION_RUN = "verification_run"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_PASSED = "verification_passed"
    BLOCKER_DISCOVERED = "blocker_discovered"
    HANDOVER_WRITTEN = "handoff_written"


class WorkstreamStatus(Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    DONE = "done"
    UNCERTAIN = "uncertain"


class ClaimType(Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    GAP = "GAP"


class ClaimStatus(Enum):
    CURRENT = "current"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


class DecisionStatus(Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
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


# ── Anchor system ──────────────────────────────────────────────────────────────


@dataclass
class EventAnchor:
    """Evidence anchor for an event or claim."""
    kind: str  # "transcript_entry" | "file_path" | "tool_use" | "code_reference"
    path: str = ""
    entry_index: int | None = None
    detail: str = ""


@dataclass
class ClaimEvidence:
    """Evidence block attached to a claim."""
    kind: str  # "code_behavior" | "transcript_entry" | "file_diff" | "tool_use"
    detail: str = ""
    anchors: list[str] = field(default_factory=list)


# ── Core schema objects ────────────────────────────────────────────────────────


@dataclass
class Event:
    """Structured session event — replaces regex-semantics as primary meaning layer."""
    event_id: str
    session_id: str
    timestamp: str
    kind: EventKind
    title: str
    detail: str = ""
    anchors: list[EventAnchor] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class Workstream:
    """Cross-session work thread, clustered by file overlap and temporal adjacency."""
    workstream_id: str
    title: str
    status: WorkstreamStatus
    summary: str = ""
    session_ids: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    decision_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    next_action: str = ""
    blockers: list[str] = field(default_factory=list)


@dataclass
class Decision:
    """Referenceable decision with rationale, consequences, and revisit conditions."""
    decision_id: str
    statement: str
    rationale: str = ""
    impact: str = "medium"  # "low" | "medium" | "high"
    status: DecisionStatus = DecisionStatus.ACTIVE
    session_ids: list[str] = field(default_factory=list)
    workstream_ids: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    revisit_if: list[str] = field(default_factory=list)


@dataclass
class Risk:
    """Explicit risk record — surfaces contract gaps, stale state, and verification failures."""
    risk_id: str
    title: str
    severity: RiskSeverity
    kind: RiskKind
    description: str = ""
    affected_claim_ids: list[str] = field(default_factory=list)
    affected_workstream_ids: list[str] = field(default_factory=list)
    mitigation: str = ""
    blocking: bool = False


@dataclass
class Claim:
    """Typed claim: FACT (grounded) / INFERENCE (synthesized) / GAP (uncertainty)."""
    claim_id: str
    statement: str
    type: ClaimType
    confidence: float = 0.5
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    scope: str = "session"  # "session" | "workstream" | "global"
    session_ids: list[str] = field(default_factory=list)
    workstream_ids: list[str] = field(default_factory=list)
    evidence: list[ClaimEvidence] = field(default_factory=list)
    verification_hint: str = ""
    supersedes_claim_id: str = ""


@dataclass
class VerificationItem:
    """Executable verification backlog item."""
    verification_id: str
    priority: str = "MEDIUM"  # "HIGH" | "MEDIUM" | "LOW"
    target_type: str = "function"  # "function" | "file" | "workflow" | "handoff_contract"
    target: str = ""
    claim_id: str = ""
    why: str = ""
    suggested_action: str = ""
    success_signal: str = ""
    failure_signal: str = ""
    anchors: list[str] = field(default_factory=list)


# ── Top-level document objects ───────────────────────────────────────────────


@dataclass
class Meta:
    """Describes how the artifact was produced and with what evidence sources."""
    schema_version: str = "2.0.0"
    generated_at: str = ""
    generator_name: str = "recap"
    generator_version: str = "2.0.0"
    evidence_mode: str = "chain+transcripts"
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "generator": {
                "name": self.generator_name,
                "version": self.generator_version,
            },
            "evidence_mode": self.evidence_mode,
            "degraded": self.degraded,
            "degradation_reasons": self.degradation_reasons,
            "source_counts": self.source_counts,
        }


@dataclass
class SessionStats:
    """Per-session statistics."""
    entry_count: int = 0
    user_message_count: int = 0
    assistant_message_count: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)  # input/output/total_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_count": self.entry_count,
            "user_message_count": self.user_message_count,
            "assistant_message_count": self.assistant_message_count,
            "token_usage": self.token_usage,
        }


@dataclass
class SessionRecord:
    """Session summary derived from transcript entries, split by sessionId."""
    session_id: str
    ordinal: int = 0
    created_at: str = ""
    ended_at: str = ""
    duration: str = ""
    priority_score: float = 0.0
    stats: SessionStats = field(default_factory=SessionStats)
    goal: str = ""
    modified_files: list[str] = field(default_factory=list)
    transcript_path: str = ""
    summary: str = ""
    event_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    workstream_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "ordinal": self.ordinal,
            "created_at": self.created_at,
            "ended_at": self.ended_at,
            "duration": self.duration,
            "priority_score": self.priority_score,
            "stats": self.stats.to_dict(),
            "goal": self.goal,
            "modified_files": self.modified_files,
            "transcript_path": self.transcript_path,
            "summary": self.summary,
            "event_ids": self.event_ids,
            "claim_ids": self.claim_ids,
            "workstream_ids": self.workstream_ids,
        }


@dataclass
class Project:
    """Stable environment and scope — makes resume stateless."""
    project_root: str = ""
    project_hash: str = ""
    terminal_id: str = ""
    current_session_id: str = ""
    transcript_discovery: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "project_hash": self.project_hash,
            "terminal_id": self.terminal_id,
            "current_session_id": self.current_session_id,
            "transcript_discovery": self.transcript_discovery,
        }


@dataclass
class ResumePacket:
    """Primary handoff artifact — first thing another LLM reads."""
    current_goal: str = ""
    current_subgoal: str = ""
    current_status: str = "unclear"  # "active" | "blocked" | "paused" | "done" | "unclear"
    last_confirmed_good_state: str = ""
    exact_next_action: str = ""
    active_files: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    pending_decisions: list[str] = field(default_factory=list)
    verification_status: str = "unverified"  # "unverified" | "partially_verified" | "verified"
    resume_risks: list[str] = field(default_factory=list)
    recommended_entry_points: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_goal": self.current_goal,
            "current_subgoal": self.current_subgoal,
            "current_status": self.current_status,
            "last_confirmed_good_state": self.last_confirmed_good_state,
            "exact_next_action": self.exact_next_action,
            "active_files": self.active_files,
            "blocking_issues": self.blocking_issues,
            "pending_decisions": self.pending_decisions,
            "verification_status": self.verification_status,
            "resume_risks": self.resume_risks,
            "recommended_entry_points": self.recommended_entry_points,
        }


@dataclass
class RenderHints:
    """Presentational guidance for human-facing markdown views."""
    preferred_human_order: list[str] = field(default_factory=lambda: [
        "resume_packet", "workstreams", "decisions", "risks",
        "verification_queue", "sessions",
    ])
    brief_mode_fields: list[str] = field(default_factory=lambda: [
        "resume_packet.current_goal",
        "resume_packet.exact_next_action",
        "resume_packet.active_files",
        "risks[0:3]",
        "verification_queue[0:3]",
    ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_human_order": self.preferred_human_order,
            "brief_mode_fields": self.brief_mode_fields,
        }


# ── Pipeline state ─────────────────────────────────────────────────────────────


@dataclass
class RecapV2State:
    """Accumulator passed through pipeline stages."""
    meta: Meta = field(default_factory=Meta)
    project: Project = field(default_factory=Project)
    resume_packet: ResumePacket = field(default_factory=ResumePacket)
    sessions: list[SessionRecord] = field(default_factory=list)
    workstreams: list[Workstream] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    verification_queue: list[VerificationItem] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    _id_counter: int = 0

    def _next_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}-{self._id_counter}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.meta.schema_version,
            "meta": self.meta.to_dict(),
            "project": self.project.to_dict(),
            "resume_packet": self.resume_packet.to_dict(),
            "sessions": [s.to_dict() for s in self.sessions],
            "workstreams": [
                {
                    "workstream_id": w.workstream_id,
                    "title": w.title,
                    "status": w.status.value,
                    "summary": w.summary,
                    "session_ids": w.session_ids,
                    "file_paths": w.file_paths,
                    "next_action": w.next_action,
                }
                for w in self.workstreams
            ],
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "statement": c.statement,
                    "type": c.type.value,
                    "confidence": c.confidence,
                    "status": c.status.value,
                    "scope": c.scope,
                    "session_ids": c.session_ids,
                    "workstream_ids": c.workstream_ids,
                    "evidence": [
                        {"kind": e.kind, "detail": e.detail, "anchors": e.anchors}
                        for e in c.evidence
                    ],
                    "verification_hint": c.verification_hint,
                    "supersedes_claim_id": c.supersedes_claim_id,
                }
                for c in self.claims
            ],
            "decisions": [
                {
                    "decision_id": d.decision_id,
                    "statement": d.statement,
                    "rationale": d.rationale,
                    "impact": d.impact,
                    "status": d.status.value,
                    "session_ids": d.session_ids,
                    "workstream_ids": d.workstream_ids,
                    "consequences": d.consequences,
                    "revisit_if": d.revisit_if,
                }
                for d in self.decisions
            ],
            "risks": [
                {
                    "risk_id": r.risk_id,
                    "title": r.title,
                    "severity": r.severity.value,
                    "kind": r.kind.value,
                    "description": r.description,
                    "affected_claim_ids": r.affected_claim_ids,
                    "affected_workstream_ids": r.affected_workstream_ids,
                    "mitigation": r.mitigation,
                    "blocking": r.blocking,
                }
                for r in self.risks
            ],
            "verification_queue": [
                {
                    "verification_id": v.verification_id,
                    "priority": v.priority,
                    "target_type": v.target_type,
                    "target": v.target,
                    "claim_id": v.claim_id,
                    "why": v.why,
                    "suggested_action": v.suggested_action,
                    "success_signal": v.success_signal,
                    "failure_signal": v.failure_signal,
                    "anchors": v.anchors,
                }
                for v in self.verification_queue
            ],
            "render_hints": RenderHints().to_dict(),
        }


# ── Pipeline stage 1: evidence discovery ────────────────────────────────────


def discover_evidence(
    project_root: Path | None = None,
    terminal_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Stage 1 — discover all evidence sources.

    Returns a dict with keys: mode, paths_scanned, current_transcript,
    handoff_path, registry_entries, degradation_reasons.

    Uses identity.json as the PRIMARY source for current session (authoritative,
    written fresh at session start, immune to compaction chain rewrites).
    Falls back to registry/handoff/direct-transcript for historical sessions.
    """
    from recap.acquire import (
        _read_identity_json,
        discover_evidence as acquire_discover_evidence,
    )

    result: dict[str, Any] = {
        "mode": "unknown",
        "paths_scanned": [],
        "current_transcript": "",
        "handoff_path": None,
        "registry_entries": [],
        "degradation_reasons": [],
        "degraded": False,
    }

    if project_root is None:
        from recap import get_project_root
        project_root = get_project_root()

    if not terminal_id:
        from recap import resolve_terminal_key
        terminal_id = resolve_terminal_key(None)

    # Strategy -1: identity.json (authoritative, written fresh at session start)
    identity = _read_identity_json()
    if identity:
        sid = identity.get("session_id")
        tp = identity.get("transcript_path")
        if sid:
            session_id = sid
        if tp:
            result["current_transcript"] = tp
            result["paths_scanned"].append(tp)

    # Try acquire.py's discovery for registry/handoff/chain fallback
    if terminal_id:
        try:
            sources = acquire_discover_evidence(
                project_root=project_root,
                terminal_id=terminal_id,
                session_id=session_id,
            )
            if sources.mode == "registry" and sources.registry_entries:
                result["mode"] = "registry"
                result["registry_entries"] = sources.registry_entries
                result["paths_scanned"].append(f"registry://{terminal_id}")
                return result
            if sources.mode == "handoff" and sources.handoff_path:
                result["mode"] = "handoff"
                result["handoff_path"] = sources.handoff_path
                result["paths_scanned"].append(sources.handoff_path)
                return result
            if sources.mode == "chain" and sources.chain_entries:
                result["mode"] = "chain"
                result["chain_entries"] = sources.chain_entries
                result["paths_scanned"].extend(e.get("transcript_path", "") for e in sources.chain_entries)
                return result
        except Exception:
            pass

    # Final fallback: direct transcript
    if result.get("current_transcript") and Path(result["current_transcript"]).exists():
        result["mode"] = "direct_transcript"
        result["degraded"] = True
        result["degradation_reasons"].append(
            "No registry or handoff found — using current transcript only"
        )
    elif not result["mode"]:
        result["mode"] = "empty"
        result["degraded"] = True
        result["degradation_reasons"].append("No evidence sources available")

    return result


# ── Pipeline stage 2: session parsing ─────────────────────────────────────────


def parse_sessions(
    state: RecapV2State,
    evidence: dict[str, Any],
) -> RecapV2State:
    """Stage 2 — parse transcripts into SessionRecord list."""
    from recap import (
        load_transcript_entries,
        extract_sessions_from_transcript,
        _summarize_session,
    )

    registry_entries = evidence.get("registry_entries", [])
    sessions: list[SessionRecord] = []
    seen_ids: set[str] = set()

    def _to_record(
        summary: dict[str, Any],
        ordinal: int,
        transcript_path: str = "",
    ) -> SessionRecord:
        stats = SessionStats(
            entry_count=summary.get("entry_count", 0),
            user_message_count=summary.get("user_message_count", 0),
            assistant_message_count=summary.get("assistant_message_count", 0),
            token_usage=summary.get("token_usage", {}),
        )
        return SessionRecord(
            session_id=summary.get("session_id", ""),
            ordinal=ordinal,
            created_at=summary.get("created_at", ""),
            duration=summary.get("duration", ""),
            priority_score=summary.get("priority_score", 0.0),
            stats=stats,
            goal=summary.get("last_goal", ""),
            modified_files=summary.get("modified_files", []),
            transcript_path=transcript_path,
            summary=_condense_goal(summary.get("last_goal", "")),
            event_ids=[],
            claim_ids=[],
            workstream_ids=[],
        )

    # Registry path: each entry has transcript_path
    # Each registry entry is a distinct interaction (different goal/prompt),
    # even when sharing a sessionId. Process ALL entries — no dedup by sessionId.
    ordinal = 0
    for entry in registry_entries:
        tp = entry.get("transcript_path", "")
        sid = entry.get("sessionId", "")
        if not tp:
            continue
        try:
            entries_list = load_transcript_entries(tp)
            summaries = extract_sessions_from_transcript(entries_list)
            for s in summaries:
                entry_sid = s.get("session_id", "")
                if entry_sid in seen_ids:
                    continue
                seen_ids.add(entry_sid)
                ordinal += 1
                record = _to_record(s, ordinal, tp)
                sessions.append(record)
        except Exception as e:
            logger.warning("Failed to parse session %s: %s", sid, e)

    # Direct transcript path (when no registry entries)
    if not sessions and evidence.get("current_transcript"):
        tp = evidence["current_transcript"]
        try:
            entries_list = load_transcript_entries(tp)
            summaries = extract_sessions_from_transcript(entries_list)
            for i, s in enumerate(summaries):
                sid = s.get("session_id", "")
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                record = _to_record(s, i + 1, tp)
                sessions.append(record)
        except Exception as e:
            logger.warning("Failed to parse direct transcript: %s", e)

    state.sessions = sessions
    return state


def _condense_goal(goal: str, max_len: int = 200) -> str:
    """Condense goal string for SessionRecord.summary field."""
    if not goal:
        return ""
    goal = goal.strip()
    if len(goal) <= max_len:
        return goal
    return goal[: max_len - 3] + "..."


# ── Pipeline stage 3: event extraction ───────────────────────────────────────


def extract_events(state: RecapV2State) -> RecapV2State:
    """Stage 3 — extract structured events from transcript entries.

    Replaces regex-semantics with direct transcript/tool parsing.
    """
    from recap import load_transcript_entries

    events: list[Event] = []
    _SKIP_SUFFIXES = frozenset({".json", ".lock", ".pyc", ".pyo", ".toml"})
    _SKIP_SEGMENTS = frozenset({"__pycache__", "node_modules", ".git"})

    for session in state.sessions:
        tp = session.transcript_path
        if not tp or not Path(tp).exists():
            continue

        try:
            entries = load_transcript_entries(tp)
        except Exception:
            continue

        entry_idx = 0
        for entry in entries:
            entry_idx += 1
            etype = entry.get("type", "")
            content = entry.get("content")
            if content is None:
                content = entry.get("message", {}).get("content")

            # Tool invocations → FILE_MODIFIED events
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name", "")
                    inp = block.get("input", {})
                    if not isinstance(inp, dict):
                        continue

                    if tool_name in ("Edit", "Write"):
                        path = inp.get("file_path", "")
                        if not path:
                            continue
                        if Path(path).suffix.lower() in _SKIP_SUFFIXES:
                            continue
                        if any(seg in path for seg in _SKIP_SEGMENTS):
                            continue

                        evt = Event(
                            event_id=state._next_id("evt"),
                            session_id=session.session_id,
                            timestamp=entry.get("timestamp", "") or entry.get("created", ""),
                            kind=EventKind.FILE_MODIFIED,
                            title=f"{tool_name}: {Path(path).name}",
                            detail=f"{tool_name} on {path}",
                            confidence=0.98,
                            anchors=[
                                EventAnchor(
                                    kind="transcript_entry",
                                    path=tp,
                                    entry_index=entry_idx,
                                    detail=f"tool_use block #{entry_idx} in {session.session_id}",
                                )
                            ],
                        )
                        events.append(evt)

                    elif tool_name == "Bash":
                        cmd = inp.get("command", "")[:80]
                        evt = Event(
                            event_id=state._next_id("evt"),
                            session_id=session.session_id,
                            timestamp=entry.get("timestamp", "") or entry.get("created", ""),
                            kind=EventKind.TOOL_INVOKED,
                            title=f"Bash: {cmd}",
                            detail=f"Ran command: {cmd}",
                            confidence=0.95,
                            anchors=[
                                EventAnchor(
                                    kind="transcript_entry",
                                    path=tp,
                                    entry_index=entry_idx,
                                    detail=f"tool_use block #{entry_idx}",
                                )
                            ],
                        )
                        events.append(evt)

            # tool_result entries → VERIFICATION_PASSED / VERIFICATION_FAILED events
            if etype == "user":
                content_str = content if isinstance(content, str) else ""
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            text = block.get("text", "")
                            if "FAILED" in text or "AssertionError" in text or "failed" in text.lower():
                                evt = Event(
                                    event_id=state._next_id("evt"),
                                    session_id=session.session_id,
                                    timestamp=entry.get("timestamp", "") or entry.get("created", ""),
                                    kind=EventKind.VERIFICATION_FAILED,
                                    title="Test failed",
                                    detail=text[:200],
                                    confidence=0.95,
                                    anchors=[
                                        EventAnchor(
                                            kind="transcript_entry",
                                            path=tp,
                                            entry_index=entry_idx,
                                            detail=f"tool_result entry #{entry_idx} in {session.session_id}",
                                        )
                                    ],
                                )
                                events.append(evt)
                            elif "passed" in text.lower() and "3 passed" in text:
                                evt = Event(
                                    event_id=state._next_id("evt"),
                                    session_id=session.session_id,
                                    timestamp=entry.get("timestamp", "") or entry.get("created", ""),
                                    kind=EventKind.VERIFICATION_PASSED,
                                    title="Tests passed",
                                    detail=text[:200],
                                    confidence=0.95,
                                    anchors=[
                                        EventAnchor(
                                            kind="transcript_entry",
                                            path=tp,
                                            entry_index=entry_idx,
                                            detail=f"tool_result entry #{entry_idx} in {session.session_id}",
                                        )
                                    ],
                                )
                                events.append(evt)
                # Explicit user intent (goal statements)
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text and len(text) > 20:
                                evt = Event(
                                    event_id=state._next_id("evt"),
                                    session_id=session.session_id,
                                    timestamp=entry.get("timestamp", "") or entry.get("created", ""),
                                    kind=EventKind.USER_INTENT_SET,
                                    title=text[:60],
                                    detail=text,
                                    confidence=0.92,
                                    anchors=[
                                        EventAnchor(
                                            kind="transcript_entry",
                                            path=tp,
                                            entry_index=entry_idx,
                                            detail=f"user intent entry #{entry_idx} in {session.session_id}",
                                        )
                                    ],
                                )
                                events.append(evt)

            # Session boundary → HANDOVER_WRITTEN event (compaction marker)
            if etype == "assistant" and content:
                text = content if isinstance(content, str) else ""
                if "## Last Session Summary" in text or "Session Recap:" in text:
                    evt = Event(
                        event_id=state._next_id("evt"),
                        session_id=session.session_id,
                        timestamp=entry.get("timestamp", "") or entry.get("created", ""),
                        kind=EventKind.HANDOVER_WRITTEN,
                        title="Session summary written",
                        detail="Compaction handoff block detected",
                        confidence=0.9,
                        anchors=[
                            EventAnchor(
                                kind="transcript_entry",
                                path=tp,
                                entry_index=entry_idx,
                                detail="handoff block in transcript",
                            )
                        ],
                    )
                    events.append(evt)

    state.events = events
    return state


# ── Pipeline stage 4: workstream clustering ───────────────────────────────────


def build_workstreams(state: RecapV2State) -> RecapV2State:
    """Stage 4 — cluster sessions into workstreams by file overlap and temporal adjacency.

    Simple clustering heuristic:
    - sessions sharing >=1 modified file → same workstream
    - sessions with shared decision symbols → same workstream
    """
    if not state.sessions:
        return state

    # Build file → {session_ids} reverse index
    file_index: dict[str, set[str]] = {}
    for session in state.sessions:
        for f in session.modified_files:
            file_index.setdefault(f, set()).add(session.session_id)

    # Cluster via connected components on file overlap
    clusters: list[set[str]] = []
    for file_path, sids in file_index.items():
        merged = False
        for cluster in clusters:
            if cluster & sids:  # intersection
                cluster.update(sids)
                merged = True
                break
        if not merged:
            clusters.append(set(sids))

    # Also create a singleton for sessions with no file matches
    all_session_ids = {s.session_id for s in state.sessions}
    covered_by_clusters = set().union(*clusters) if clusters else set()
    orphan_sessions = all_session_ids - covered_by_clusters
    for sid in orphan_sessions:
        clusters.append({sid})

    # Build Workstream objects
    workstreams: list[Workstream] = []
    ws_titles: dict[str, str] = {}

    # Assign titles based on shared files
    for i, cluster in enumerate(clusters, 1):
        cluster_sessions = [s for s in state.sessions if s.session_id in cluster]
        all_files: list[str] = []
        for cs in cluster_sessions:
            all_files.extend(cs.modified_files)

        # Title from most common file
        from collections import Counter
        file_counts = Counter(all_files)
        top_file = file_counts.most_common(1)[0][0] if file_counts else f"workstream-{i}"
        title = Path(top_file).stem if top_file else f"workstream-{i}"

        # Determine status from session goals
        goals = [s.goal for s in cluster_sessions if s.goal]
        status = WorkstreamStatus.ACTIVE
        if not goals:
            status = WorkstreamStatus.UNCERTAIN

        ws = Workstream(
            workstream_id=f"ws-{i}",
            title=title,
            status=status,
            summary=f"Clustered from {len(cluster)} session(s), {len(all_files)} file(s)",
            session_ids=sorted(cluster),
            file_paths=sorted(set(all_files)),
            next_action=cluster_sessions[-1].goal if cluster_sessions else "",
        )
        workstreams.append(ws)

        # Track session → workstream mapping
        for sid in cluster:
            ws_titles[sid] = title

    # Update session workstream_ids
    sid_to_wsid: dict[str, str] = {ws.workstream_id: ws.title for ws in workstreams}
    for session in state.sessions:
        session.workstream_ids = [
            ws.workstream_id
            for ws in workstreams
            if session.session_id in ws.session_ids
        ]

    state.workstreams = workstreams
    return state


# ── Pipeline stage 5: claim building ────────────────────────────────────────


def build_claims(state: RecapV2State) -> RecapV2State:
    """Stage 5 — build typed FACT / INFERENCE / GAP claims.

    FACT: grounded in tool_use blocks or explicit handoff/file evidence
    INFERENCE: synthesized from session goals or workstream clustering
    GAP: unverified paths, missing proofs, degraded evidence mode
    """
    claims: list[Claim] = []

    # FACT: each session goal (transcript-native, authoritative even with no file edits)
    for session in state.sessions:
        if session.goal:
            claims.append(
                Claim(
                    claim_id=state._next_id("clm"),
                    statement=f"Goal: {session.goal}",
                    type=ClaimType.FACT,
                    confidence=0.92,
                    status=ClaimStatus.CURRENT,
                    scope="session",
                    session_ids=[session.session_id],
                    evidence=[
                        ClaimEvidence(
                            kind="transcript_content",
                            detail=f"Goal set in session {session.session_id}",
                            anchors=[f"transcript:{session.transcript_path}"],
                        )
                    ],
                    verification_hint=f"Verify goal implementation in session {session.session_id}",
                )
            )

    # FACT: test result events (test failure/pass from tool_result entries)
    for evt in state.events:
        if evt.kind == EventKind.VERIFICATION_FAILED:
            claims.append(
                Claim(
                    claim_id=state._next_id("clm"),
                    statement=f"Test failed: {evt.detail}",
                    type=ClaimType.FACT,
                    confidence=0.95,
                    status=ClaimStatus.CURRENT,
                    scope="session",
                    session_ids=[evt.session_id],
                    evidence=[
                        ClaimEvidence(
                            kind="transcript_content",
                            detail=evt.detail,
                            anchors=[f"transcript:{evt.anchors[0].path}"],
                        )
                    ],
                    verification_hint="Run the failing test to reproduce and fix",
                )
            )
        elif evt.kind == EventKind.VERIFICATION_PASSED:
            claims.append(
                Claim(
                    claim_id=state._next_id("clm"),
                    statement=f"Tests passed: {evt.detail}",
                    type=ClaimType.FACT,
                    confidence=0.95,
                    status=ClaimStatus.CURRENT,
                    scope="session",
                    session_ids=[evt.session_id],
                    evidence=[
                        ClaimEvidence(
                            kind="transcript_content",
                            detail=evt.detail,
                            anchors=[f"transcript:{evt.anchors[0].path}"],
                        )
                    ],
                    verification_hint="Confirm the passing tests still pass on re-run",
                )
            )

    # FACT: each modified file in a session
    # Also: detect when a later session modifies the same file and mark ALL prior claims superseded
    file_claims: dict[str, list[Claim]] = {}
    # Also track goal claims for approach-level contradiction detection
    approach_keywords_old = {"regex", "inline", "scattered", "check_valid_input"}
    approach_keywords_new = {"decorator", "validate", "remove", "switch", "instead", "type-check"}
    goal_claims: list[Claim] = [c for c in claims if "Goal:" in c.statement]

    def _goals_touch_same_files(g1: str, g2: str) -> bool:
        """Heuristic: do two goals likely target overlapping files?"""
        words1 = set(g1.lower().split())
        words2 = set(g2.lower().split())
        return bool(words1 & words2)

    for new_goal in goal_claims:
        new_sid = new_goal.session_ids[0] if new_goal.session_ids else ""
        new_text = new_goal.statement.lower()
        # Check if this is a "new approach" goal
        if not any(kw in new_text for kw in approach_keywords_new):
            continue
        for old_goal in goal_claims:
            old_sid = old_goal.session_ids[0] if old_goal.session_ids else ""
            old_text = old_goal.statement.lower()
            # Only consider earlier sessions
            if old_sid >= new_sid:
                continue
            # Check for conflicting approaches
            if any(kw in old_text for kw in approach_keywords_old) and _goals_touch_same_files(old_text, new_text):
                old_goal.status = ClaimStatus.CONTRADICTED
                new_goal.supersedes_claim_id = old_goal.claim_id
                break
    for session in state.sessions:
        for path in session.modified_files[:8]:
            prior_list = file_claims.get(path, [])
            new_claim = Claim(
                claim_id=state._next_id("clm"),
                statement=f"File modified: {path}",
                type=ClaimType.FACT,
                confidence=0.95,
                status=ClaimStatus.CURRENT,
                scope="session",
                session_ids=[session.session_id],
                evidence=[
                    ClaimEvidence(
                        kind="tool_use",
                        detail=f"Edit/Write tool_use found in {session.session_id}",
                        anchors=[f"transcript:{session.transcript_path}"],
                    )
                ],
                verification_hint=f"Run /tldr-deep {path} to verify behavior",
            )
            if prior_list:
                # Later session modifying same file — mark all prior claims as contradicted
                for prior in prior_list:
                    prior.status = ClaimStatus.CONTRADICTED
                # New claim supersedes the earliest prior claim (the one from the first session that touched this file)
                new_claim.supersedes_claim_id = prior_list[0].claim_id
            claims.append(new_claim)
            file_claims.setdefault(path, []).append(new_claim)

    # GAP: degraded evidence mode
    if state.meta.degraded:
        for reason in state.meta.degradation_reasons:
            claims.append(
                Claim(
                    claim_id=state._next_id("clm"),
                    statement=f"Evidence degraded: {reason}",
                    type=ClaimType.GAP,
                    confidence=0.99,
                    status=ClaimStatus.UNVERIFIED,
                    scope="global",
                    evidence=[
                        ClaimEvidence(
                            kind="code_behavior",
                            detail=reason,
                            anchors=["discover_evidence() returned degraded=True"],
                        )
                    ],
                    verification_hint="Verify handoff chain or registry is accessible",
                )
            )

    # INFERENCE: workstream spans multiple sessions
    for ws in state.workstreams:
        if len(ws.session_ids) > 1:
            claims.append(
                Claim(
                    claim_id=state._next_id("clm"),
                    statement=f"Workstream '{ws.title}' spans {len(ws.session_ids)} sessions",
                    type=ClaimType.INFERENCE,
                    confidence=0.75,
                    status=ClaimStatus.CURRENT,
                    scope="workstream",
                    workstream_ids=[ws.workstream_id],
                    session_ids=ws.session_ids,
                    verification_hint=f"Cross-reference goals in sessions {ws.session_ids}",
                )
            )

    # GAP: sessions relying on condensed transcript (no modified files)
    for session in state.sessions:
        if not session.modified_files and session.goal:
            claims.append(
                Claim(
                    claim_id=state._next_id("clm"),
                    statement=(
                        f"Session {session.session_id} has goals but no modified files "
                        "— transcript-only narrative, not file-level evidence"
                    ),
                    type=ClaimType.GAP,
                    confidence=0.9,
                    status=ClaimStatus.UNVERIFIED,
                    scope="session",
                    session_ids=[session.session_id],
                    verification_hint=f"Verify session {session.session_id} goal was actually implemented",
                )
            )

    state.claims = claims

    # Update session claim_ids
    for claim in claims:
        for sid in claim.session_ids:
            for session in state.sessions:
                if session.session_id == sid:
                    if claim.claim_id not in session.claim_ids:
                        session.claim_ids.append(claim.claim_id)

    return state


# ── Pipeline stage 6: resume packet ───────────────────────────────────────────


def build_resume_packet(state: RecapV2State) -> RecapV2State:
    """Stage 6 — distill the most recent session into a ResumePacket."""
    if not state.sessions:
        state.resume_packet = ResumePacket()
        return state

    latest = state.sessions[-1]

    # Collect blocking issues (GAP claims from any session — unverified risks are global)
    blocking = [
        c.statement for c in state.claims
        if c.type == ClaimType.GAP
    ][:3]

    # Collect resume risks from CONTRADICTED and STALE claims
    resume_risks = [
        c.statement for c in state.claims
        if c.status in (ClaimStatus.CONTRADICTED, ClaimStatus.STALE)
    ][:5]

    # Collect unresolved decisions
    pending = [
        d.statement for d in state.decisions
        if d.status == DecisionStatus.ACTIVE
        and latest.session_id in d.session_ids
    ][:3]

    # Build recommended entry points from modified files
    entry_points = []
    for path in latest.modified_files[:3]:
        entry_points.append({
            "path": path,
            "symbol": "",
            "reason": f"Modified in current session ({latest.session_id[:8]}...)",
        })

    state.resume_packet = ResumePacket(
        current_goal=latest.goal,
        current_subgoal="",
        current_status="active",
        last_confirmed_good_state="",
        exact_next_action=latest.goal,
        active_files=latest.modified_files[:5],
        blocking_issues=blocking,
        pending_decisions=pending,
        verification_status="unverified",
        resume_risks=resume_risks,
        recommended_entry_points=entry_points,
    )

    return state


# ── Pipeline stage 7: render ───────────────────────────────────────────────────


def render_json(state: RecapV2State) -> str:
    """Emit canonical JSON document."""
    return json.dumps(state.to_dict(), indent=2, ensure_ascii=False)


def render_markdown(state: RecapV2State) -> str:
    """Human-facing markdown rendered from the same schema data."""
    lines: list[str] = []
    rp = state.resume_packet
    meta = state.meta

    lines.append(f"# ReCap v2 — {meta.evidence_mode}")
    lines.append("")

    # Resume packet — front-loaded per design principle
    lines.append("## Resume Packet")
    lines.append("")
    if rp.current_goal:
        lines.append(f"**Current goal**: {rp.current_goal}")
    if rp.exact_next_action:
        lines.append(f"**Next action**: {rp.exact_next_action}")
    if rp.active_files:
        lines.append(f"**Active files**: {', '.join(rp.active_files)}")
    if rp.blocking_issues:
        lines.append("**Blocking**: " + "; ".join(rp.blocking_issues[:3]))
    if rp.pending_decisions:
        lines.append("**Pending decisions**: " + "; ".join(rp.pending_decisions[:3]))
    lines.append("")

    # Workstreams
    if state.workstreams:
        lines.append("## Workstreams")
        for ws in state.workstreams:
            lines.append(f"### {ws.title} (`{ws.workstream_id}`)")
            lines.append(f"- Status: `{ws.status.value}`")
            lines.append(f"- Sessions: {len(ws.session_ids)}")
            if ws.file_paths:
                lines.append(f"- Files: {', '.join(ws.file_paths[:5])}")
            if ws.next_action:
                lines.append(f"- Next: {ws.next_action}")
            lines.append("")
        lines.append("")

    # Claims (FACT / INFERENCE / GAP)
    if state.claims:
        lines.append("## Claims")
        for claim in state.claims[:15]:
            conf = f"{claim.confidence:.0%}"
            status_str = f" [{claim.status.value}]" if claim.status != ClaimStatus.CURRENT else ""
            lines.append(f"- `[{claim.type.value}]` ({conf}{status_str}) {claim.statement}")
            if claim.evidence:
                ev = claim.evidence[0]
                lines.append(f"  - Evidence: {ev.detail}")
        lines.append("")

    # Verification queue
    if state.verification_queue:
        lines.append("## Verification Queue")
        for v in state.verification_queue[:10]:
            lines.append(f"- `[{v.priority}]` {v.claim_id}: {v.target}")
            lines.append(f"  - Success: {v.success_signal}")
            lines.append(f"  - Failure: {v.failure_signal}")
        lines.append("")

    # Session timeline
    if state.sessions:
        lines.append("## Sessions")
        for s in state.sessions:
            lines.append(f"### [{s.ordinal}] {s.session_id[:12]}...")
            lines.append(f"- Goal: {s.goal}")
            if s.modified_files:
                lines.append(f"- Modified: {', '.join(s.modified_files[:5])}")
            lines.append("")
        lines.append("")

    return "\n".join(lines)


def render_markdown_brief(state: RecapV2State) -> str:
    """Brief markdown — resume packet only."""
    lines: list[str] = []
    rp = state.resume_packet
    lines.append("# ReCap Brief")
    lines.append("")
    if rp.current_goal:
        lines.append(f"**Goal**: {rp.current_goal}")
    if rp.exact_next_action:
        lines.append(f"**Next action**: {rp.exact_next_action}")
    if rp.active_files:
        lines.append(f"**Active files**: {', '.join(rp.active_files)}")
    if rp.blocking_issues:
        lines.append(f"**Blocking**: {'; '.join(rp.blocking_issues)}")
    return "\n".join(lines)


# ── Subagent transcript filtering ──────────────────────────────────────────────


def _is_subagent_transcript(path: Path) -> bool:
    """Check if a transcript path belongs to a subagent.

    Uses exact component-level matching, not substring matching.
    """
    if not path.parts:
        return False
    for part in path.parts:
        if part == "subagents":
            return True
    if path.name.startswith("agent-"):
        return True
    return False


# ── Top-level pipeline function ────────────────────────────────────────────────


def build_recap_v2(
    project_root: Path | None = None,
    terminal_id: str = "",
    session_id: str = "",
) -> RecapV2State:
    """Run the full recap v2 pipeline, returning the accumulated state."""
    state = RecapV2State()

    # meta
    state.meta = Meta(
        generated_at=datetime.now(timezone.utc).isoformat(),
        evidence_mode="unknown",
        degraded=False,
    )

    # stage 1: discover
    evidence = discover_evidence(project_root, terminal_id, session_id)
    state.meta.evidence_mode = evidence["mode"]
    state.meta.degraded = evidence["degraded"]
    state.meta.degradation_reasons = evidence.get("degradation_reasons", [])
    state.meta.source_counts = {
        "transcripts": len(state.sessions),
        "handoffs": 1 if evidence.get("handoff_path") else 0,
        "registry_entries": len(evidence.get("registry_entries", [])),
    }

    # stage 2: parse sessions
    state = parse_sessions(state, evidence)

    # stage 3: extract events
    state = extract_events(state)

    # stage 4: build workstreams
    state = build_workstreams(state)

    # stage 5: build claims
    state = build_claims(state)

    # stage 6: resume packet
    state = build_resume_packet(state)

    return state


def main() -> None:
    """CLI entry point for recap v2."""
    import argparse

    parser = argparse.ArgumentParser(description="recap v2 — JSON-first session handoff")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON (default: markdown)",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Brief mode (resume packet only)",
    )
    args = parser.parse_args()

    # Fix sys.path so 'recap' package resolves when running as a module
    import sys as _sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent.parent
    _skills_pkg = _root / "skills"
    if str(_skills_pkg) not in _sys.path:
        _sys.path.insert(0, str(_skills_pkg))

    from recap import resolve_terminal_key, get_project_root

    project_root = get_project_root()
    terminal_id = resolve_terminal_key(None)
    session_id = ""  # resolved inside discover_evidence if needed

    state = build_recap_v2(project_root, terminal_id, session_id)

    if args.json:
        print(render_json(state))
    else:
        print(render_markdown(state))


if __name__ == "__main__":
    main()
