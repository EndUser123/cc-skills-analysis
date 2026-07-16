---
name: debrief
description: "Unified analysis hub — mines transcripts for unfinished work + origin-anchored tasks. Modes: default (transcript → root-cause tasks), chain (multi-session retrospective: /recap→gaps→/friction→/red-team→/rns + SCORES), gaps (deterministic gap detectors + mandatory haiku gap reviewer + RNS + artifact contract), top (6-source problem scan → ranked tasks). Trigger phrases: 'debrief this transcript', 'mine the chat history', 'victim log', 'why is this broken', 'run a retro', 'top problems', 'what gaps remain'. Absorbs /retro and /top-problems; gap detection is debrief-owned."
version: 1.0.50
status: stable
category: analysis
enforcement: advisory
triggers:
  - /debrief
  - "debrief this transcript"
  - "victim log"
  - "why is this broken"
  - /retro
  - /top-problems
  - "run a retro"
  - "top problems"
  - "what gaps remain"
suggest:
  - /improve
  - /wiki
  - /review
  - /red-team
do_not:
  - write a finding as a task without running /truth on it (UNVERIFIED claims don't ship)
  - state a verified fact without a file:line citation
  - mark a task complete on the basis of a fix that could not be run
  - skip the source-file rename when the user gave a file path
execution:
  directive: Read the source transcript, detect victim-log signature, dispatch parallel investigator subagents that call debrief_core.run() per finding-tree with /truth verification at every layer, then TaskCreate/Update and rename the source file.
  default_args: "<path-to-transcript-or-export>"  # If omitted, auto-resolve via resolve_export.py (see Auto-resolving the input file below).
  examples:
    - "/debrief C:/Users/brsth/Downloads/session-export.txt"
    - "/debrief  (uses the file already referenced in conversation)"
    - "mine this chat history for open issues and make tasks"
    - "why does this transcript keep mentioning bash going silent"
workflow_steps:
  - id: ingest_and_classify
    first_tool: Bash
  - id: detect_victim_log
  - id: recursive_investigate
    first_tool: Agent
  - id: verify_with_truth
    first_tool: Skill
  - id: gap_analyze_tasks
    first_tool: TaskList
  - id: write_tasks
    first_tool: TaskCreate
  - id: tag_source_file
    first_tool: Bash
  - id: report_and_breadcrumb
---

# /debrief — Recursive Root-Cause Investigator

**Problem solved:** "I have a transcript that keeps mentioning the same symptoms — bash went silent, hooks mis-fired, the parser crashed. I want each symptom traced back to the **code origin**, not just listed. The next LLM should pick up the tasks and fix the bug, not patch the symptom."

A transcript is a **victim log**. By the time the symptom appears, the bug is already in the code. `/debrief` exists to invert that: it walks each finding **down the causal chain** — symptom → candidate origin → verified origin — until every surfaced task is anchored at the code line that has to change, not the transcript line that has to be ignored.

## Why this skill exists (the failure mode it prevents)

Three kinds of rot turn a transcript into useless noise:

1. **Symptom-list rot.** A debriefer writes tasks like "Bash returned empty" — anchored at the transcript line. The next LLM picks up the task, can't reproduce the symptom without the transcript, and either closes the task unverified or spends an hour rediscovering the origin. The right task is anchored at the **line of code that produces the symptom**, not the line of transcript that describes it.
2. **Unverified-claim rot.** A prior session's guess ("the file is 2.7 GB", "the root cause is X") gets copied forward until someone treats it as ground truth. `/debrief` runs `/truth` on every claim at every layer of the recursion — no claim advances to a task without a `VERIFIED | FALSE | PARTIAL | UNVERIFIED` verdict, and `UNVERIFIED` blocks advancement.
3. **Re-walked-dead-end rot.** The next LLM re-derives the same wrong premise the last one did, because the wrong turn was never recorded. `/debrief` lifts every dead-end into the task body so the next investigator starts at the origin, not at the wrong premise.
4. **Orphaned-finding rot.** An extraction surfaces 30 findings; 5 become tasks, 25 are "already fixed / already tracked / deferred / external" and silently dropped. The next session re-discovers them because they were never *recorded as resolved or parked*. `/debrief` must account for **every** finding.

So a task written by `/debrief` is a **memory-transfer device anchored at the code**, not a symptom index. If a fresh session can't pick up the task and make verifiable progress without re-reading the transcript, the task is incomplete.

## When to use

- The user points at a transcript and says "find the bugs" / "what's still broken" / "trace this back to origin."
- The transcript itself shows victim-log patterns (multiple symptoms of the same kind — see **Phase 0: victim-log detection**).
- End of a long multi-turn session that surfaced findings but didn't track them.
- A session was compacted or interrupted mid-investigation and the open threads need to survive.

**Do NOT use for:**
- Live session summarization with no file (that's `/recap`).
- A pure bug fix on a known root cause (that's `/rca` or `/debug`).
- A multi-session chain analysis with no export file — `/debrief chain` handles chain exports (`chain_*.md`) directly. If you only have loose per-session transcripts that haven't been chained yet, run `/recap` on each first to build the chain.

## Modes

`/debrief` is four entry points sharing one state machine. Pick by what the user pointed at.

| Mode | Invocation | When | What it does |
|---|---|---|---|
| **default** | `/debrief <file>` | A single transcript or session export | Victim-log detection → recursive origin-trace → VERIFIED tasks + source-file rename. The full Phase 0–9 loop. |
| **chain** | `/debrief chain <chain_*.md>` (or `/retro`) | A multi-session chain export | Walks the chain through the retrospective protocol: recap → gaps → `/friction` → `/red-team` (pre-mortem) → `/rns`, then emits a SCORES summary. Absorbs `/retro`. |
| **gaps** | `/debrief gaps <path>` | Want deterministic first-pass detectors before recursion | Runs debrief's session-goal/outcome detectors + carryover registry + leverage scoring + mandatory haiku gap-reviewer, seeds the findings into `debrief_core.run()`. Artifact contract enforced. |
| **top** | `/debrief top <path>` (or `/top-problems`) | Want a ranked architectural-problem scan across the 6 sources | 6-source scan + veto checks + X-Y detection + fix-level classification → **ranked tasks** (findings become tasks; debrief creates them just like in default mode). Absorbs `/top-problems`. |

**Modes compose.** `/debrief gaps top <path>` runs deterministic detectors AND the 6-source scan, merging both finding sets before the recursive state machine. `/debrief chain <file>` implies `gaps` (chain mode always runs the deterministic detectors on each session segment).

**The unifying rule across all modes:** every finding flows through `debrief_core.run()` — the enforced CLASSIFIED → LOCATED → VERIFIED → WRITTEN state machine with `/truth` verification at every layer. No mode bypasses the gate. The difference is *what seeds the findings*: default relies on LLM extraction, gaps adds deterministic detectors, top adds the 6-source ranked scan, chain sequences it across sessions. Lateral opportunity findings are now routed through `write_opportunity_layer()` — they require an `idea` and `generalization_test` to reach WRITTEN; weak opportunities are rejected with `PROMOTE_TO: reject`.

## Two surfaces of /debrief

`/debrief` is two surfaces, but they differ in scope. The **skill** (`/debrief <file>`) is the full recursive origin-trace: it runs the complete state machine through `debrief_core.run()`, walks the causal chain, verifies each finding with `/truth`, and writes tasks. The **hook** (`SessionEnd_debrief_reflect.py`) is **candidate extraction only**: it reads the last 3000 lines of a session transcript, calls a local or hosted LLM for defect/opportunity candidates, and writes a `candidates.json` file for human review. Hook output must not be mistaken for the full debrief verification — it carries a `coverage_scope` metadata field documenting this. Both surfaces share the same opportunity schema (`assets/opportunity_task_template.md`) and the same `__lib/dream_state.py` for cross-session idempotency. Findings from both surfaces land in the same artifacts directory; the user reviews and promotes them the same way.

## Routing rule — read this before answering "should I use /debrief?"

Do not route to `/debrief` because some other skill's docs say so. Read
[`references/routing-by-affordances.md`](references/routing-by-affordances.md)
first; route by the work's affordances, not by citing another skill's
self-positioning. The full rule + a worked example for transcript-mining
questions live there.

## Internal rubric — bad LLM behavior detection

When the walked transcript/chain contains examples of bad LLM behavior (false
claims, name-based inference, sycophancy, goal drift, compact drift, fabricated
completion, rubber-stamping, missed user corrections, wrong command choice,
recurring patterns), `/debrief` applies the rubric at
[`references/bad-behavior-rubric.md`](references/bad-behavior-rubric.md) as an
internal check. It is not a new mode or visible command; findings ride
`/debrief`'s existing state-machine output through the same `/truth` gate as
any other finding.

## Auto-resolving the input file

When `/debrief` is invoked **without** a `<path>` argument, the LLM MUST auto-resolve an export for the current session before invoking the `plan` step. The flow:

1. **Derive `session_id` explicitly** — from the live `transcript_path` in your most recent hook payload (per `/recap` SKILL.md rule). Do **NOT** rely on terminal-keyed auto-detection.
2. **Run the resolver**:
   ```bash
   python "P:/packages/.claude-marketplace/plugins/cc-skills-analysis/skills/debrief/scripts/resolve_export.py" \
     --session-id "<derived_session_id>"
   ```
   It prints one JSON line to stdout: `{"path": "...", "session_id": "...", "action": "reused"|"exported"|"stale"|"missing", "stale": bool}`.
   - `action=reused` — an existing export in `~/.claude/exports/` or `~/Downloads/` matches this session and the live transcript is not newer than the export. Use the `path` field directly.
   - `action=exported` — no fresh export existed (or the existing one was stale); the resolver invoked `chs_cli.py --export --session-id <id>` and wrote a new file. Use the new `path`.
   - `action=stale` or `missing` — only happens with `--no-export`; re-export first or pass `--force-export`.
3. **Pass the resolved path to `plan`**: `python scripts/debrief.py plan --path "<resolved_path>"`.

**How matching works.** Exports written after this commit ship with a YAML frontmatter block (`session_id`, `exported_at`, `session_count`, `chain_depth`) at the top — that is the authoritative match key. Older exports lack frontmatter; the resolver falls back to the prose `**Root session:**` line at the top of the file. This backward-compat fallback means legacy exports from before this commit still resolve correctly.

**How staleness works.** The export is stale when the live transcript's mtime is newer than the export file's mtime. During a live session the transcript is being written continuously, so a re-export is expected to fire once per `/debrief` invocation — that's a point-in-time snapshot, not a bug. Re-running `/debrief` later will re-export again; proliferation is bounded by the timestamp suffix and can be GC'd separately.

**Why the resolver requires `--session-id`.** The resolver does NOT auto-detect the current session from a terminal-keyed file or `~/.claude/active-session-*.txt` — that path is unsafe under concurrent Claude sessions in one Windows Terminal (last-writer-wins). The LLM is the only actor that can correctly derive `session_id` from the live `transcript_path` in its hook payload context. The resolver is therefore a *consumer* of an explicitly-passed id, not an auto-detector.

**Safety.** Creating a new export is additive (it writes a new file under `~/.claude/exports/`); it does NOT mutate live state. The skill's "confirm before mutating live state" rule (below) does not require a confirmation prompt here. Re-exports for a stale match overwrite `chain_<session_id>_refresh.md` (a sibling filename) to avoid timestamp pile-up; the original stale file is left in place for forensic reference.

## Handoff routing

After classifying findings, `/debrief` emits a `HANDOFF:` block naming each
finding's destination (`/improve`, `/skill-audit`, `/claude-audit`, `/red-team`,
`/review`, `/wiki` candidate, task, reject). The full per-finding destination
rules live at [`references/handoff-routing.md`](references/handoff-routing.md).
`/debrief` produces `/wiki` **candidates**; it does not auto-write `/wiki`.
The consolidation acceptance checklist (criterion 6) enforces this gate.

## The investigator loop

The skill's body is **a loop, not a pipeline**. Each finding is the unit of work; each iteration walks one layer closer to the origin. The bundled state machine `__lib/debrief_core.py` enforces the discipline; the LLM supplies the human judgment (read files, classify, recurse).

The full Phase 0 → Phase 9 diagram lives in [`references/loop-diagram.md`](references/loop-diagram.md). Read it before invoking the loop.

## Bundled components

| File | Role |
|---|---|
| `__lib/debrief_core.py` | The state machine + recursive loop. The LLM supplies `source_tree_resolver` and `layer_extractor` callbacks (Agent tool invocations); `debrief_core` enforces the state discipline and emits ready-to-task bodies. `--selfcheck` green. |
| `__lib/gap_engine_adapter.py` | Optional bridge to debrief's deterministic gap engine (session goal/outcome, completion filter, carryover+resolution registry, leverage scoring, gap-to-skill routing). Lazy-imported from `skills.debrief.gap_engine`; only loaded under `--gap-detectors`. Converts engine Findings to debrief's `{symptom_text, symptom_source}` shape at the boundary so the state machine stays the single source of truth. |
| `scripts/chunk_plan.py` | Chunk plan + theme-hint grep. |
| `scripts/debrief.py` | Driver: `plan` (chunks + extraction prompts), `run` (route deduped findings through `debrief_core.run()` — the only path to `WRITTEN`), `validate` (BLOCKERS-id check), `close` (Phase 8/9 closure gate — refuses done without a tagged file + breadcrumb task), `selfcheck`. |
| `scripts/rename_tag.py` | Deterministic source-file rename. |
| `assets/task_template.md` | The 9-field cold-start task template (TLDR + 9 fields, lite/full split). |
| `references/extraction_prompt.md` | The paste-ready parallel-extraction prompt (Phase 1). |
| `references/task_writing_guide.md` | The 9-field rationale + grouping rule + decision-gate-first. |

## Scope boundaries

- **This skill writes tasks and renames one source file.** It does not implement fixes. If the user wants a fix implemented, say so and stop.
- **Confirm before mutating live state.** Phases 6/8 are side-effecting. State the plan (N creates, M updates, old → new filename) and proceed. Pause for confirmation if the rename target is outside Downloads or if the plan creates more than ~8 tasks.
- **Mark every cross-session claim with its evidence level.** `MUST RE-VERIFY` is mandatory for any claim the recursion couldn't reach verified-origin level on.
- **When recursion hits the budget without verifying origin, write the task with `MUST RE-VERIFY: <next-session-action>` so the breadcrumb tells the next LLM exactly where to pick up.**
- **Every finding must be accounted for.** Group findings into task groups freely (fewer, well-scoped tasks beat tracker bloat), but none may be orphaned. The accounting: (1) **open/un-tasked** → one task each or folded into a group task that lists them; (2) **verified-fixed** → recorded in the breadcrumb task, no separate task; (3) **already-tracked** → cite the existing `#<id>` in the breadcrumb; (4) **explicitly deferred** → one PARKED group task with the deferral gate (see #989); (5) **external / not-our-code** → one documentation-only task. Before `close`, state the count **in the breadcrumb task body** using this exact sentinel (the `close` gate regex-matches it as a structure-invariant — it refuses exit 0 without it): `ACCOUNTING: <N> findings -> <A> tasked, <B> fixed-in-breadcrumb, <C> deferred, <D> external`. The sentinel proves accounting *happened*; the gate deliberately does not validate the numbers.
- Per the global Destructive Action rules, confirm before deleting or overwriting anything other than the task tracker entries and the single source-file rename.
- **Before close, ask: did this session surface any stale-path / dead-doc / drifted-config reference?** If yes, file it as a breadcrumb note pointing to `/main` (the `doc_drift` check scans CLAUDE.md + settings.json for absolute script paths that no longer resolve) — not as a task. The next `/main` run will re-flag it until the doc or the code is fixed.

## Durable-lesson pass

Every non-trivial debrief must explicitly check whether a verified finding is
more than a one-off symptom or local fix. Ask:

1. Does the finding reveal a reusable engineering or workflow principle?
2. Would the principle apply in another coding task, subsystem, or session?
3. What evidence supports the generalization, and what observation would
   falsify it?
4. Is the right destination a concrete task, a `/wiki` candidate, a skill or
   hook change, or rejection as local-only?

For coding findings, preserve the general rule: **minimal surface area,
complete defensive behavior**. A small change must not remove validation,
error handling, privacy protections, lifecycle cleanup, resource bounds,
compatibility behavior, or regression coverage merely to keep the diff small.
The principle applies across coding work, not only to CCR or observability.

Durable lessons require evidence and a stated scope. `/debrief` may emit a
`/wiki` candidate, but must not write durable memory automatically; `/wiki`
remains the approval-gated persistence owner. One-off fixes stay tasks or are
rejected as local-only.

## Source-file naming standard (Phase 8)

The rename target is **not** a freeform restatement of the transcript. It follows one house format:

```
<session-start-date> [<Domain-theme> #<id> #<id> · <theme> #<id>].<ext>
```

Example: `2026-07-01 [CHS #917 · dream-cycle #976 · gate #942 · plugin-audit #982].txt`

Rules — the export tool's auto-generated stem (`2026-07-01-145732-cusersbrsthdownloads-...`, `Review npm version file content`, etc.) is garbage and is **never** kept:

1. **Prefix = session-start date only**, pulled from the transcript *content* — the earliest real in-session event timestamp. NOT the export-tool filename timestamp, and NOT a date quoted inside a recap/template/example. Pass it as `rename_tag.py --date YYYY-MM-DD`.
2. **Bracket = domain/feature themes only.** Short topic labels (`CHS`, `pi`, `go`, `gate`, `plugin-audit`, `opportunity`); acronyms UPPERCASE, else lowercase.
3. **Each task ID appears exactly once**, under its real topic. Never list the same ID under two themes.
4. **No meta / self-referential themes.** `debrief-skill` and `breadcrumb` do not go in the filename — the breadcrumb lives in the task tracker (`#NNN`), which is where the next `/debrief` looks it up.
5. Themes joined by ` · `.

`rename_tag.py --date <session-start-date> --themes "<Domain>:<id>,<id> <theme>:<id>" --path <file> --apply` enforces this. `--selfcheck` asserts the format.

## The recursive investigator in 5 lines

A debriefer running `/debrief` does, in order: (1) `debrief.py plan --path <file>` to get chunks + theme hints, (2) `debrief.py run --path <file> --findings <dedup.json> --truth-mode contract` to route the deduped findings through the enforced state machine (the only path to `WRITTEN` tasks — `contract` mode leaves un-/truth-stamped findings at LOCATED with a `MUST RE-VERIFY` note), (3) call `/truth` on every layer transition the run surfaced, (4) gap-analyze the `WRITTEN` findings against `TaskList` and TaskCreate each + invoke `rename_tag.py --apply`, (5) `debrief.py close --path <file> --breadcrumb-task N --tracker-snapshot <dump>` as the closure gate — it refuses exit 0 unless the source file is tagged AND a non-completed breadcrumb task exists. The loop in (2) does the heavy lifting; the gate in (5) is what stops "done" from being a judgment call. Pass `--wiki` to (5) to emit a `/wiki ingest <tagged-file>` directive — the B/C/D accounting buckets (verified-fixed, deferred, external) are durable knowledge, not tasks, and `/wiki` ingests the tagged transcript with automatic SHA256 dedup (re-ingest of an already-logged file is a no-op, so it's safe to run every close).

`/debrief` handles both single-transcript files and multi-session chain exports (`chain_*.md`) — the victim-log detector, recursion budget, and `--truth-mode contract` gate all scale to chain length. **Chain mode** (`/debrief chain` or `/retro`) walks the chain through the retrospective protocol: recap → gaps → `/friction` → `/red-team` (pre-mortem) → `/rns`, then emits a SCORES summary. Both the default and chain modes share `debrief_core` (same state machine, victim-log detection, /truth gate, task template). `/retro` is now a stub routing to `/debrief chain` — do not invoke it directly; chain `chain_*.md` inputs through `/debrief chain`.

## Gaps mode: debrief-owned deterministic detectors (`--gap-detectors`)

`/debrief gaps` is selected by passing `--gap-detectors` to the run. `/debrief`'s strength is recursive origin-tracing; the gap engine supplies the deterministic first pass — session-goal/outcome detection, carryover+resolution registry, leverage scoring, and gap-to-skill routing — before findings enter the recursive state machine.

- `--gap-detectors`: run debrief's deterministic detectors on `--path` and merge the open findings into the run. Findings arrive as `{symptom_text, symptom_source}` at the same `--findings` seam debrief_core already consumes, then flow through the normal state machine (CLASSIFIED → LOCATED → VERIFIED → WRITTEN). Each WRITTEN task body gets a `[gap] gap_score: N | owner_skill: X` tag stamped by `attach_score_and_owner`.
- `--gap-review` (requires `--gap-detectors`): two-pass gap-reviewer agent. Pass 1 writes `gap_reviewer_handoff.json` under `~/.claude/.artifacts/debrief/{session-id}/` and prints the Agent-tool dispatch instruction; the running LLM dispatches the gap_reviewer, which writes `gap_reviewer_result.json`. Re-run with the same flags (pass 2) to merge the agent's findings.
- `--findings` is optional when `--gap-detectors` is set; supply both to merge LLM-extracted findings with detector findings.

**Carryover model:** the gap engine's carryover (`carryover.json`) persists per `--session-id` alongside debrief's `dream-state.json`. Different axes — finding-ID-keyed vs topic-keyed — no merge. Carryover lets a goal that recurred across sessions escalate severity even when each individual transcript mentions it once.

**Coupling note:** `--gap-detectors` imports from `skills.debrief.gap_engine` (lazy, in-function). The base `run` path stays import-free. The gap engine is debrief-owned, so its adapter and state machine evolve together.

## After-action rubric — false absorption / lazy stub classification

When the session under review contains command-consolidation, migration, or absorption work (claims that a command was "shipped / absorbed / stubbed / deprecated / internalized / retired"), flag these as root-cause tasks and route to `/skill-audit preserve`:

- **False absorption claim** — a parent mode advertised as production while its backend runner/harness/script is missing or pending. (Regression of record: `/adv-review` → `/red-team adversarial` advertised dispatch while `runner.py`/`calibrate.py`/`harness_registry.py` were unbuilt, #872/#873/#874.)
- **Lazy stub classification** — a deprecated command labeled a "stub" by name without reading its source. A deprecation header ≠ stub; `workflow_steps: []` alone ≠ stub. The classifier must read the full body and any referenced engine/backend.
- **Unsupported "shipped" claim** — a consolidation report asserting a command was absorbed without citing old-source + parent-source + backend-existence evidence.

Detection cue: any doc/migration-table row using the words *stub*, *absorbed*, *shipped*, *deprecated*, *internalized*, *retired* without a source citation. Each instance becomes a root-cause task pointing at `/skill-audit preserve <plan>` (or `/red-team` for adversarial review). The mechanical scaffold is `cc-skills-analysis/skills/skill-audit/scripts/capability_preservation.py`; the rubric is `references/capability-preservation-check.md`.

`/debrief` does not run the audit itself — it captures the lesson and routes.

## Cross-Skill Transfer Check (XSTC)

After the `HANDOFF:` block and before the breadcrumb task body, emit one
XSTC artifact per run. Local transcript findings → `local_only`; recurring
LLM-behavior or process patterns → classification + affected_surfaces +
owner + validation_step. Canonical template + worked examples at
[`references/cross-skill-transfer-check.md`](references/cross-skill-transfer-check.md).
The owner field maps to a retained command (`/improve`, `/red-team`,
`/review`, `/debrief`, `/claude-audit`, `/skill-audit`, or "shared routing
reference") — pick by the affordance table in the template, not by name.

**Advisory status:** XSTC discipline is currently prompt-advisory only. No
runtime hook enforces XSTC emission. See the CEC's
`completion-evidence-contract.md` for the typed-evidence discipline that
governs completion claims.

## Completion Evidence Contract — after-action rubric

When mining transcripts that contain overclaim patterns, classify each
discovery using the contract's four overclaim types. The contract lives
at
[`references/completion-evidence-contract.md`](references/completion-evidence-contract.md).
The four rubric classes:

| behavior_type | What it means | Evidence |
|---|---|---|
| `overclaimed_completion` | Report claims "done"/"verified"/"zero drift" without ledger row, or with row whose evidence doesn't match authority_required | Compare the report's ✅ block to its ledger rows; mismatched status = overclaim. |
| `fake_verification` | Report quotes output that was never actually produced (echoed, hallucinated) | Re-run the verification command; if output differs, the quote is fabricated. |
| `static_test_runtime_confusion` | Report claims `runtime_enforced` for a guardrail whose only evidence is `static_invariant_tested` or `prompt_advisory` | Read the SKILL.md claim + the test; the mismatch is the overclaim. |
| `user_surface_verification_gap` | Report claims user-visible behavior without driving the actual user path (no `claude plugin list`, no slash command invocation) | Check for `claude plugin list` / command-line smoke evidence; absence = overclaim. |

Emit the classified finding into the same XSTC `HANDOFF:` block under
`/debrief`. Routes:

- `overclaimed_completion` → `/red-team` (the contract is the acceptance criterion; `/red-team` BLOCKs).
- `fake_verification` → `/red-team` + `/skill-audit` (the SKILL.md that made the claim needs audit).
- `static_test_runtime_confusion` → `/claude-audit` if it's a hook/config gate, else `/skill-audit`.
- `user_surface_verification_gap` → `/claude-audit` if the surface is plugin/marketplace, else `/skill-audit`.

## Thought Partner Addendum

At the end of transcript mining, emit a Thought Partner Addendum (TPA) when
the pass surfaced a lesson not captured as a task that would change future
efficiency, effectiveness, or trust. Each item carries `observation`,
`why_it_matters`, `evidence`, `recommended_action`,
`urgency: now | later | watch`. Wiki candidates stay candidates — do not
auto-write `/wiki`. Omit the section when nothing material was found; never
displace the after-action rubric or the CEC ledger. Canonical contract +
worked examples at `debrief/references/thought-partner-addendum.md`
(canonical owner: `/improve`). The TPA is prompt-advisory only.

## Partner Posture

`/debrief`'s posture is **Learning / Forensics Partner** (see the Partner
Posture Map in `debrief/references/thought-partner-addendum.md`). `/debrief`
mines transcripts, sessions, failures, bad LLM behavior, missed opportunities,
unresolved work, and durable lessons, separates transcript findings from
recommendations, produces task / wiki / skill / hook candidates without
silently writing to `/wiki`, and detects recurring patterns and handoff gaps.
Posture is prompt-advisory.

## Suggest

`/debrief` cross-suggests after a run (once tasks are written, not mid-analysis):
- `/improve` — when a root-cause finding is better treated as a design/process/hook recommendation than a tracker task.
- `/wiki` — when a session produced a durable lesson worth persisting (not a one-off bug fix).
- `/review` — when a generated task touches implementation quality the user should run a structured review on.
- `/red-team` — when a finding is a high-risk design or contract change worth adversarial stress before the task is executed.
