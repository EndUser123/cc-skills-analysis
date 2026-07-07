#!/usr/bin/env python3
"""prune_scan.py - mechanical scaffold for the `prune` subcommand of /skill-audit.

SCAN ONLY. Never moves or deletes a skill. Emits JSON candidate lists so the LLM
(or user) can review before any archival. This mirrors /similarity's "does NOT
delete, hands to review" discipline and user memory #1005 ("don't auto-clean,
confirm first"). Archival is a manual, reviewed step documented in the skill body.

Signals:
  retire          — stub/deprecated/TODO/empty-body marker in the description
  merge           — high name+description token overlap with a sibling skill (dedupe)
  review_primitive — single-tool wrapper (reuses primitive_smells.analyze)

Usage:
  python prune_scan.py <plugin-name|skill-dir|all>
  python prune_scan.py selfcheck
"""
from __future__ import annotations
import importlib.util, json, re, sys
from pathlib import Path
from typing import Any

REPO = Path("P:/packages/.claude-marketplace/plugins")

# Reuse the sibling primitive_smells analyzer (single-tool-wrapper detection).
_spec = importlib.util.spec_from_file_location(
    "_primitive_smells", Path(__file__).parent / "primitive_smells.py")
_PS = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
assert _spec.loader is not None
_spec.loader.exec_module(_PS)

_STUB_MARKERS = ("deprecated", "deprecation", "stub", "todo", "unimplemented",
                 "parked", "dead", "no longer")
_STOP = {"the", "and", "for", "with", "from", "that", "this", "your", "skill",
         "using", "use", "uses", "when", "via", "into", "skill", "code", "claude"}
_TOKEN = re.compile(r"[a-z][a-z0-9]+")


def _desc(text: str) -> str:
    # Stop at the next frontmatter field OR the closing ``---`` (so a minimal
    # frontmatter of just name+description doesn't bleed into the body).
    m = re.search(r"^description:\s*(.+?)(?:\n[a-z_-]+:|\n---|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def _tokens(s: str) -> set[str]:
    return {t for t in _TOKEN.findall(s.lower()) if len(t) > 2} - _STOP


def _plugin_of(sk: Path) -> str:
    parts = [p.lower() for p in sk.parts]
    if "plugins" in parts:
        i = parts.index("plugins")
        if i + 1 < len(sk.parts):
            return sk.parts[i + 1]
    return "?"


def _skill_paths(target: str) -> list[Path]:
    if target in ("all", "."):
        return list(REPO.glob("*/skills/*/SKILL.md"))
    if (REPO / target / "skills").is_dir():
        return list((REPO / target / "skills").glob("*/SKILL.md"))
    p = Path(target)
    if p.is_dir():
        return list(p.rglob("SKILL.md"))
    return [p] if p.name.lower() == "skill.md" else []


def scan(target: str) -> dict[str, Any]:
    retire: list[dict[str, Any]] = []
    review_primitive: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []
    for sk in _skill_paths(target):
        try:
            text = sk.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = sk.parent.name
        desc = _desc(text)
        body = text.split("---", 2)[-1]
        stub_reason = next((m for m in _STUB_MARKERS if m in desc.lower()), None)
        is_empty = len(body.strip()) < 80
        path = str(sk).replace("\\", "/")
        meta.append({"name": name, "plugin": _plugin_of(sk), "path": path,
                     "desc": desc[:140], "tokens": sorted(_tokens(f"{name} {desc}"))})
        if stub_reason or is_empty:
            retire.append({"skill": name, "plugin": _plugin_of(sk), "path": path,
                           "reason": stub_reason or "empty-body",
                           "desc": desc[:140]})
            continue  # a stub is not also a wrapper candidate
        a = _PS.analyze(sk)
        if a and a.get("is_wrapper"):
            review_primitive.append({"skill": name, "plugin": _plugin_of(sk),
                                     "path": path, "primary_tool": a["primary_tool"]})

    merge: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, x in enumerate(meta):
        tx = set(x["tokens"])
        if not tx:
            continue
        for y in meta[i + 1:]:
            if x["name"] == y["name"]:
                continue
            pair = tuple(sorted([x["name"], y["name"]]))
            if pair in seen:
                continue
            ty = set(y["tokens"])
            inter, uni = len(tx & ty), len(tx | ty)
            # inter>=3 bounds precision; jaccard 0.4 catches word-form variance
            # (transcript/transcripts). Merge is advisory-only, never auto-applied.
            if uni and inter / uni >= 0.4 and inter >= 3:
                merge.append({"a": x["name"], "b": y["name"],
                              "a_plugin": x["plugin"], "b_plugin": y["plugin"],
                              "jaccard": round(inter / uni, 2),
                              "shared": sorted(tx & ty)[:6]})
                seen.add(pair)

    return {"target": target, "total_scanned": len(meta),
            "retire": retire, "merge": merge, "review_primitive": review_primitive}


def _selfcheck() -> None:
    import tempfile
    d = Path(tempfile.mkdtemp())
    plug = d / "plugins" / "cc-test" / "skills"
    (plug / "transcribe-youtube").mkdir(parents=True)
    (plug / "transcribe-youtube" / "SKILL.md").write_text(
        "---\nname: transcribe-youtube\ndescription: extract youtube transcripts\n---\n"
        "# transcribe-youtube\nThis skill extracts transcripts from YouTube videos via the "
        "batch notebook workflow. Real body content, multiple sentences, well above the "
        "empty-body threshold so it must not be flagged as a stub or retire candidate.\n",
        encoding="utf-8")
    (plug / "yt-transcriber").mkdir(parents=True)
    (plug / "yt-transcriber" / "SKILL.md").write_text(
        "---\nname: yt-transcriber\ndescription: extract youtube transcripts\n---\n"
        "# yt-transcriber\nA second skill that also extracts YouTube transcripts, intentionally "
        "named and described to overlap with transcribe-youtube so the dedupe signal fires. "
        "Body is long enough to clear the empty-body threshold.\n",
        encoding="utf-8")
    (plug / "old-thing").mkdir(parents=True)
    (plug / "old-thing" / "SKILL.md").write_text(
        "---\nname: old-thing\ndescription: DEPRECATED stub\n---\n# z\nshort\n", encoding="utf-8")
    # Point REPO at the temp plugins dir for this run.
    global REPO
    REPO = d / "plugins"
    res = scan("cc-test")
    retire_names = {r["skill"] for r in res["retire"]}
    assert "old-thing" in retire_names and "transcribe-youtube" not in retire_names, res["retire"]
    pairs = {(m["a"], m["b"]) for m in res["merge"]}
    assert any("transcribe-youtube" in p and "yt-transcriber" in p for p in pairs), res["merge"]
    print(f"selfcheck OK: {len(res['retire'])} retire, {len(res['merge'])} merge, "
          f"{len(res['review_primitive'])} primitive-review")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    if args[0] == "selfcheck":
        _selfcheck(); sys.exit(0)
    print(json.dumps(scan(args[0]), indent=2))
