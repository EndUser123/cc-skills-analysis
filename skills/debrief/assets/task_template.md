# Cold-Start Task Template

Copy this skeleton into every task description (created or updated). A task is done
when a fresh LLM — zero session memory — can pick it up and make verifiable progress
without re-reading the source transcript.

```
TLDR:           <3 lines max — the disciplined-task summary. See TLDR rule below.>
TITLE:          <imperative, names the shipping change, not the symptom>
TASK_KIND:      <full | lite — see Scale rule below; default full>
PROBLEM:        <one sentence — the user-facing problem this solves>
VERIFIED FACTS: <file:line + probe output + transcript line, each with a source tag>
                e.g. "history.jsonl = 3.2 MB not 2.7 GB (wc, transcript L4991)"
MUST RE-VERIFY: <claims carried from the session that were NOT re-confirmed this run>
                e.g. "row count not re-verified — Bash was down (transcript L8736)"
GENERALIZABLE_PRINCIPLE: <the generalizable invariant from the fix path, if /truth verified one; else omit>
APPLIES_TO:     <coding|research|writing|debugging|workflow|tool|unknown — domain the principle covers>
DEAD ENDS:      <approaches already tried that failed or were the wrong cause — do not repeat>
                e.g. "DB-path repoint was SECONDARY cause; source-format is primary (L5094)"
PARENT_TASK:    <#<id> if this task shares a pipeline with an existing one — see Update vs Create>
DISCRIMINATING TEST: <the ONE command whose output says fixed / not-fixed>
                e.g. "reindex → read N, skipped 0, ingested N; SELECT MAX(timestamp) > 0"
DEFINITION OF DONE: <concrete, runnable, gated — test name + expected output>
BLOCKERS:       <task IDs or external facts that gate this; "none" if clear — IDs are validated>
BLAST RADIUS:   <what it touches, reversibility, safety notes>
NEXT STEP:      <the first file:line to touch>
```

## Field notes

- **TLDR** is the FIRST three lines after the title (or the first sentence if the body
  is paragraph-style). Format: one line for what changes, one line for the discriminating
  test, one line for the definition of done. The next LLM scanning the task list should
  be able to act on TLDR alone in 80% of cases — the rest of the fields are the evidence
  dossier, not the headline. Tasks that hide the discriminating test under eight lines
  of facts train the next LLM to skip the task.
- **TASK_KIND** is `full` for any change-unit task (the default — fields populated below);
  `lite` for a trivial single-step finding. Lite tasks carry TLDR + TITLE + DISCRIMINATING
  TEST + DEFINITION OF DONE. They are evaluated by the same grader (so the eval can detect
  mixing the two); if a "lite" task turns out to need more fields when the next LLM picks
  it up, **promote it to full and update the description** (don't pad an empty DEAD ENDS).
- **VERIFIED FACTS vs MUST RE-VERIFY** is the most important split. It is what stops a
  prior session's guess from graduating into an unmarked assertion. If you did not
  re-run the check this session, the claim goes in MUST RE-VERIFY, not VERIFIED FACTS.
- **DEAD ENDS** is the field that saves the next LLM the most time. Wrong premises get
  re-walked precisely because the wrong turn was never recorded. Be specific about *why*
  it was wrong, with the transcript line.
- **PARENT_TASK** is `#<id>` when the new task shares a *pipeline* (not just a surface) with
  an existing task. Example: a new sub-defect in #918's ingestion pipeline → PARENT_TASK: #918.
  This is the relationship the next LLM needs to find "the work under #918." Tasks without
  a parent leave the next LLM to rediscover the relationship.
- **DISCRIMINATING TEST** is the definition of done in miniature. If you can't name the
  single command that distinguishes fixed from not-fixed, the task isn't ready.
- **BLOCKERS** references are validated by `debrief.py validate` against the live
  task tracker snapshot. A dangling or already-completed reference is a WARN, not a
  silent pass — fix or drop it before committing the task.
- **TITLE** names the change ("repoint CHS ingest source to projects/**/*.jsonl"),
  not the symptom ("fix CHS"). Someone scanning the task list should know what gets built.

## For UPDATE (not create)

Do not overwrite the existing description. Append a dated section:

```
=== <YYYY-MM-DD> debrief update — <source file tag> ===
<new VERIFIED FACTS / DEAD ENDS / line citations discovered this run>
<updated DISCRIMINATING TEST or DEFINITION OF DONE if the run refined them>
GATED BY: #<id> (if a new blocker was identified)
```
