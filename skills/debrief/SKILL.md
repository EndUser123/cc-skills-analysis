---
name: debrief
description: "This skill is used when the user points at a transcript or chat-history file and asks to mine it for unfinished work, open issues, origin-anchored tasks, or to trace symptoms back to code. Trigger phrases include 'debrief this transcript', 'mine the chat history', 'transcript to tasks', 'turn this session into tasks', 'victim log', and 'why is this broken'. Recursively walks symptom → cause → origin chains, calls /friction and /truth from inside the loop, and writes cold-start tasks to the tracker with the source file tagged. Distinct from /recap (summarizes) and /top-problems (lists, never creates tasks); /retro is the multi-session chain mode."
version: 1.0.40
status: stable
category: analysis
enforcement: advisory
triggers:
  - /debrief
  - "debrief this transcript"
  - "victim log"
  - "why is this broken"
suggest: []
do_not:
  - write a finding as a task without running /truth on it (UNVERIFIED claims don't ship)
  - state a verified fact without a file:line citation
  - mark a task complete on the basis of a fix that could not be run
  - skip the source-file rename when the user gave a file path
execution:
  directive: Read the source transcript, detect victim-log signature, dispatch parallel investigator subagents that call debrief_core.run() per finding-tree with /truth verification at every layer, then TaskCreate/Update and rename the source file.
  default_args: "<path-to-transcript-or-export>"
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

So a task written by `/debrief` is a **memory-transfer device anchored at the code**, not a symptom index. If a fresh session can't pick up the task and make verifiable progress without re-reading the transcript, the task is incomplete.

## When to use

- The user points at a transcript and says "find the bugs" / "what's still broken" / "trace this back to origin."
- The transcript itself shows victim-log patterns (multiple symptoms of the same kind — see **Phase 0: victim-log detection**).
- End of a long multi-turn session that surfaced findings but didn't track them.
- A session was compacted or interrupted mid-investigation and the open threads need to survive.

**Do NOT use for:**
- Live session summarization with no file (that's `/recap`).
- Listing problems without creating tasks (that's `/top-problems`).
- A multi-session chain analysis (use `/retro` — it calls `/debrief`'s `debrief_core` for the per-session extraction step).

## Two surfaces of /debrief

`/debrief` is two surfaces of the same shared logic. The **skill** is invoked manually with `/debrief <file>` and produces findings on demand. The **hook** is the `SessionEnd_debrief_reflect.py` script wired to Claude Code's `SessionEnd` event and produces findings automatically at every session close. Both share the same `__lib__/debrief_core.py` state machine, the same `assets/opportunity_task_template.md` schema, and the same `__lib__/dream_state.py` for cross-session idempotency. Findings from both surfaces land in the same artifacts directory; the user reviews and promotes them the same way.

## The investigator loop

The skill's body is **a loop, not a pipeline**. Each finding is the unit of work; each iteration walks one layer closer to the origin. The bundled state machine `__lib__/debrief_core.py` enforces the discipline; the LLM supplies the human judgment (read files, classify, recurse).

The full Phase 0 → Phase 9 diagram lives in [`references/loop-diagram.md`](references/loop-diagram.md). Read it before invoking the loop.

## Bundled components

| File | Role |
|---|---|
| `__lib__/debrief_core.py` | The state machine + recursive loop. The LLM supplies `source_tree_resolver` and `layer_extractor` callbacks (Agent tool invocations); `debrief_core` enforces the state discipline and emits ready-to-task bodies. `--selfcheck` green. |
| `scripts/chunk_plan.py` | Chunk plan + theme-hint grep. |
| `scripts/debrief.py` | Driver (plan / validate / selfcheck modes). |
| `scripts/rename_tag.py` | Deterministic source-file rename. |
| `assets/task_template.md` | The 9-field cold-start task template (TLDR + 9 fields, lite/full split). |
| `references/extraction_prompt.md` | The paste-ready parallel-extraction prompt (Phase 1). |
| `references/task_writing_guide.md` | The 9-field rationale + grouping rule + decision-gate-first. |

## Scope boundaries

- **This skill writes tasks and renames one source file.** It does not implement fixes. If the user wants a fix implemented, say so and stop.
- **Confirm before mutating live state.** Phases 6/8 are side-effecting. State the plan (N creates, M updates, old → new filename) and proceed. Pause for confirmation if the rename target is outside Downloads or if the plan creates more than ~8 tasks.
- **Mark every cross-session claim with its evidence level.** `MUST RE-VERIFY` is mandatory for any claim the recursion couldn't reach verified-origin level on.
- **When recursion hits the budget without verifying origin, write the task with `MUST RE-VERIFY: <next-session-action>` so the breadcrumb tells the next LLM exactly where to pick up.**
- Per the global Destructive Action rules, confirm before deleting or overwriting anything other than the task tracker entries and the single source-file rename.

## The recursive investigator in 5 lines

A debriefer running `/debrief` does, in order: (1) `debrief.py plan --path <file>` to get chunks + theme hints, (2) `python debrief_core.py` with `layer_extractor` and `source_tree_resolver` callbacks that dispatch Agent tool sub-investigators per finding, (3) call `/truth` on every layer transition, (4) gap-analyze the resulting `WRITTEN` findings against `TaskList`, (5) TaskCreate each + invoke `rename_tag.py --apply`. The loop in (2) does the heavy lifting; everything else is plumbing.

`/debrief` and `/retro` share `debrief_core` — `/debrief` for files, `/retro` for session chains (it walks the chain first, then runs `debrief_core` per session, then aggregates). Same state machine, same victim-log detection, same /truth gate, same task template.