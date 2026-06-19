"""Hook health detector — scans transcript for hook execution errors.

Detects hook attachment entries with non-zero exit codes, indicating
hook failures that may have been silently suppressed (non-blocking errors).

What it detects:
- Hook executions with non-zero exit codes (errors, warnings)
- Hooks that consistently fail across sessions (via carryover)
- SessionStart hook failures that may affect session setup
- Freshness: hook errors are timestamped from the transcript entry so the
  operator can distinguish a live failure from a historical one. Errors
  older than 24h are downgraded to "low" severity and tagged "stale".

What it does NOT detect:
- PreToolUse exit(2) blocks (these are intentional, not errors)
- Hook performance issues (that's a separate concern)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import EvidenceRef, Finding

# PreToolUse exit(2) is intentional blocking — not a health issue
_BLOCKING_HOOK_PREFIXES = ("PreToolUse:", "UserPromptSubmit:")

# Hooks where non-zero exit is expected behavior
_EXPECTED_NONZERO_HOOKS = frozenset({
    "PreToolUse:edit", "PreToolUse:write", "PreToolUse:bash",
    "PreToolUse:read", "PreToolUse:agent", "PreToolUse:skill",
})

# Errors older than this are considered stale — downgraded to low severity
_STALE_HOOK_ERROR_HOURS = 24.0


def _parse_entry_timestamp(entry: dict[str, Any]) -> datetime | None:
    """Parse a transcript entry's ISO timestamp into a tz-aware datetime."""
    ts = entry.get("timestamp")
    if not ts or not isinstance(ts, str):
        return None
    try:
        # Format: 2026-06-05T17:15:12.196948+00:00 or 2026-06-05T17:15:12.196Z
        cleaned = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def _age_hours(timestamp: datetime | None) -> float | None:
    """Hours between `timestamp` and now (UTC). Returns None if timestamp is missing."""
    if not timestamp:
        return None
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (now - timestamp).total_seconds() / 3600.0


def detect_hook_errors(
    transcript_path: Path | None,
    terminal_id: str = "",
    session_id: str = "",
    git_sha: str | None = None,
) -> list[Finding]:
    """Scan transcript for hook execution errors.

    Reads raw JSONL to find attachment entries with non-zero exit codes,
    filtering out intentional PreToolUse blocks.

    Returns:
        List of findings for genuine hook errors.
    """
    if not transcript_path or not transcript_path.exists():
        return []

    errors: list[dict[str, Any]] = []

    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                att = entry.get("attachment")
                if not isinstance(att, dict):
                    continue

                att_type = att.get("type", "")
                if "hook" not in att_type:
                    continue

                hook_name = att.get("hookName", "")
                exit_code = att.get("exitCode", 0)
                stderr = (att.get("stderr") or "").strip()

                # Skip intentional PreToolUse blocks
                if exit_code == 2 and any(
                    hook_name.startswith(p) for p in _BLOCKING_HOOK_PREFIXES
                ):
                    continue

                # Skip expected non-zero hooks
                if hook_name.lower() in _EXPECTED_NONZERO_HOOKS and exit_code == 2:
                    continue

                # Only flag actual errors (non-zero, non-2 exit codes)
                if exit_code not in (0, 2):
                    ts = _parse_entry_timestamp(entry)
                    errors.append({
                        "hook_name": hook_name,
                        "exit_code": exit_code,
                        "stderr": stderr[:300],
                        "type": att_type,
                        "duration_ms": att.get("durationMs"),
                        "timestamp": ts,
                        "age_hours": _age_hours(ts),
                    })
    except (OSError, PermissionError):
        return []

    if not errors:
        return []

    # Deduplicate by hook_name — keep the most recent error per hook
    seen_hooks: dict[str, dict[str, Any]] = {}
    for err in errors:
        seen_hooks[err["hook_name"]] = err

    findings: list[Finding] = []
    for idx, (hook_name, err) in enumerate(seen_hooks.items()):
        # Classify severity by hook type AND freshness:
        # - SessionStart errors are high (affect session setup) but only when live
        # - Stale errors (>= _STALE_HOOK_ERROR_HOURS old) are downgraded to low
        # - Live errors keep their default severity
        base_severity = "high" if "SessionStart" in hook_name else "medium"
        age_h = err.get("age_hours")
        if age_h is not None and age_h >= _STALE_HOOK_ERROR_HOURS:
            severity = "low"
            staleness_tag = f" (stale, ~{age_h:.0f}h old)"
        else:
            severity = base_severity
            staleness_tag = ""

        stderr_preview = err["stderr"][:150] if err["stderr"] else "no stderr output"
        ts_str = err["timestamp"].isoformat() if err.get("timestamp") else "unknown"
        findings.append(
            Finding(
                id=f"HOOK-{idx + 1:03d}",
                title=f"Hook error: {hook_name}{staleness_tag}",
                description=(
                    f"Hook '{hook_name}' exited with code {err['exit_code']} "
                    f"at {ts_str}{staleness_tag}. "
                    f"stderr: {stderr_preview}"
                ),
                source_type="detector",
                source_name="hook_health_detector",
                domain="quality",
                gap_type="runtime_error",
                severity=severity,
                evidence_level="verified",
                action="recover",
                priority=severity,
                scope="local",
                terminal_id=terminal_id,
                session_id=session_id,
                git_sha=git_sha,
                evidence=[
                    EvidenceRef(
                        kind="hook_error",
                        value=hook_name,
                        detail=(
                            f"exit_code={err['exit_code']}, "
                            f"timestamp={ts_str}, "
                            f"age_hours={age_h if age_h is not None else 'unknown'}, "
                            f"stderr={stderr_preview[:100]}"
                        ),
                    ),
                ],
            )
        )

    return findings
