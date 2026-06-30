---
name: debrief
description: "Mine a chat-history export or session-transcript FILE for every open issue and opportunity, then create or update structured tasks in the task tracker — each written to survive a cold start — and tag the source file with the resulting task numbers. Use this whenever the user points at a transcript / chat-export / session-history file and wants the unfinished work captured as tasks, or asks to find the open issues and opportunities, turn this session into tasks, or mine the chat history. Also use it proactively at the end of a long session that produced findings but no tracked tasks. Distinct from /recap (summarizes only) and /top-problems (identifies problems but never creates tasks) — this skill WRITES to the task tracker via TaskCreate/TaskUpdate and renames the source file."
version: 0.1.0
status: experimental
category: analysis
enforcement: advisory
triggers:
  - /debrief
  - "transcript to tasks"
  - "mine the chat history"
  - "open issues and opportunities"
  - "turn this session into tasks"
  - "debrief this transcript"
suggest:
  - /recap
  - /top-problems
  - /gto
do_not:
  - create tasks without first reading the existing task list (creates duplicates)
  - state a verified fact inside a task without a file:line or transcript-line citation
  - mark a task complete on the basis of a fix you could not run
  - skip the source-file rename when the user gave a file path
execution:
  directive: Read the source transcript file (parallel-chunked if large), extract open issues and opportunities, gap-analyze against the existing task list, then create or update tasks in the cold-start template, wire dependencies, and tag the source file with task numbers.
  default_args: "<path-to-transcript-or-export>"
  examples:
    - "/debrief C:/Users/brsth/Downloads/session-export.txt"
    - "/debrief  (uses the file already referenced in conversation)"
    - "mine this chat history for open issues and make tasks"
workflow_steps:
  - id: ingest_source
    first_tool: Read
  - id: synthesize_findings
  - id: gap_analyze_tasks
    first_tool: TaskList
  - id: write_tasks
    first_tool: TaskCreate
  - id: wire_dependencies
  - id: tag_source_file
    first_tool: Bash
  - id: report
---

# /debrief — Transcript → Cold-Start Tasks

**Problem solved:** "I have a big chat-history export and I want every piece of unfinished work captured as tasks that the *next* LLM — starting cold, with zero memory of this session — can actually pick up and finish."

A transcript is a one-way time capsule. The findings inside it die there unless they're promoted into the task tracker in a form that survives a cold start. This skill is that promotion pipeline: **read → mine → gap-analyze → write tasks → wire dependencies → tag the source file.**

## Why this skill exists (the failure mode it prevents)

Transcripts carry two kinds of rot that make naive "summarize and list" useless:

1. **Unverified claims repeated as fact.** A prior session's guess ("the file is 2.7 GB", "the root cause is X") gets copied forward until someone treats it as ground truth. The fix is structural: every task must separate **VERIFIED FACTS** (with a citation) from **MUST RE-VERIFY** (explicitly untrusted).
2. **Re-walked dead ends.** The next LLM re-derives the same wrong premise the last one did, because the wrong turn was never recorded. The fix is a **DEAD ENDS** field: "we tried X, it was the secondary cause, don't ship it as the answer."

So a task written by this skill is a *memory-transfer device*, not a reminder. If a fresh session can't pick it up and make verifiable progress without re-reading the transcript, the task is incomplete.

## When to use

- The user points at a transcript / chat-export / `.txt` / `.jsonl` session file and wants unfinished work captured.
- End of a long multi-turn session that surfaced findings but didn't track them.
- A session was compacted or interrupted mid-investigation and the open threads need to survive.
- The user asks to "find the open issues", "what's still broken", "turn this into tasks".

**Do NOT use for:** live session summarization with no file (that's `/recap`), or listing problems without creating tasks (that's `/top-problems`).

## The pipeline

### Phase 1 — Ingest (read the whole source, cheaply)

Transcript exports are usually too large for one Read (the Read tool caps at ~256 KB). Don't try to read it all yourself and don't read it serially.

1. Count lines: `wc -l "<file>"`.
2. If it fits one Read (< ~250 KB), read it directly.
3. If it's large, **split into N equal chunks and dispatch N parallel `Explore` subagents**, one per chunk, each running the extraction prompt in [`references/extraction_prompt.md`](references/extraction_prompt.md). Target ~2,000 lines per chunk and **cap N at 6** — beyond that the token cost (each subagent reads its chunk in full) outweighs the latency win, and you must still synthesize all N outputs in one place.

The parallel chunk-read is the single biggest lever on a big transcript — a 9k-line file takes the same wall-clock as a 2k-line file. The extraction prompt is fixed and lives in the reference file so every run uses the identical, battle-tested wording rather than reinventing it.

Each subagent returns: open issues + opportunities, each with a 1–3 sentence description, the **transcript line number(s)**, and any **named files/plugins/symbols**.

### Phase 2 — Synthesize

Collect the chunk outputs and produce a single consolidated list:
- **Group by theme** (e.g. "ingestion & data quality", "tooling friction", "state/hygiene debt"). Themes make the list scannable and surface the real center of gravity.
- **De-duplicate** across chunks (the same issue often appears in two adjacent chunks).
- **Separate OPEN ISSUES from OPPORTUNITIES.** Issue = something broken/blocking/risky. Opportunity = an improvement that could be taken.
- Keep the transcript line numbers — they are the citation that lets a follow-on LLM jump straight to the evidence.

### Phase 3 — Gap-analyze against the existing task list (BEFORE creating anything)

This is the step that prevents the most common failure: duplicate tasks. **Call `TaskList` first.** For every item from Phase 2, decide:

- **UPDATE** an existing task if one already covers it → append the new evidence, dead-ends, and line citations to that task's description (do not overwrite — append a dated section).
- **CREATE** a new task only if nothing existing covers it.

A follow-on LLM cannot find work that lives in two places. When in doubt, update.

### Phase 4 — Write tasks in the cold-start template

Every task — created or updated — gets the eight fields in [`assets/task_template.md`](assets/task_template.md):

```
TITLE:        imperative, names the shipping change (not the symptom)
PROBLEM:      one sentence — the user-facing problem
VERIFIED FACTS: file:line + probe output + transcript line, with source tags
MUST RE-VERIFY: claims carried from the session that were NOT re-confirmed
DEAD ENDS:    approaches already tried that failed or were the wrong cause
DISCRIMINATING TEST: the one command that says fixed / not-fixed
DEFINITION OF DONE: concrete, runnable, gated
BLOCKERS:     task IDs or external facts that gate this
BLAST RADIUS: what it touches, reversibility, safety notes
```

The full rationale for each field (and the writing principles — one task per *change-unit* not per atomic issue; decision-gate-first; why "DEAD ENDS" matters more than "background") is in [`references/task_writing_guide.md`](references/task_writing_guide.md). Read it before the first task you write in a session.

**Grouping rule:** one task per *change-unit that ships and verifies together*, not one task per atomic issue. A "fix the parser" + "repoint the source" + "repair the bad rows" that all live in one pipeline and verify with one test are ONE task with sub-bullets, not three.

**Scale the template to the finding.** The full eight fields are for non-trivial change-unit tasks. For a genuinely trivial, single-step finding on a small transcript, a **lite task** is acceptable: `PROBLEM` + `DISCRIMINATING TEST` + `DEFINITION OF DONE`. If you can't fill `DEAD ENDS` with anything real (not "none"), that's the signal the finding is lite-tier — don't pad the field. A lite task is still a task; what's forbidden is dropping `DISCRIMINATING TEST`, because that's the field that enforces "verified, not asserted."

### Phase 5 — Wire dependencies

Create blocker/decision-gate tasks FIRST so you can reference their IDs, then set `blockedBy` on the tasks they gate. Emit the result as a small dependency graph in the final report — it tells the next LLM the order to attack.

Common pattern: if the value of a body of work is unproven, create a cheap **decision-gate** task ("measure whether anyone actually uses X") and `blockedBy` the expensive pipeline tasks on it. This stops follow-on LLMs polishing a ghost.

### Phase 6 — Tag the source file

Use the bundled formatter so the rename is deterministic, not improvised each run:

```bash
python skills/debrief/scripts/rename_tag.py \
  --themes "chs:917,918 pi:914 go:916,939 gate:942,943,944,945" \
  --path "<source file>"          # dry-run: prints the name it WOULD produce
  # add --apply once the dry-run looks right
```

The script encodes the house style and — critically — the **noise-vs-signal decision** (`is_noise_name`): throwaway stems (`claude*`, `review *`, `session*`, `✳ …`, pure hex hashes) become bracket-only; meaningful stems (`auth-refactor`, `snapshot-handoff-design`) are kept as a prefix. This stops the "drop the original name" call from being an N=1 over-generalization — it's now an audited rule. Run `--selfcheck` to confirm the formatter before relying on it.

**House style (what the script produces):**

`✳ Review npm version file content.txt` → `[chs #917 #918 · pi #914 · go #916 #939 · gate #942 #943 #944 #945].txt`
`auth-refactor.jsonl` (signal stem) → `auth-refactor [chs #917 #918].jsonl`

- `[ … ]` encloses the tag; themes are short lowercase labels; `<theme> #<id> #<id>` within a theme; themes separated by ` · ` (U+00B7).
- The script validates against Windows-forbidden chars (`\ / : * ? " < > |`) and refuses to overwrite an existing destination.
- This is a rename (reversible). State the old → new path explicitly in the report.

### Phase 7 — Report

Output, in this order:
1. **Consolidated OPEN ISSUES** (grouped by theme, with transcript line citations).
2. **Consolidated OPPORTUNITIES** (same).
3. **Tasks touched** — N created, M updated, with the `#ID` + one-line subject for each.
4. **Dependency graph** (the attack order).
5. **Source file** old → new name.

Keep the report tight — the tasks themselves hold the detail; the report is the index.

## Scope boundaries

- **This skill writes tasks and renames one source file.** It does not implement fixes, run migrations, or edit code beyond the task tracker. If the user wants a fix implemented, say so and stop — don't drift into implementation mid-debrief.
- **Confirm before mutating live state.** Phase 4 (`TaskCreate`/`TaskUpdate`) and Phase 6 (rename) are side-effecting. Before the first write, state the plan plainly — N creates, M updates, and the old → new filename — then proceed. Pause for explicit confirmation if the rename target is outside the user's Downloads/workspace, or if the plan creates more than ~8 tasks (a sign the grouping rule wasn't applied). Always dry-run the rename script (`--apply` is opt-in) before committing it.
- Mark every cross-session claim with its evidence level. If something was NOT re-verified this session, the task's `MUST RE-VERIFY` field says so explicitly. Never let "probably" graduate into an unmarked assertion inside a task.
- Per the global Destructive Action rules, confirm with the user before deleting or overwriting anything other than the task tracker entries and the single source-file rename.

## Reference files

| File | Read it when |
|------|--------------|
| [`references/extraction_prompt.md`](references/extraction_prompt.md) | Phase 1 — the exact parallel-subagent extraction prompt (copy verbatim into each Explore agent) |
| [`references/task_writing_guide.md`](references/task_writing_guide.md) | Phase 4 — before writing the first task: the 8-field rationale + grouping/decision-gate principles |
| [`assets/task_template.md`](assets/task_template.md) | Phase 4 — the copy-paste task skeleton |
