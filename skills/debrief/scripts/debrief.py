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
LIB_DIR = SKILL_DIR / "__lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

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


# ── run mode ────────────────────────────────────────────────────────────────
_TAG_RE = re.compile(r"(?:^| )\[[^\]]+\](?=\.[^.]+$|$)")


def _is_tagged(basename: str) -> bool:
    """A Phase-8-tagged filename carries a ` [tag]` before the extension."""
    return bool(_TAG_RE.search(basename))


def mode_run(path: str, findings_path: str, truth_mode: str,
             resolver_cache_path: str = "", apply: bool = False,
             gto_detectors: bool = False, gap_review: bool = False,
             session_id: str = "debrief-run") -> int:
    """Route deduped findings through debrief_core.run() — the only executable
    path to WRITTEN tasks. The state machine enforces /truth + origin guards;
    this command is what stops the LLM from bypassing it by hand-dedup.

    --truth-mode contract (default): every finding stays UNVERIFIED -> LOCATED
    with recursion_exhausted + a MUST RE-VERIFY note. That is today's behavior,
    but now it is machine-stamped rather than LLM-asserted.

    --gto-detectors: run gto's deterministic detectors (session goal/outcome,
    completion filter, carryover+resolution registry, leverage scoring,
    gap-to-skill routing) on --path and merge findings in. Lazy-imported from
    skills.gto.__lib; base run path stays import-free.
    --gap-review: requires --gto-detectors. First pass writes the gap_reviewer
    handoff + emits the Agent-tool dispatch instruction to stderr; re-run after
    the agent writes gap_reviewer_result.json to merge its findings.
    """
    import debrief_core

    if not os.path.exists(path):
        print(f"error: missing transcript: {path}", file=sys.stderr)
        return 2
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        transcript_text = f.read()
    if not findings_path and not gto_detectors:
        print("error: --findings required unless --gto-detectors is set", file=sys.stderr)
        return 2
    raw_findings: list = []
    if findings_path:
        loaded = _read_json(findings_path)
        if isinstance(loaded, dict):
            loaded = loaded.get("findings", loaded.get("tasks", []))
        raw_findings = loaded if isinstance(loaded, list) else []

    gto_shaped: list[dict] = []
    gto_raw_findings: list = []
    if gto_detectors:
        from gto_adapter import (run_gto_detectors, gto_findings_to_debrief,
                                 write_gap_review_handoff, read_gap_review_debrief)
        artifacts_dir = Path.home() / ".claude" / ".artifacts" / "debrief" / session_id
        gto_raw_findings = run_gto_detectors(path, session_id, artifacts_dir,
                                             root=os.getcwd())
        gto_shaped = gto_findings_to_debrief(gto_raw_findings)
        if gap_review:
            # Second pass: agent already wrote the result file -> merge.
            agent_shaped = read_gap_review_debrief(artifacts_dir)
            if agent_shaped:
                gto_shaped = gto_shaped + agent_shaped
                gto_raw_findings = []  # score/owner attach skipped; agent findings have no score
            else:
                # First pass: write handoff + tell the LLM to dispatch the agent.
                handoff = write_gap_review_handoff(
                    artifacts_dir, gto_raw_findings,
                    session_context={"session_id": session_id, "transcript": path})
                print(f"# gap_reviewer handoff written: {handoff}", file=sys.stderr)
                print(f"# Dispatch the gap_reviewer agent (GAP_REVIEW_SYSTEM), then re-run "
                      f"this command with the same flags to merge gap_reviewer_result.json.",
                      file=sys.stderr)
                return 0
        raw_findings = list(raw_findings) + gto_shaped

    initial = []
    for item in raw_findings:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            initial.append((str(item[0]), str(item[1])))
        elif isinstance(item, dict):
            t = item.get("symptom_text") or item.get("text") or item.get("subject") or ""
            s = item.get("symptom_source") or item.get("source") or item.get("id") or path
            if t:
                initial.append((str(t), str(s)))

    # truth_callable per --truth-mode
    truth_callable = None
    if truth_mode == "contract":
        def truth_callable(f):
            return {"status": "UNVERIFIED", "evidence": "",
                    "correction": "", "note": "contract mode: LLM must run /truth"}
    elif truth_mode == "skip":
        truth_callable = None
    elif truth_mode == "skill":
        print("error: --truth-mode skill not wired yet (plan_verifier CLI unconfirmed)",
              file=sys.stderr)
        return 2
    else:
        print(f"error: unknown --truth-mode: {truth_mode}", file=sys.stderr)
        return 2

    # source_tree_resolver from --resolver-cache (optional). Cache is a list of
    # {text, file, line, explanation} — the LLM populates one per finding.
    resolver = None
    if resolver_cache_path:
        cache_raw = _read_json(resolver_cache_path)
        cache = cache_raw if isinstance(cache_raw, list) else cache_raw.get("entries", [])
        table = {}
        for e in cache:
            if isinstance(e, dict) and e.get("text"):
                table[e["text"]] = (e.get("file", ""), int(e.get("line", 0) or 0),
                                    e.get("explanation", ""))
        def resolver(text: str):
            if text in table:
                return table[text]
            for k, v in table.items():
                if k and (k in text or text in k):
                    return v
            return ("", 0, "")

    res = debrief_core.run(
        transcript_text=transcript_text,
        initial_findings=initial,
        layer_extractor=lambda p: ([], []),
        source_tree_resolver=resolver,
        truth_callable=truth_callable,
    )
    out = {
        "summary": res["summary"],
        "written": res["tasks"]["written"],
        "opportunities_skipped": res["summary"].get("opportunities_skipped", 0),
        "blocked": [f for f in res["findings"]
                    if f.get("state") == "located" or f.get("recursion_exhausted")],
    }
    if gto_shaped:
        from gto_adapter import attach_score_and_owner
        out["gto_findings_merged"] = len(gto_shaped)
        out["written"] = attach_score_and_owner(out["written"], gto_shaped)
    print(json.dumps(out, indent=2))
    if apply:
        print(f"\n# Phase 8 rename (fill themes + run):", file=sys.stderr)
        print(f"python rename_tag.py --themes \"<theme>:<id>,...\" --path \"{path}\" --apply",
              file=sys.stderr)
        print(f"# Phase 9: create breadcrumb task referencing these findings + the renamed file.",
              file=sys.stderr)
    return 0


# ── close mode ──────────────────────────────────────────────────────────────
def mode_close(path: str, breadcrumb_task: int, tracker_snapshot: str,
               allow_untagged: bool = False, wiki: bool = False) -> int:
    """Phase 8/9 closure gate. Refuses exit 0 unless the source file is tagged
    AND a non-completed breadcrumb task exists in the tracker snapshot. This is
    the check that stops the LLM from declaring `/debrief` done without the
    rename + breadcrumb."""
    failures = []
    p = Path(path)
    # Phase 8: file is tagged (or a tagged sibling exists next to the original).
    tagged_present = False
    tagged_path = None
    if p.exists() and _is_tagged(p.name):
        tagged_present = True
        tagged_path = p
    elif p.exists() and not _is_tagged(p.name):
        for cand in p.parent.glob(f"{p.stem} [*]{p.suffix}"):
            tagged_present = True
            tagged_path = cand
            break
    if not tagged_present and not allow_untagged:
        failures.append("source file not tagged (Phase 8 rename did not run)")

    # Phase 9: breadcrumb task exists and is not completed/deleted.
    if tracker_snapshot:
        snap = _read_json(tracker_snapshot)
        if isinstance(snap, dict):
            snap = snap.get("tasks", snap)
        row = next((t for t in snap if t.get("id") == breadcrumb_task), None)
        if row is None:
            failures.append(f"breadcrumb task #{breadcrumb_task} not found in snapshot")
        elif row.get("status") in ("completed", "deleted"):
            failures.append(f"breadcrumb task #{breadcrumb_task} is {row.get('status')}")
        else:
            # Structure-invariant (NOT a discriminator): the breadcrumb must
            # carry an ACCOUNTING line proving the LLM did finding-bucketing at
            # all. Catches "declared done with no accounting" — the one failure
            # mode worth gating. Deliberately does NOT validate the numbers
            # (count-equivalence is theater when both sides come from the same
            # LLM) and does NOT call an LLM verifier (≈0 discrimination on this
            # corpus; see memory feedback_gate_discrimination_rule). Presence of
            # the sentinel is the whole check, like requiring a "TLDR:" prefix.
            body = " ".join(str(row.get(k, "")) for k in ("subject", "description"))
            if not re.search(r"ACCOUNTING:\s*\d+\s*findings", body, re.IGNORECASE):
                failures.append(
                    f"breadcrumb task #{breadcrumb_task} missing ACCOUNTING line "
                    "(emit 'ACCOUNTING: <N> findings -> <A> tasked, <B> fixed-in-breadcrumb, "
                    "<C> deferred, <D> external' per SKILL.md scope boundaries)"
                )
    else:
        failures.append("no --tracker-snapshot supplied (cannot verify breadcrumb)")

    if failures:
        for m in failures:
            print(f"FAIL: {m}", file=sys.stderr)
        return 1
    print(f"OK: tagged file present + breadcrumb #{breadcrumb_task} exists")
    # Reminder fires every close so the flag isn't forgotten; --wiki escalates
    # to a full directive that hands the tagged transcript to /wiki ingest
    # (SHA256 dedup is automatic — re-ingest of an already-logged file is a no-op).
    if wiki and tagged_path is not None:
        print(
            "\nWIKI DIRECTIVE: durable findings (the B/C/D accounting buckets — "
            "verified-fixed, deferred, external) are wiki candidates.\n"
            "  1. Skill(skill=\"wiki\")   # skill-first gate\n"
            f"  2. /wiki ingest \"{tagged_path}\"   # explicit single file, deduped by SHA256\n"
            "If the hash is already in log.md, /wiki skips it — safe to re-run."
        )
    else:
        print("HINT: durable findings are wiki candidates → re-run close with --wiki "
              "to emit the /wiki ingest directive.")
    return 0


# ── selfcheck mode ──────────────────────────────────────────────────────────
def mode_selfcheck() -> int:
    """Run --selfcheck on every script in scripts/, then exercise run + close."""
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
        import debrief_core  # noqa: F401
        print("imports: OK")
    except Exception as e:
        print(f"imports: FAIL ({e})", file=sys.stderr)
        rc = 4

    # _is_tagged: the Phase-8 detection close relies on
    try:
        assert _is_tagged("auth [chs #917].jsonl") is True
        assert _is_tagged("plain-transcript.txt") is False
        assert _is_tagged("[chs #917].txt") is True
        print("is_tagged: OK")
    except AssertionError as e:
        print(f"is_tagged: FAIL ({e})", file=sys.stderr)
        rc = 5

    # mode_run: contract truth-mode must block every finding (0 WRITTEN).
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        tpath = tdir / "tx.txt"
        tpath.write_text("rows duplicate on ingest, fell back to workaround",
                         encoding="utf-8")
        fjson = tdir / "f.json"
        fjson.write_text(json.dumps([
            {"symptom_text": "rows duplicate", "symptom_source": "L10"},
            {"symptom_text": "missing audit log", "symptom_source": "L11"},
        ]), encoding="utf-8")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_rc = mode_run(str(tpath), str(fjson), truth_mode="contract")
        out = json.loads(buf.getvalue())
        assert run_rc == 0, f"run should exit 0, got {run_rc}"
        assert out["summary"]["written"] == 0, \
            "contract mode must not produce WRITTEN tasks (no /truth stamp)"
        assert out["summary"]["total_findings"] >= 2
        print("run-contract: OK (gate bites — 0 WRITTEN)")

        # close: negative case — untagged file, missing breadcrumb.
        snap = tdir / "snap.json"
        snap.write_text(json.dumps([{"id": 1, "status": "pending"}]), encoding="utf-8")
        close_rc_neg = mode_close(str(tpath), breadcrumb_task=999,
                                  tracker_snapshot=str(snap))
        assert close_rc_neg != 0, "close must fail on untagged + missing breadcrumb"
        # close: positive case — tagged file + present breadcrumb WITH accounting.
        tagged = tdir / "tx [debrief #1].txt"
        tagged.write_text("x", encoding="utf-8")
        snap2 = tdir / "snap2.json"
        snap2.write_text(json.dumps([{
            "id": 1, "status": "pending",
            "description": "ACCOUNTING: 2 findings -> 1 tasked, 1 fixed-in-breadcrumb, "
                           "0 deferred, 0 external",
        }]), encoding="utf-8")
        close_rc_pos = mode_close(str(tagged), breadcrumb_task=1,
                                  tracker_snapshot=str(snap2))
        assert close_rc_pos == 0, f"close should pass on tagged + present, got {close_rc_pos}"
        # close: accounting-gate bites — breadcrumb present but no ACCOUNTING line.
        snap3 = tdir / "snap3.json"
        snap3.write_text(json.dumps([{"id": 1, "status": "pending"}]), encoding="utf-8")
        close_rc_noacct = mode_close(str(tagged), breadcrumb_task=1,
                                     tracker_snapshot=str(snap3))
        assert close_rc_noacct != 0, "close must fail when breadcrumb lacks ACCOUNTING line"
        print("close: OK (negative bites, positive passes, accounting-gate bites)")
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

    p_run = sub.add_parser("run", help="route findings through debrief_core.run() (the enforced path)")
    p_run.add_argument("--path", required=True, help="transcript file")
    p_run.add_argument("--findings", default="", help="deduped findings JSON (optional with --gto-detectors)")
    p_run.add_argument("--truth-mode", choices=("contract", "skip", "skill"),
                       default="contract",
                       help="contract=UNVERIFIED stamp (default); skip=no gate; skill=stub")
    p_run.add_argument("--resolver-cache", default="",
                       help="optional JSON: [{text,file,line,explanation}]")
    p_run.add_argument("--apply", action="store_true",
                       help="emit Phase 8/9 instructions to stderr")
    p_run.add_argument("--gto-detectors", action="store_true",
                       help="run gto's goal/outcome/carryover/score/route detectors on --path and merge")
    p_run.add_argument("--gap-review", action="store_true",
                       help="with --gto-detectors: write gap_reviewer handoff (pass 1) / merge result (pass 2)")
    p_run.add_argument("--session-id", default="debrief-run",
                       help="artifacts dir key (default: debrief-run)")

    p_close = sub.add_parser("close", help="Phase 8/9 closure gate (refuses done without tag + breadcrumb)")
    p_close.add_argument("--path", required=True, help="original or renamed transcript")
    p_close.add_argument("--breadcrumb-task", type=int, required=True)
    p_close.add_argument("--tracker-snapshot", required=True,
                         help="TaskList snapshot JSON")
    p_close.add_argument("--allow-untagged", action="store_true",
                         help="skip the Phase-8 tag check (emergency use only)")
    p_close.add_argument("--wiki", action="store_true",
                         help="emit a /wiki ingest directive for the tagged transcript (durable-findings capture)")

    sub.add_parser("selfcheck", help="run --selfcheck on every script")

    args = ap.parse_args()
    if args.mode == "plan":
        return mode_plan(args.path or [], args.json)
    if args.mode == "validate":
        return mode_validate(args.existing_tasks, args.proposed_tasks)
    if args.mode == "run":
        return mode_run(args.path, args.findings, args.truth_mode,
                        args.resolver_cache, args.apply,
                        args.gto_detectors, args.gap_review, args.session_id)
    if args.mode == "close":
        return mode_close(args.path, args.breadcrumb_task, args.tracker_snapshot,
                          args.allow_untagged, args.wiki)
    if args.mode == "selfcheck":
        return mode_selfcheck()
    ap.error(f"unknown mode: {args.mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
