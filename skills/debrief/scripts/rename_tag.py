#!/usr/bin/env python3
"""debrief Phase 6 — deterministic source-file rename (house style).

House naming standard (codified 2026-07-01):
    <session-start-date> [<Domain #id #id · domain #id>].ext

The export tool's auto-generated stem (timestamps, "cusersbrsthdownloads...",
"review npm version file", etc.) is garbage and is NEVER kept. The only
prefix is the session-start date, pulled from the transcript content (the
earliest real in-session event timestamp — NOT the export-tool timestamp and
NOT a date quoted inside a recap/template). Pass it via --date; it becomes
the stem. If --date is omitted the stem falls back to bracket-only.

Bracket = domain/feature themes only. Rules:
  - theme label is a short topic (CHS, pi, go, gate, plugin-audit, opportunity);
    acronyms UPPERCASE, else lowercase.
  - IDs grouped under their real topic; each ID appears exactly once.
  - NO meta / self-referential themes (debrief-skill, breadcrumb). The
    breadcrumb lives in the task tracker, not the filename.
  - themes joined by " · ".

Usage:
  # dry-run: show the name that WOULD result
  python rename_tag.py --date 2026-07-01 --themes "CHS:917,918 pi:914 gate:942" \
      --path "C:/Users/brsth/Downloads/2026-07-01-145732-...garbage....txt"

  # actually rename
  python rename_tag.py --themes "..." --path "..." --apply

  # self-check (no framework, exits non-zero on failure)
  python rename_tag.py --selfcheck
"""
import argparse, os, re, sys

# Stems that are almost certainly auto-generated / throwaway export titles.
# Bracket-only is safe for these. Everything else keeps the stem as a prefix.
NOISE_PATTERNS = [
    r"^claude(\b|\d|$)",     # claude, claude1, claude-router
    r"^review\b",
    r"^session\b",
    r"^temp\b",
    r"^chat\b",
    r"^export\b",
    r"^✳\s",                 # ✳-prefixed throwaway exports
    r"^[0-9a-f]{8,}$",       # pure hex / session hash
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.I)

FORBIDDEN = set('\\/:*?"<>|')


def is_noise_name(stem: str) -> bool:
    return bool(NOISE_RE.search(stem.strip()))


def format_tag(themes):
    """themes = [(label, [ids]), ...] -> 'chs #917 #918 · pi #914'."""
    parts = []
    for label, ids in themes:
        if not ids:
            continue
        parts.append(f"{label} " + " ".join(f"#{i}" for i in ids))
    return " · ".join(parts)


def build_name(stem: str, ext: str, themes) -> str:
    tag = format_tag(themes)
    if not tag:
        return f"{stem}{ext}"
    if is_noise_name(stem):
        return f"[{tag}]{ext}"
    return f"{stem} [{tag}]{ext}"


def validate(name: str) -> None:
    bad = set(c for c in name if c in FORBIDDEN)
    assert not bad, f"forbidden Windows filename chars in result: {bad}"


def _parse_themes(s: str):
    out = []
    for tok in s.split():
        if ":" not in tok:
            continue
        label, ids = tok.split(":", 1)
        out.append((label, [int(x) for x in ids.split(",") if x.strip()]))
    return out


def _selfcheck() -> None:
    # format_tag
    assert format_tag([("chs", [917, 918]), ("pi", [914])]) == "chs #917 #918 · pi #914"
    assert format_tag([("gate", [942])]) == "gate #942"
    assert format_tag([("x", [])]) == ""  # empty theme drops out
    # is_noise_name
    assert is_noise_name("claude") is True
    assert is_noise_name("Review npm version file content") is True
    assert is_noise_name("✳ something") is True
    assert is_noise_name("0a1b2c3d4e5f6a7b") is True
    assert is_noise_name("auth-refactor") is False
    assert is_noise_name("snapshot-handoff-design") is False
    # build_name
    assert build_name("Review npm", ".txt", [("chs", [917, 918])]) == "[chs #917 #918].txt"
    assert build_name("auth-refactor", ".jsonl", [("chs", [917])]) == "auth-refactor [chs #917].jsonl"
    assert build_name("auth", ".txt", []) == "auth.txt"
    # validate rejects forbidden chars
    try:
        validate("bad: name.txt")
        raise AssertionError("validate should have rejected ':'")
    except AssertionError as e:
        assert "forbidden" in str(e), str(e)
    # round-trip the actual session rename
    themes = [("chs", [917, 918]), ("pi", [914]), ("go", [916, 939]),
              ("gate", [942, 943, 944, 945])]
    got = build_name("✳ Review npm version file content", ".txt", themes)
    assert got == "[chs #917 #918 · pi #914 · go #916 #939 · gate #942 #943 #944 #945].txt", got
    # house standard (codified 2026-07-01): <session-start-date> [domain themes].ext
    assert build_name("2026-07-01", ".txt", [("CHS", [917]), ("plugin-audit", [982])]) \
        == "2026-07-01 [CHS #917 · plugin-audit #982].txt"
    print("self-check OK")


def main():
    ap = argparse.ArgumentParser(description="debrief Phase 6 rename formatter")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--date", default="",
                    help="session-start date (YYYY-MM-DD) pulled from transcript content; "
                         "becomes the stem, replacing the export tool's garbage prefix")
    ap.add_argument("--stem", default="",
                    help="override stem explicitly (rare; prefer --date)")
    ap.add_argument("--ext", default=".txt")
    ap.add_argument("--themes", help='"CHS:917,918 pi:914 gate:942,943"  (whitespace-separated)')
    ap.add_argument("--path", help="existing file to rename")
    ap.add_argument("--apply", action="store_true", help="actually rename (default: dry-run)")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return 0

    if not args.themes:
        ap.error("--themes is required (or --selfcheck)")
    themes = _parse_themes(args.themes)
    # --date wins (house standard: session-start date is the only allowed prefix;
    # it replaces the export tool's garbage stem). Then explicit --stem. Then the
    # path basename — which for export garbage should be treated as noise, so the
    # result is bracket-only.
    if args.date:
        stem = args.date
    elif args.stem:
        stem = args.stem
    elif args.path:
        stem = os.path.splitext(os.path.basename(args.path))[0]
    else:
        stem = ""
    if args.path:
        ext = os.path.splitext(args.path)[1] or args.ext
    else:
        ext = args.ext if args.ext.startswith(".") else f".{args.ext}"
    new = build_name(stem, ext, themes)
    validate(new)

    if args.path and args.apply:
        assert os.path.exists(args.path), f"missing source: {args.path}"
        dst = os.path.join(os.path.dirname(os.path.abspath(args.path)), new)
        assert not os.path.exists(dst), f"dest already exists: {dst}"
        os.rename(args.path, dst)
        print(f"renamed -> {dst}")
    else:
        kind = "NOISE (bracket-only)" if is_noise_name(stem) else "SIGNAL (prefix kept)"
        print(f"[{kind}]\n  {stem or '(none)'}{ext}\n  -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
