"""Shared transcript reader handling all Claude Code JSONL formats.

Claude Code stores transcripts in three formats:
- Simple: {"role": "user", "content": "text"}
- Old:    {"sender": "user", "text": "text"} or {"sender": "user", "content": "text"}
- New:    {"type": "user", "message": {"content": "text" | [{"type":"text","text":"..."}]}}

All 6 transcript-reading call sites in GTO previously used only the simple format.
This module handles all three, adapted from RNS chain.py.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TranscriptTurn:
    role: str  # "user" | "assistant"
    content: str
    turn_number: int  # 1-based line number in JSONL


def read_turns(
    transcript_path: Path,
    *,
    max_age_days: int | None = None,
) -> list[TranscriptTurn]:
    """Read transcript JSONL handling all Claude Code formats.

    Args:
        transcript_path: Path to transcript JSONL file.
        max_age_days: If set, skip files older than this many days.

    Returns:
        List of TranscriptTurn with role, content, and 1-based turn_number.
    """
    if not transcript_path.exists():
        return []

    if max_age_days is not None:
        try:
            mtime = os.path.getmtime(transcript_path)
            age_days = (datetime.now(timezone.utc).timestamp() - mtime) / 86400
            if age_days > max_age_days:
                return []
        except OSError:
            return []

    turns: list[TranscriptTurn] = []
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, start=1):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role, content = _extract_role_content(entry)
                if role and content:
                    turns.append(TranscriptTurn(
                        role=role,
                        content=content,
                        turn_number=line_num,
                    ))
    except (OSError, PermissionError):
        pass

    return turns


def _extract_role_content(entry: dict) -> tuple[str | None, str]:
    """Extract (role, content) from a single JSONL entry.

    Returns (None, "") for non-message entries (system, tool_use, etc).
    """
    # New format: {"type": "user"|"assistant", "message": {"content": ...}}
    etype = entry.get("type", "")
    if etype in ("user", "assistant"):
        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            return None, ""
        raw = msg.get("content", "")
        text = _flatten_content(raw)
        return etype, text

    # Old format: {"sender": "user"|"assistant", "text": "..."}
    sender = entry.get("sender", "")
    if sender in ("user", "assistant"):
        text = entry.get("text", "") or entry.get("content", "")
        if isinstance(text, list):
            text = _flatten_content(text)
        return sender, str(text)

    # Simple format: {"role": "user"|"assistant", "content": "..."}
    role = entry.get("role", "")
    if role in ("user", "assistant"):
        raw = entry.get("content", "")
        text = _flatten_content(raw)
        return role, text

    return None, ""


def _flatten_content(raw: str | list) -> str:
    """Flatten content that may be a string or list of content blocks."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return " ".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(raw) if raw else ""


_FILE_EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def extract_edited_files(transcript_path: Path, root: Path | None = None) -> list[Path]:
    """Extract unique file paths from Edit/Write/NotebookEdit tool calls in a transcript.

    Scans assistant turns for tool_use blocks targeting file-editing tools,
    returning deduplicated absolute paths. If root is given, only files under
    root are included.

    Args:
        transcript_path: Path to transcript JSONL file.
        root: Optional project root to filter results.

    Returns:
        Deduplicated list of edited file paths, in order of first appearance.
    """
    if not transcript_path.exists():
        return []

    seen: set[str] = set()
    files: list[Path] = []

    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # New format: assistant message with content blocks
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if block.get("name") not in _FILE_EDIT_TOOLS:
                        continue
                    fp = (block.get("input") or {}).get("file_path", "")
                    if not fp or fp in seen:
                        continue
                    resolved = Path(fp).resolve()
                    if root is not None:
                        try:
                            resolved.relative_to(root)
                        except ValueError:
                            continue
                    seen.add(fp)
                    files.append(resolved)
    except (OSError, PermissionError):
        pass

    return files
