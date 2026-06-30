# Task Writing Guide

Read this before writing the first task of a debrief. It explains *why* the template
fields exist and the grouping rules that make the task set usable by a cold-start LLM.

## The core principle

A task written by `/debrief` is a **memory-transfer device**, not a reminder. The next
LLM has zero session memory. If it can't pick up the task and make verifiable progress
without re-reading the transcript, the task is incomplete.

## Grouping: one task per change-unit, not per atomic issue

Resist "one task per finding." Group findings into the smallest set where each task
**ships and verifies as a unit**. Three fixes that live in one pipeline and prove out
with one test are ONE task with sub-bullets — not three tasks that each look independent
but actually can't be verified alone.

Why: atomic tasks force the next LLM to re-read the same shared evidence for each one,
and they let a secondary-cause fix get shipped before the primary-cause fix (the classic
"shipped the wrong answer" failure). A change-unit task carries its own completion gate,
which makes that impossible.

### Decision-gate-first

If the *value* of a body of work is unproven, create a cheap decision-gate task first
("measure whether anyone actually queries this DB") and `blockedBy` the expensive
pipeline tasks on it. This stops follow-on LLMs from investing in infrastructure nobody
uses. The decision gate is almost always the highest-ROI task in the set.

## Update vs Create (gap analysis)

**Always call `TaskList` before creating anything.** For each finding:

- If an existing task already covers it → **UPDATE**: append a dated section with the new
  evidence, dead-ends, and line citations. Never overwrite — append.
- Only if nothing covers it → **CREATE**.

Duplicates are worse than gaps: the next LLM can't find work that lives in two places.
When uncertain, update.

## The eight fields, and why each exists

| Field | Why it exists |
|-------|---------------|
| **TITLE** | Names the change, not the symptom. A scanner of the task list should know what gets built. |
| **PROBLEM** | One sentence of user-facing problem. Anchors the task to a real need, not an implementation detail. |
| **VERIFIED FACTS** | Citations (file:line + transcript line). The only thing that stops a guess from becoming ground truth. |
| **MUST RE-VERIFY** | Claims carried from the session that were NOT re-confirmed this run. Explicit untrustworthiness beats silent assertion. |
| **DEAD ENDS** | Approaches tried that failed or were the wrong cause. Saves the next LLM from re-walking the wrong premise — usually the highest-value field. |
| **DISCRIMINATING TEST** | The one command whose output says fixed/not-fixed. Definition of done in miniature; enforces the global "claim verification" rule at task level. |
| **DEFINITION OF DONE** | Concrete, runnable, gated. "Test X passes with output Y", not "fixed". |
| **BLOCKERS** | Task IDs or external facts that gate this. Lets you emit the dependency graph. |
| **BLAST RADIUS** | What it touches, reversibility, safety. Surfaces live-DB / FK-trap / flag-flip risks before someone trips them. |

## Dependency wiring

Create blocker and decision-gate tasks **first** so you can reference their IDs, then
set `blockedBy` on the tasks they gate. Emit the result as a small graph in the final
report — it tells the next LLM the order to attack:

```
#942 (decision-gate) ─┐
                      ├─► #918 (pipeline work)
#943 (blocker)       ─┼─► #917 (work needing runtime proof)
#944 (sub-blocker)   ──► #939
#945 (cleanup)        standalone
```

## Anti-patterns to refuse

- **"Background narrative" field** — invites drift (the 2.7 GB-style misreport). Don't
  add one; the cited VERIFIED FACTS are the background.
- **Pasting the full transcript path into every task** — one pointer in the report is
  enough. The line citations already locate the evidence.
- **A task with no DISCRIMINATING TEST** — if you can't name the command that proves it
  fixed, the task isn't ready to ship to a cold-start LLM.
- **Marking a task complete on a fix you couldn't run** — unverifiable "done" is the
  failure mode this whole skill exists to prevent.
