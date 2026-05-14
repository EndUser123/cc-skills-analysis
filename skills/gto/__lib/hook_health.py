"""Hook health detector — scans transcript for hook execution errors.

Detects hook attachment entries with non-zero exit codes, indicating
hook failures that may have been silently suppressed (non-blocking errors).

What it detects:
- Hook executions with non-zero exit codes (errors, warnings)
- Hooks that consistently fail across sessions (via carryover)
- SessionStart hook failures that may affect session setup

What it does NOT detect:
- PreToolUse exit(2) blocks (these are intentional, not errors)
- Hook performance issues (that's a separate concern)
"""
from __future__ import annotations

import json
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
                    errors.append({
                        "hook_name": hook_name,
                        "exit_code": exit_code,
                        "stderr": stderr[:300],
                        "type": att_type,
                        "duration_ms": att.get("durationMs"),
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
        # Classify severity by hook type
        severity = "high" if "SessionStart" in hook_name else "medium"

        stderr_preview = err["stderr"][:150] if err["stderr"] else "no stderr output"
        findings.append(
            Finding(
                id=f"HOOK-{idx + 1:03d}",
                title=f"Hook error: {hook_name}",
                description=(
                    f"Hook '{hook_name}' exited with code {err['exit_code']}. "
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
                        detail=f"exit_code={err['exit_code']}, stderr={stderr_preview[:100]}",
                    ),
                ],
            )
        )

    return findings
