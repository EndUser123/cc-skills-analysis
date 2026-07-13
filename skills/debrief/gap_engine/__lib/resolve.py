"""Finding resolution checker for GAP.

Determines which findings have been addressed by comparing against
session-scoped file changes, terminal-status short-circuit, and
registered resolution strategies (longest-prefix-wins dispatch).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from ..models import EvidenceRef, Finding

# Terminal statuses: once a finding reaches one of these, a matching strategy
# must NOT re-resolve it (was a latent re-resolution bug — a deferred/rejected
# finding could be flipped to resolved by a later file edit). SM-002.
_TERMINAL_STATUSES = frozenset({"resolved", "deferred", "rejected", "mapped"})


@dataclass(frozen=True)
class ResolveCtx:
    """Context threaded to every resolution strategy."""

    edited_file_set: set[str]
    root: Path
    transcript_explicit: bool = False
    session_id: str = ""


ResolutionStrategy = Callable[[Finding, ResolveCtx], "str | None"]


def _doc_strategy(_f: Finding, ctx: ResolveCtx) -> str | None:
    """DOC-* findings — README was missing; resolve if it now exists."""
    if (ctx.root / "README.md").exists():
        return "README.md now exists"
    return None


def _git_strategy(_f: Finding, ctx: ResolveCtx) -> str | None:
    """GIT-* findings — .git was missing; resolve if it now exists."""
    if (ctx.root / ".git").exists():
        return ".git directory now exists"
    return None


def _session_strategy(_f: Finding, ctx: ResolveCtx) -> str | None:
    """GAP-SESSION-* — resolve when the run was given an existing --transcript."""
    if ctx.transcript_explicit:
        return "resolved via --transcript"
    return None


# Extension point: add a strategy by registering its finding-ID prefix here.
# Dispatch is longest-prefix-wins, so GAP-SESSION-UNRESOLVED matches GAP-SESSION
# before any future GAP- strategy. Equal-length collisions raise at dispatch.
RESOLUTION_STRATEGIES: dict[str, ResolutionStrategy] = {
    "DOC-": _doc_strategy,
    "GIT-": _git_strategy,
    "GAP-SESSION": _session_strategy,
}


def _dispatch_strategy(f: Finding, ctx: ResolveCtx) -> str | None:
    """Run the longest registered prefix matching f.id. None if no match.

    A string has exactly one prefix of a given length, so among all matching
    prefixes the longest is unique — no tie-break needed.
    """
    matches = [p for p in RESOLUTION_STRATEGIES if f.id.startswith(p)]
    if not matches:
        return None
    best = max(matches, key=len)
    return RESOLUTION_STRATEGIES[best](f, ctx)


def resolve_findings(findings: list[Finding], ctx: ResolveCtx) -> list[Finding]:
    """Mark findings resolved against session edits, terminal status, and strategies.

    Returns a new list with status/evidence updated for resolved findings.
    Resolution signals, in order:
      1. Terminal status — resolved/deferred/rejected/mapped short-circuits (no re-resolve)
      2. File edit match — finding.file is in the session's edited set
      3. Registered strategy — longest-prefix match returns a non-None reason
    """
    result: list[Finding] = []
    for f in findings:
        resolved = _try_resolve(f, ctx)
        result.append(resolved if resolved else f)
    return result


def _try_resolve(f: Finding, ctx: ResolveCtx) -> Finding | None:
    """Attempt to resolve a single finding. Returns updated Finding or None."""
    # Signal 1: terminal status — do not re-resolve.
    if f.status in _TERMINAL_STATUSES:
        return f

    # Signal 2: file edit match.
    if f.file:
        normalized = f.file.replace("\\", "/")
        if normalized in ctx.edited_file_set:
            return _mark_resolved(f, f"file_edited: {f.file}")

    # Signal 3: registered strategy.
    reason = _dispatch_strategy(f, ctx)
    if reason:
        return _mark_resolved(f, reason)

    return None


def _mark_resolved(f: Finding, reason: str) -> Finding:
    """Return a copy of the finding with resolved status and evidence."""
    evidence = list(f.evidence) + [EvidenceRef(kind="auto_resolved", value=reason)]
    return replace(f, status="resolved", evidence=evidence)
