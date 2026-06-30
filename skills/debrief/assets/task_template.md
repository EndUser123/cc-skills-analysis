# Cold-Start Task Template

Copy this skeleton into every task description (created or updated). A task is done
when a fresh LLM — zero session memory — can pick it up and make verifiable progress
without re-reading the source transcript.

```
TITLE:          <imperative, names the shipping change, not the symptom>
PROBLEM:        <one sentence — the user-facing problem this solves>
VERIFIED FACTS: <file:line + probe output + transcript line, each with a source tag>
                e.g. "history.jsonl = 3.2 MB not 2.7 GB (wc, transcript L4991)"
MUST RE-VERIFY: <claims carried from the session that were NOT re-confirmed this run>
                e.g. "row count not re-verified — Bash was down (transcript L8736)"
DEAD ENDS:      <approaches already tried that failed or were the wrong cause — do not repeat>
                e.g. "DB-path repoint was SECONDARY cause; source-format is primary (L5094)"
DISCRIMINATING TEST: <the ONE command whose output says fixed / not-fixed>
                e.g. "reindex → read N, skipped 0, ingested N; SELECT MAX(timestamp) > 0"
DEFINITION OF DONE: <concrete, runnable, gated — test name + expected output>
BLOCKERS:       <task IDs or external facts that gate this; "none" if clear>
BLAST RADIUS:   <what it touches, reversibility, safety notes>
NEXT STEP:      <the first file:line to touch>
```

## Field notes

- **VERIFIED FACTS vs MUST RE-VERIFY** is the most important split. It is what stops a
  prior session's guess from graduating into an unmarked assertion. If you did not
  re-run the check this session, the claim goes in MUST RE-VERIFY, not VERIFIED FACTS.
- **DEAD ENDS** is the field that saves the next LLM the most time. Wrong premises get
  re-walked precisely because the wrong turn was never recorded. Be specific about *why*
  it was wrong, with the transcript line.
- **DISCRIMINATING TEST** is the definition of done in miniature. If you can't name the
  single command that distinguishes fixed from not-fixed, the task isn't ready.
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
