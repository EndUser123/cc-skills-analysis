"""Mechanical scaffold for the capability-preservation check.

Reads a skill directory and reports the structurally-determinable facts the
reviewer needs before applying the judgment rubric in
references/capability-preservation-check.md:

  - frontmatter (name, workflow_steps, description, status, enforcement)
  - whether the skill carries a deprecation / redirect marker
  - referenced backend files (__lib/, scripts/, runner.py, calibrate.py,
    harness_registry.py) and whether each exists on disk
  - a coarse "thin-stub" structural signal (empty workflow_steps AND a body
    that is essentially a redirect notice)

This script does NOT classify. It emits facts; classification is a judgment
the reviewer applies after reading the full source.

Usage:
    python capability_preservation.py <skill-dir> [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEPRECATION_RX = re.compile(r"\b(DEPRECATED|deprecation stub|use /\w+)\b", re.IGNORECASE)
_BACKEND_TOKENS = ("runner.py", "calibrate.py", "harness_registry.py", "__lib/", "scripts/")
_FENCE_RX = re.compile(r"```.*?```", re.DOTALL)


def _parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4:]
    fm = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def _backend_existence(skill_dir, body):
    prose = _FENCE_RX.sub("", body)
    report = {}
    for token in _BACKEND_TOKENS:
        if token not in prose:
            continue
        candidate = skill_dir / token.rstrip("/")
        report[token] = {
            "mentioned": True,
            "exists": candidate.exists(),
            "path": str(candidate),
        }
    return report


def _is_thin_stub_structural(fm, body):
    ws = fm.get("workflow_steps", "")
    steps_empty = ws in ("", "[]")
    prose = re.sub(r"^#.*$", "", _FENCE_RX.sub("", body), flags=re.MULTILINE)
    prose = re.sub(r"\s+", " ", prose).strip()
    return steps_empty and len(prose) < 400


def analyze(skill_dir):
    skill_md = Path(skill_dir) / "SKILL.md"
    if not skill_md.exists():
        return {"skill_dir": str(skill_dir), "error": "SKILL.md not found"}
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(text)
    deprecation = sorted({m.group(1).lower() for m in _DEPRECATION_RX.finditer(body)})
    return {
        "skill_dir": str(skill_dir),
        "name": fm.get("name"),
        "workflow_steps_raw": fm.get("workflow_steps"),
        "description": fm.get("description"),
        "status": fm.get("status"),
        "enforcement": fm.get("enforcement"),
        "deprecation_markers": deprecation,
        "thin_stub_structural_signal": _is_thin_stub_structural(fm, body),
        "referenced_backends": _backend_existence(Path(skill_dir), body),
        "py_files_on_disk": sorted(
            p.relative_to(skill_dir).as_posix()
            for p in Path(skill_dir).glob("**/*.py")
            if not p.relative_to(skill_dir).as_posix().startswith("tests/")
        ),
        "note": "Mechanical facts only. Apply the classification rubric in "
                "references/capability-preservation-check.md to classify.",
    }


def _main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("skill_dir", type=Path)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()
    report = analyze(args.skill_dir)
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        for k, v in report.items():
            print("== %s ==" % k)
            print("   %s" % v)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
