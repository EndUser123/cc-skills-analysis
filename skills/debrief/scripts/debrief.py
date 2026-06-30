#!/usr/bin/env python3
"""debrief driver — the one entry point that unifies dry-run + live.

Reads the bundle (chunk_plan, extraction prompt, task template, rename
formatter), so a single CLI produces a deterministic, auditable run:

  python debrief.py --path "C:/Users/brsth/transcript.txt"   # dry-run
  python debrief.py --path "..." --apply                      # rename the file
  python debrief.py --path "... --path "..."                  # batch

The driver does NOT extract issues from the transcript itself — that
requires LLM judgment. It produces the *plan* a debriefer (or parallel
Explore subagents) executes: chunk ranges, extraction prompts, theme
hints, proposed rename target, BLOCKERS validity checks, and the
meta-task breadcrumb.

Modes:
  plan     — print chunk plan + extraction prompts + theme hints (default)
  render   — also print the proposed task templates + dependency graph
             from a JSON of proposed-tasks produced by the debriefer
             (see --proposed-tasks)
  validate — read an existing tracker snapshot (--existing-tasks) and
             check every BLOCKERS: #<id> reference resolves + warn on
             dangling / already-completed refs
  selfcheck — run --selfcheck on every script in scripts/

Usage:
  python debrief.py plan   --path "transcript.txt"
  python debrief.py render --path "transcript.txt" --proposed-tasks tasks.json
  python debrief.py validate --existing-tasks tasks.json --proposed-tasks tasks.json
  python debrief.py selfcheck
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
SKILL_DIR = HERE.parent  # skills/debrief

# ── helpers ────────────────────────────────────────────────────────────────
def _read_json(path: str) -> object:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_script(name: str) -> str:
    p = HERE / name
    assert p.exists(), f"missing sibling script: {p}"
    return str(p)


def _run_script(script: str, args: list) -> tuple:
    """Run a sibling script; return (returncode, stdout, stderr)."""
    p = subprocess.run([sys.executable, script, *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


# ── plan mode ──────────────────────────────────────────────────────────────
def mode_plan(paths: list, json_mode: bool) -> int:
    if not paths:
        print("error: --path required for plan mode", file=sys.stderr)
        return 2
    rc = 0
    for path in paths:
        if not os.path.exists(path):
            print(f"error: missing source: {path}", file=sys.stderr)
            rc = 1
            continue
        print(f"\n══════════════ {path} ══════════════")
        # chunk plan + theme hints
        cp = _resolve_script("chunk_plan.py")
        cprc, cpout, cperr = _run_script(cp, ["--path", path, "--json"])
        if cprc != 0:
            print(f"chunk_plan FAILED: {cperr}", file=sys.stderr)
            rc = cprc
            continue
        plan = json.loads(cpout)
        if json_mode:
            print(json.dumps(plan, indent=2))
            continue
        print(f"size: {plan['bytes']:,} bytes / {plan['total_lines']:,} lines")
        print(f"plan.mode: {plan['plan']['mode']}  ({plan['plan']['reason']})")
        for c in plan["plan"]["chunks"]:
            print(f"  - {c['label']}: lines {c['start']}–{c['end']}")
        print(f"theme_hints (top 3): {plan['theme_hints']['top_themes']}")
        print(f"  counts: {plan['theme_hints']['theme_counts']}")
        # extraction prompts (one per chunk)
        ep = (SKILL_DIR / "references" / "extraction_prompt.md").read_text(
            encoding="utf-8")
        # extract the prompt body between the leading '> ...' block
        body = ep.split("## The prompt", 1)[1] if "## The prompt" in ep else ""
        for c in plan["plan"]["chunks"]:
            print(f"\n────── extraction prompt for {c['label']} (lines {c['start']}–{c['end']}) ──────")
            print(body.strip()
                  .replace("<ABSOLUTE PATH>", path)
                  .replace("<START>", str(c["start"]))
                  .replace("<END>", str(c["end"])))
        # proposed rename (no IDs yet — emit a placeholder so the debriefer
        # can fill in themes after extraction).
        stem = Path(path).stem
        ext = Path(path).suffix or ".txt"
        print(f"\n────── rename target ──────")
        # detect noise vs signal the same way rename_tag does
        from rename_tag import is_noise_name, build_name  # type: ignore
        kind = "NOISE (bracket-only)" if is_noise_name(stem) else "SIGNAL (prefix kept)"
        print(f"[{kind}] {stem}{ext}")
        print(f"  example placeholder: {build_name(stem, ext, [('theme', [999])])}")
        print(f"  fill in the themes + real IDs after extraction, then:")
        print(f"    python rename_tag.py --themes \"<theme>:<id>,...\" --path \"{path}\"")
        print(f"    python rename_tag.py --themes \"<theme>:<id>,...\" --path \"{path}\" --apply")
    return rc


# ── validate mode ──────────────────────────────────────────────────────────
def mode_validate(existing_tasks_path: str, proposed_tasks_path: str) -> int:
    """Check every BLOCKERS: #<id> in proposed tasks against the live tracker snapshot."""
    if not existing_tasks_path or not proposed_tasks_path:
        print("error: --existing-tasks and --proposed-tasks required for validate",
              file=sys.stderr)
        return 2
    existing = _read_json(existing_tasks_path)
    if not isinstance(existing, list):
        # tolerate {"tasks": [...]} wrapper from some dumpers
        existing = existing.get("tasks", existing)
    existing_ids = {t["id"]: t for t in existing if "id" in t}
    completed_ids = {tid for tid, t in existing_ids.items()
                     if t.get("status") == "completed"}
    proposed = _read_json(proposed_tasks_path)
    if not isinstance(proposed, list):
        proposed = proposed.get("tasks", proposed)
    blockers_re = re.compile(r"BLOCKERS:\s*([^\n]+)")
    bad = 0
    for t in proposed:
        body = t.get("description", "")
        m = blockers_re.search(body)
        if not m:
            continue
        for tok in re.findall(r"#(\d+)", m.group(1)):
            tid = int(tok)
            if tid not in existing_ids:
                print(f"  WARN {t.get('subject','?')[:60]}: dangling # {tid}", file=sys.stderr)
                bad += 1
            elif tid in completed_ids:
                print(f"  WARN {t.get('subject','?')[:60]}: blocks on completed # {tid}",
                      file=sys.stderr)
                bad += 1
    if bad:
        print(f"\n{bad} BLOCKERS warnings", file=sys.stderr)
        return 3
    print(f"OK: all BLOCKERS refs resolve in the existing tracker snapshot.")
    return 0


# ── selfcheck mode ──────────────────────────────────────────────────────────
def mode_selfcheck() -> int:
    """Run --selfcheck on every script in scripts/."""
    rc = 0
    for name in ("chunk_plan.py", "rename_tag.py"):
        cprc, cpout, cperr = _run_script(str(HERE / name), ["--selfcheck"])
        print(f"{name}: {'OK' if cprc == 0 else 'FAIL'}")
        if cprc != 0:
            print(cperr, file=sys.stderr)
            rc = cprc
    # also: ask the debriefer scripts to import each other
    try:
        import rename_tag  # noqa: F401
        import chunk_plan  # noqa: F401
        print("imports: OK")
    except Exception as e:
        print(f"imports: FAIL ({e})", file=sys.stderr)
        rc = 4
    return rc


def main():
    ap = argparse.ArgumentParser(description="debrief driver")
    sub = ap.add_subparsers(dest="mode", required=True)

    p_plan = sub.add_parser("plan", help="chunk plan + extraction prompts + rename target")
    p_plan.add_argument("--path", action="append", help="transcript path (repeatable)")
    p_plan.add_argument("--json", action="store_true")

    p_val = sub.add_parser("validate", help="BLOCKERS-id validity check")
    p_val.add_argument("--existing-tasks", required=True,
                       help="TaskList snapshot (json: list of {id, status, subject})")
    p_val.add_argument("--proposed-tasks", required=True,
                       help="Proposed task bodies (json: list of {id?, subject, description})")

    sub.add_parser("selfcheck", help="run --selfcheck on every script")

    args = ap.parse_args()
    if args.mode == "plan":
        return mode_plan(args.path or [], args.json)
    if args.mode == "validate":
        return mode_validate(args.existing_tasks, args.proposed_tasks)
    if args.mode == "selfcheck":
        return mode_selfcheck()
    ap.error(f"unknown mode: {args.mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main())