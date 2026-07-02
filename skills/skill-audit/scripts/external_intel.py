#!/usr/bin/env python3
"""external_intel.py - detect skills referenced in an artifact and map to internal skills.

Inputs: one or more artifact paths.
  - .jsonl            -> Claude Code transcript; walk tool_use Skill blocks + slash commands
  - SKILL.md / .md    -> treat the file itself as one external skill
  - dir               -> walk for every SKILL.md beneath it
  - .log / .txt / *   -> free text; grep slash commands and SKILL.md path mentions

Output: JSON manifest on stdout. The LLM then runs the qualitative diff against
the matched internal skills (see references/external-intel-rubric.md) and emits
actionable hand-offs, e.g.  -> run `/skill-audit improve <internal-path>`.

Usage:
  python external_intel.py <artifact> [<artifact> ...]
  python external_intel.py selfcheck
"""
from __future__ import annotations
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO = Path("P:/packages/.claude-marketplace/plugins")
# /name with optional :namespace, lowercase-only so Windows drive tails (/Users) reject.
# Lookbehind rejects: word char, '/', and '<' (so XML close-tags like </promise> don't match).
SLASH_CMD = re.compile(r"(?<![<\w/])/([a-z][a-z0-9-]+(?::[a-z0-9-]+)?)\b")
SKILL_PATH = re.compile(r"skills/([a-z][a-z0-9-]+)/SKILL\.md", re.IGNORECASE)


def iter_internal_skills() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not REPO.exists():
        return out
    for sk in REPO.glob("*/skills/*/SKILL.md"):
        name = sk.parent.name
        desc = ""
        try:
            text = sk.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^description:\s*(.+?)(?:\n[a-z_-]+:|\Z)", text, re.S | re.M)
            if m:
                desc = m.group(1).strip()[:400]
        except OSError:
            pass
        out.append({"name": name, "path": str(sk).replace("\\", "/"), "desc": desc})
    return out


def parse_jsonl(path: str) -> Iterable[Tuple[int, Any]]:
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except json.JSONDecodeError:
                continue


def _content_blocks(rec: Any) -> List[Any]:
    msg = rec.get("message") if isinstance(rec, dict) else None
    if isinstance(msg, dict):
        c = msg.get("content")
    else:
        c = rec.get("content") if isinstance(rec, dict) else None
    return c if isinstance(c, list) else []


def _add(found: Dict[str, Dict[str, Any]], name: str, cite: str) -> None:
    slot = found.setdefault(name, {"count": 0, "citations": []})
    slot["count"] += 1
    if len(slot["citations"]) < 5:
        slot["citations"].append(cite)


def _role_of(rec: Any) -> str:
    msg = rec.get("message") if isinstance(rec, dict) else None
    if isinstance(msg, dict):
        return str(msg.get("role", "")).lower()
    return ""


def detect_from_transcript(path: str) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    for i, rec in parse_jsonl(path):
        role = _role_of(rec)
        for b in _content_blocks(rec):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == "Skill":
                # Structured invocation — authoritative regardless of role.
                nm = (b.get("input") or {}).get("skill")
                if nm:
                    _add(found, nm, f"{path}:{i}")
            elif b.get("type") == "text" and role == "user":
                # Prose slash-scan is noisy on assistant output (paths, XML, doc text);
                # only trust slash commands the user typed.
                for m in SLASH_CMD.finditer(b.get("text", "")):
                    _add(found, m.group(1), f"{path}:{i}")
    return found


def detect_from_text(path: str) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for m in SKILL_PATH.finditer(text):
        _add(found, m.group(1).lower(), f"{path}:path")
    for m in SLASH_CMD.finditer(text):
        _add(found, m.group(1), f"{path}:slash")
    return found


def detect_from_skillmd(path: str) -> Dict[str, Dict[str, Any]]:
    p = Path(path)
    name = p.parent.name if p.name.lower() == "skill.md" else p.stem
    return {name: {"count": 1, "citations": [path], "source": "skill-file"}}


def classify(path: str) -> Tuple[str, str]:
    p = Path(path)
    if p.is_dir():
        sk = p / "SKILL.md"
        return ("skillmd", str(sk)) if sk.exists() else ("dir", str(p))
    lower = p.name.lower()
    if lower.endswith(".jsonl"):
        return "transcript", path
    if lower == "skill.md" or lower.endswith(".md"):
        return "skillmd", path
    return "text", path


def detect(path: str) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    kind, p = classify(path)
    if kind == "transcript":
        return kind, detect_from_transcript(p)
    if kind == "skillmd":
        return kind, detect_from_skillmd(p)
    if kind == "text":
        return kind, detect_from_text(p)
    if kind == "dir":
        out: Dict[str, Dict[str, Any]] = {}
        for sk in Path(p).rglob("SKILL.md"):
            for k, v in detect_from_skillmd(str(sk)).items():
                out[k] = v
        return kind, out
    return "unknown", {}


_INTERNAL: List[Dict[str, str]] = []


def _internal() -> List[Dict[str, str]]:
    global _INTERNAL
    if not _INTERNAL:
        _INTERNAL = iter_internal_skills()
    return _INTERNAL


def map_internal(ext_name: str) -> Dict[str, Any]:
    intl = _internal()
    if not intl:
        return {"internal": None, "path": None, "confidence": 0.0, "match_basis": "no-internal-index"}

    def score(item: Dict[str, str]) -> float:
        # Token-level, not char-level: char SequenceMatcher lets a shared suffix
        # (-review) swamp the rest and false-match "code-review" -> "adv-review".
        et = set(re.findall(r"[a-z0-9]+", ext_name.lower()))
        it = set(re.findall(r"[a-z0-9]+", item["name"].lower()))
        if et and it:
            nj = len(et & it) / len(et | it)
        else:
            nj = SequenceMatcher(None, ext_name.lower(), item["name"].lower()).ratio()
        dt = set(re.findall(r"[a-z0-9]+", item["desc"].lower())) if item["desc"] else set()
        overlap = len(et & dt) / (len(et) + 1) if et else 0.0
        return max(nj, 0.5 * nj + 0.5 * overlap)

    best = max(intl, key=score)
    s = score(best)
    basis = "name" if s > 0.7 else ("keyword" if s > 0.35 else "none")
    if s <= 0.35:
        return {"internal": None, "path": None, "confidence": round(s, 2), "match_basis": basis}
    return {"internal": best["name"], "path": best["path"], "confidence": round(s, 2), "match_basis": basis}


def run(paths: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"artifacts": [], "external_skills": []}
    agg: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        kind, found = detect(path)
        out["artifacts"].append({"path": path, "kind": kind, "signals": len(found)})
        for name, info in found.items():
            slot = agg.setdefault(
                name, {"name": name, "invocations": 0, "citations": [], "sources": []}
            )
            slot["invocations"] += info["count"]
            slot["citations"].extend(info["citations"][:5])
            if kind not in slot["sources"]:
                slot["sources"].append(kind)
    for name, slot in sorted(agg.items(), key=lambda kv: -kv[1]["invocations"]):
        slot["internal_match"] = map_internal(name)
        out["external_skills"].append(slot)
    return out


def _selfcheck() -> None:
    import tempfile

    sample = [
        {"message": {"role": "user", "content": [{"type": "text", "text": "run /tdd then /ship"}]}},
        {"message": {"role": "assistant",
                      "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "code-review"}}]}},
        {"message": {"role": "user", "content": [{"type": "text", "text": "see C:/Users/x and file:///p/q"}]}},
    ]
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in sample))
    res = run([p])
    names = {s["name"] for s in res["external_skills"]}
    assert "code-review" in names, f"Skill tool_use not detected: {names}"
    assert "tdd" in names and "ship" in names, f"slash not detected: {names}"
    # drive-letter tails must NOT register
    assert "Users" not in names and "p" not in names, f"path false positive: {names}"
    # no internal code-review skill exists; matcher must not produce a false-STRONG
    # match (the bug was char-ratio code-review -> adv-review at 0.76). A weak
    # keyword-tier candidate (e.g. -> code at ~0.5) is acceptable; it's labelled
    # for the LLM to discount.
    cr = next(s for s in res["external_skills"] if s["name"] == "code-review")
    im = cr["internal_match"]
    assert im["confidence"] < 0.6 and im["match_basis"] != "name", im
    print("selfcheck OK:", sorted(names), "-> code-review weakly matched (", im, ")")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    if args[0] == "selfcheck":
        _selfcheck()
        sys.exit(0)
    print(json.dumps(run(args), indent=2))
