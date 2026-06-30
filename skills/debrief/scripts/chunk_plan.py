#!/usr/bin/env python3
"""debrief Phase 1 — chunk plan + theme-hint grep.

Two operations in one tool so the debriefer doesn't have to count and divide:

  1. Decide whether the source needs chunking, and if so, produce N equal
     line ranges to dispatch to parallel Explore subagents. Caps N at 6 to
     keep the token cost bounded (per SKILL.md Phase 1 rule).

  2. Surface the transcript's "center of gravity" *before* extraction:
     keyword counts for the eight themes that nearly every transcript hits
     (ingestion, tooling, friction, state, handoff, transcript, gate, daemon).
     The debriefer uses these as the grouping hint that Phase 2 needs —
     grouping by theme is easier if the themes are obvious from the start.

Usage:
  python chunk_plan.py --path "C:/Users/brsth/transcript.txt"
  python chunk_plan.py --path "..." --json       # machine-readable
  python chunk_plan.py --selfcheck
"""
import argparse, json, os, re, sys

# Phase 1 rule from SKILL.md: ~2000 lines per chunk, cap N at 6.
TARGET_LINES_PER_CHUNK = 2000
MAX_CHUNKS = 6
SINGLE_READ_KB = 250  # ~250 KB fits one Read.

THEMES = {
    "ingestion":  r"\b(ingest|ingestion|reindex|backfill)\w*",
    "tooling":    r"\b(hook|router|dispatch|skill|plugin)\w*",
    "friction":   r"\b(friction|stuck|hang|silent|broken|wrong|crash)\w*",
    "state":      r"\b(state|db|database|ledger|schema|table)\w*",
    "handoff":    r"\b(handoff|snapshot|resume|restore|precompact)\w*",
    "transcript": r"\b(transcript|jsonl|history\.jsonl)\w*",
    "gate":       r"\b(gate|blocking|deny|denied|rejected)\w*",
    "daemon":     r"\b(daemon|server|bgtask|cron)\w*",
}


def _size_bytes(path: str) -> int:
    return os.path.getsize(path)


def _count_lines(path: str) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def plan_chunks(total_lines: int, file_bytes: int) -> dict:
    """Decide chunk count + ranges. Returns dict for JSON output."""
    if file_bytes <= SINGLE_READ_KB * 1024:
        return {
            "mode": "single-read",
            "reason": f"{file_bytes} bytes <= {SINGLE_READ_KB} KB threshold",
            "chunks": [{"start": 1, "end": total_lines, "label": "whole-file"}],
        }
    # Need chunking.
    chunk_count = max(1, min(MAX_CHUNKS, (total_lines + TARGET_LINES_PER_CHUNK - 1) // TARGET_LINES_PER_CHUNK))
    base = total_lines // chunk_count
    extra = total_lines - base * chunk_count
    chunks, cur = [], 1
    for i in range(chunk_count):
        span = base + (1 if i < extra else 0)
        chunks.append({"start": cur, "end": cur + span - 1,
                       "label": f"chunk-{i+1}-of-{chunk_count}"})
        cur += span
    return {
        "mode": "parallel-chunk",
        "reason": (f"{total_lines} lines / {file_bytes} bytes > threshold; "
                   f"{chunk_count} chunks (target {TARGET_LINES_PER_CHUNK}/chunk, cap {MAX_CHUNKS})"),
        "chunks": chunks,
    }


def theme_hints(path: str) -> dict:
    """Keyword count per theme; surfaces the center of gravity."""
    # Stream the file rather than slurp — transcripts can be hundreds of MB.
    counts = {t: 0 for t in THEMES}
    pats = {t: re.compile(p, re.I) for t, p in THEMES.items()}
    # Line buffer (transcript lines are short; 1 MB chunks are plenty).
    BUF = 1 << 20
    total_lines = 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(BUF)
            if not buf:
                break
            text = buf.decode("utf-8", errors="replace")
            total_lines += text.count("\n")
            for theme, pat in pats.items():
                counts[theme] += len(pat.findall(text))
    return {"lines_scanned": total_lines, "theme_counts": counts,
            "top_themes": sorted(counts, key=counts.get, reverse=True)[:3]}


def _selfcheck() -> None:
    # plan_chunks: single-read threshold
    p = plan_chunks(500, 50_000)
    assert p["mode"] == "single-read", p
    assert p["chunks"][0]["start"] == 1 and p["chunks"][0]["end"] == 500
    # plan_chunks: chunks within cap
    p = plan_chunks(9_000, 500_000)
    assert p["mode"] == "parallel-chunk"
    assert 1 <= len(p["chunks"]) <= MAX_CHUNKS
    # cap kicks in at MAX_CHUNKS * TARGET_LINES_PER_CHUNK = 12000
    p = plan_chunks(50_000, 5_000_000)
    assert len(p["chunks"]) == MAX_CHUNKS, p
    # chunks are contiguous + cover everything
    p = plan_chunks(9_500, 500_000)
    cur = 1
    for c in p["chunks"]:
        assert c["start"] == cur, c
        cur = c["end"] + 1
    assert cur - 1 == 9_500
    # theme_hints: fixtures
    with open(os.devnull, "w") as _:
        pass  # noop, just ensure file ops exist
    # round-trip the real session file if it exists (else skip)
    rt = (r"C:\Users\brsth\Downloads"
          r"\✳ Review npm version file content.txt")
    if os.path.exists(rt):
        h = theme_hints(rt)
        assert h["lines_scanned"] > 0
        assert sum(h["theme_counts"].values()) > 0
    print("self-check OK")


def main():
    ap = argparse.ArgumentParser(description="debrief Phase 1 chunk plan + theme hint")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--path", help="transcript path")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return 0
    if not args.path:
        ap.error("--path is required (or --selfcheck)")
    assert os.path.exists(args.path), f"missing: {args.path}"

    total_lines = _count_lines(args.path)
    file_bytes = _size_bytes(args.path)
    plan = plan_chunks(total_lines, file_bytes)
    hints = theme_hints(args.path)
    out = {"source": args.path, "total_lines": total_lines,
           "bytes": file_bytes, "plan": plan, "theme_hints": hints}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"source:    {args.path}")
        print(f"size:      {file_bytes:,} bytes / {total_lines:,} lines")
        print(f"plan.mode: {plan['mode']}  ({plan['reason']})")
        for c in plan["chunks"]:
            print(f"  - {c['label']}: lines {c['start']}–{c['end']}")
        print(f"theme_hints (top 3 first):")
        for t in hints["top_themes"]:
            print(f"  - {t}: {hints['theme_counts'][t]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())