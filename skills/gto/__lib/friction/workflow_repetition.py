"""Workflow repetition detector — finds repeated commands in transcripts."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from ...models import EvidenceRef, Finding


def extract_bash_commands(transcript_path: Path) -> list[str]:
    """Extract Bash tool commands from transcript."""
    commands: list[str] = []
    
    if not transcript_path.exists():
        return commands

    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                if '"tool": "Bash"' in line or '"tool":"Bash"' in line:
                    cmd_match = re.search(r'"command":\s*"([^"]+)"', line)
                    if cmd_match:
                        commands.append(cmd_match.group(1))
    except (OSError, UnicodeDecodeError):
        pass
    
    return commands


def detect_workflow_repetition(
    transcript_path: Path,
    terminal_id: str,
    session_id: str,
    git_sha: str | None,
) -> list[Finding]:
    """Detect repeated commands that indicate automation opportunities."""
    findings: list[Finding] = []
    
    commands = extract_bash_commands(transcript_path)
    if not commands:
        return findings
    
    counts = Counter(commands)
    
    for cmd, count in counts.items():
        if count >= 3:
            findings.append(
                Finding(
                    id=f"FRIC-REP-{len(findings) + 1:03d}",
                    title=f"Repeated command: {cmd[:50]}",
                    description=f"Command run {count} times - candidate for automation",
                    source_type="detector",
                    source_name="workflow_repetition",
                    domain="friction",
                    gap_type="workflow_repetition",
                    severity="medium",
                    evidence_level="verified",
                    scope="session",
                    terminal_id=terminal_id,
                    session_id=session_id,
                    git_sha=git_sha,
                    evidence=[
                        EvidenceRef(
                            kind="command",
                            value=cmd,
                            detail=f"count:{count}",
                        ),
                    ],
                    metadata={"command": cmd, "count": count},
                )
            )
    
    return findings
