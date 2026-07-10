#!/usr/bin/env python3
"""Resolve the export file for a given session_id.

Used by /debrief when no --path is given. Finds an existing chain_*.md export
for the requested session_id (searching ~/.claude/exports/ then ~/Downloads/),
checks staleness against the live transcript mtime, and shells out to
chs_cli.py --export to create a fresh export when none exists or the existing
one is stale.

Frontmatter (session_id) is the authoritative match key. The **Root session:**
prose line is the legacy fallback for exports written before frontmatter
existed — i.e. any export produced before this commit ships.

The resolver requires --session_id explicitly. It does NOT auto-detect the
current session from a terminal-keyed file; that path is unsafe under
concurrent Claude sessions in one Windows Terminal. The invoker (the LLM)
derives session_id from the live transcript_path per the /recap SKILL.md rule
and passes it here.

Stdlib-only. Pure functions (parse_export_session_id, find_export, is_stale)
have unit tests in tests/test_resolve_export.py.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


CHS_CLI = Path("P:/packages/.claude-marketplace/plugins/search-research/skills/chs/scripts/chs_cli.py")
EXPORTS_DIR = Path.home() / ".claude" / "exports"
DOWNLOADS_DIR = Path.home() / "Downloads"
PROJECTS_DIR = Path.home() / ".claude" / "projects" / "P--"

# Authoritative: parse YAML frontmatter (--- ... ---) at the head of the file.
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SESSION_ID_KEY_RE = re.compile(r'^\s*session_id\s*:\s*"?([A-Za-z0-9._:-]+)"?\s*$', re.MULTILINE)

# Legacy fallback: exports written before frontmatter shipped used this prose line.
ROOT_SESSION_RE = re.compile(r"^\*\*Root session:\*\*\s*`?([A-Za-z0-9-]+)`?\s*$", re.MULTILINE)

# session_id matches: any non-empty run of safe characters. chs_cli accepts
# whatever string `--session-id` receives, so this validator only needs to
# reject shell-unsafe characters (spaces, slashes, quotes, backticks,
# semicolons, globs). Anything else — UUIDs, IC- ids, short slugs — passes.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def parse_export_session_id(path: Path, head_chars: int = 4000) -> str | None:
    """Return the session_id declared in an export, or None if unparseable.

    Frontmatter is authoritative. The **Root session:** prose line is the
    backward-compat fallback. Reads at most `head_chars` bytes (the header
    is always near the top; the transcript body is irrelevant to matching).
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read(head_chars)
    except OSError:
        return None

    m = FRONTMATTER_RE.match(text)
    if m:
        km = SESSION_ID_KEY_RE.search(m.group(1))
        if km:
            return km.group(1)

    rm = ROOT_SESSION_RE.search(text)
    if rm:
        return rm.group(1)

    return None


def find_export(session_id: str) -> Path | None:
    """Search exports dir (newest first) then Downloads, return the most-recent
    export whose declared session_id matches. Returns None if none found."""
    for d in (EXPORTS_DIR, DOWNLOADS_DIR):
        if not d.is_dir():
            continue
        # Most-recent first; this is the proxy for "best candidate" because
        # the parse step then confirms it.
        candidates = sorted(
            (p for p in d.glob("chain_*.md") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in candidates:
            sid = parse_export_session_id(p)
            if sid == session_id:
                return p
    return None


def is_stale(export_path: Path, session_id: str) -> bool:
    """Stale iff the live transcript was modified after the export file was
    written. Robust to frontmatter parsing failure (file mtime is the truth).

    Returns True when no live transcript exists (conservatively treat as stale
    so re-export rebuilds a known-good snapshot).
    """
    transcript = PROJECTS_DIR / f"{session_id}.jsonl"
    if not transcript.exists():
        return True
    export_mtime = export_path.stat().st_mtime
    transcript_mtime = transcript.stat().st_mtime
    return transcript_mtime > export_mtime


def _resolve_session_id_match(path: Path, session_id: str) -> bool:
    """Strict match: session_id is a UUID-like string and must equal the
    parsed export id exactly. Rejects partial/loose matches by construction."""
    return parse_export_session_id(path) == session_id


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Resolve the export file for a session_id (used by /debrief auto-input)."
    )
    p.add_argument(
        "--session-id",
        required=True,
        help="Session ID (derive from live transcript_path, never auto-detect).",
    )
    p.add_argument(
        "--no-export",
        action="store_true",
        help="Don't create a new export; just report the existing match (if any).",
    )
    p.add_argument(
        "--force-export",
        action="store_true",
        help="Skip staleness check and always re-export.",
    )
    args = p.parse_args(argv)

    # Sanity-check the session_id shape — reject obviously wrong input
    # rather than silently globbing against everything.
    if not SESSION_ID_RE.match(args.session_id):
        print(
            json.dumps(
                {"action": "invalid_session_id", "session_id": args.session_id}
            ),
            file=sys.stderr,
        )
        return 2

    existing = find_export(args.session_id)
    reused = existing is not None and not is_stale(existing, args.session_id)

    if reused and not args.force_export:
        print(
            json.dumps(
                {
                    "path": str(existing),
                    "session_id": args.session_id,
                    "action": "reused",
                    "stale": False,
                }
            )
        )
        return 0

    if args.no_export:
        action = "stale" if existing else "missing"
        print(
            json.dumps(
                {
                    "path": str(existing) if existing else None,
                    "session_id": args.session_id,
                    "action": action,
                    "stale": action == "stale",
                }
            )
        )
        return 0

    # (Re-)export. chs_cli.py --export writes to a default path and prints
    # JSON metadata to stdout (the "path" field is what we want).
    cmd = [sys.executable, str(CHS_CLI), "--export", "--session-id", args.session_id]
    if existing is not None:
        # Stale re-export: write to a deterministic overwrite target so the
        # glob finds it; otherwise the timestamp would just pile up siblings.
        cmd.extend(["--output", str(EXPORTS_DIR / f"chain_{args.session_id}_refresh.md")])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            json.dumps(
                {
                    "action": "export_failed",
                    "session_id": args.session_id,
                    "stderr": result.stderr.strip(),
                    "stdout": result.stdout.strip(),
                }
            ),
            file=sys.stderr,
        )
        return 1

    # Pull the path from chs_cli's JSON metadata (last non-empty line).
    new_path: Path | None = None
    for line in reversed(result.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                meta = json.loads(line)
                if "path" in meta:
                    new_path = Path(meta["path"])
                    break
            except json.JSONDecodeError:
                continue

    if new_path is None:
        # Fall back to the glob — a new file should be the most-recent match.
        new_path = find_export(args.session_id)

    if new_path is None:
        print(
            json.dumps(
                {"action": "export_completed_but_path_unknown", "stdout": result.stdout.strip()}
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "path": str(new_path),
                "session_id": args.session_id,
                "action": "exported",
                "stale": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())