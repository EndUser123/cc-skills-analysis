# /debrief — Phase 0 to Phase 9 (the recursive investigator loop)

The full phase-by-phase loop is documented here, not in SKILL.md, because the
diagram itself is ~1,400 words and is only needed by a debriefer who is about
to run the skill end-to-end. SKILL.md references this file once; the
debriefer reads it before invoking the loop.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 0 — victim-log detection (debrief_core.detect_victim_log)            │
│   ≥1 symptom kind recurs ≥3 times OR ≥3 distinct symptom kinds each appear   │
│   → is_victim_log = True → bump recursion budget (max_layers 3→4, per-layer │
│   8→12). The output explicitly notes when this fires.                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1 — Ingest + extract (parallel chunked if large)                      │
│   python scripts/debrief.py plan --path <file>                              │
│   Driver emits chunk plan + theme hints + paste-ready extraction prompts.    │
│   Dispatch one Explore subagent per chunk; each returns initial findings    │
│   with: title, symptom_text, transcript-line citation, named files/symbols. │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2 — Recursive investigation (the loop)                                │
│   For each finding, run debrief_core.run() with:                             │
│     source_tree_resolver — LLM reads the cited file:line, returns           │
│       (file, line, explanation) for the candidate origin.                   │
│     layer_extractor      — for each LOCATED finding, asks the Agent tool to │
│       "where else does this code smell appear / what explains it?" and      │
│       returns (texts, sources) for child findings.                          │
│     truth_callable       — invokes /truth on every claim at every layer.    │
│                                                                             │
│   State machine per finding:                                                │
│     DISCOVERED → CLASSIFIED (via /friction category) → LOCATED → VERIFIED   │
│                 → WRITTEN.  No skip.  UNVERIFIED → recursion_exhausted.    │
│                                                                             │
│   Recursion budget: default 3 layers, 8 findings/layer. Victim-log          │
│   transcripts get 4 layers, 12 findings/layer.                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 3 — /friction classification (inside the loop)                         │
│   When a finding is classified as workflow friction (vs code defect),       │
│   invoke /friction's category taxonomy so the task body carries the right   │
│   classification. The local classify_with_friction() in debrief_core does   │
│   the easy routing; /friction handles the ambiguous cases.                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 4 — /truth verification (mandatory at every layer)                    │
│   For every finding at LOCATED, invoke /truth with:                         │
│     CLAIM:  <the finding's origin claim>                                    │
│     STATUS: VERIFIED | FALSE | PARTIAL | UNVERIFIED                          │
│     EVIDENCE: <file:line, command output, or "none provided">               │
│   UNVERIFIED blocks advancement. FALSE rewrites the finding (correction     │
│   goes into MUST RE-VERIFY). FALSE on a top-level finding is rare; FALSE on │
│   a deep recursion means we picked the wrong layer and the breadcrumb       │
│   flags it.                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 5 — Gap-analyze against the existing task list                         │
│   Call TaskList. For each WRITTEN finding from the loop:                    │
│     1. PARENT_TASK pipeline? → CREATE new task, set PARENT_TASK: #<id>.     │
│     2. Existing task literally covers it?   → UPDATE (append, never over).  │
│     3. Otherwise → CREATE standalone.                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 6 — Write tasks in the cold-start template                            │
│   The template is in assets/task_template.md (9 fields, TLDR on top).       │
│   Every finding's task body carries the causal chain as evidence:            │
│     TLDR: <origin line — what changes>                                       │
│     VERIFIED FACTS: <chain of layer L1, L2, L3 evidence with citations>     │
│     DISCRIMINATING TEST: <read origin_file:origin_line and confirm>          │
│   The chain is the proof. Without it, the task is a symptom.                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 7 — Validate BLOCKERS references                                      │
│   python scripts/debrief.py validate --existing-tasks <snap> --proposed X   │
│   Warns on dangling IDs and already-completed IDs.                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 8 — Tag the source file                                              │
│   python scripts/rename_tag.py --themes "<theme>:<id>,..." --path <src>     │
│   The themes + IDs come from the WRITTEN findings' PARENT_TASKs and the     │
│   breadcrumb meta-task.                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 9 — Report + breadcrumb                                               │
│   Output the victim-log verdict, the recursion tree per finding, the WRITTEN│
│   tasks, and the rename. Always create one breadcrumb task recording       │
│   (source file, date, finding IDs) so the next /debrief on the same file    │
│   finds it via TaskList and emits UPDATE, not CREATE.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why a loop, not a pipeline

A transcript is a victim log: by the time a symptom appears in the conversation,
the bug is already in the code. A pipeline (extract → list → write) produces
symptom-level tasks. A loop (classify → locate → verify → recurse) produces
origin-level tasks.

The state machine in `__lib__/debrief_core.py` enforces the discipline. The
LLM supplies two callbacks that cannot be encoded as deterministic logic:

- `source_tree_resolver(text)` — reads the cited file:line and decides where
  in the code the symptom originates. Returns `(file, line, explanation)`.
- `layer_extractor(parent)` — for each located finding, asks "where else
  does this code smell appear / what explains it?" and returns the next
  layer's `(texts, sources)`.

The recursion budget (default 3 layers, 8 findings/layer; 4 layers, 12
findings/layer for victim-log transcripts) bounds how far the loop walks.
When the budget hits without verifying the origin, the finding is yielded
with `recursion_exhausted=True` and the task body carries a `MUST RE-VERIFY`
note so the next LLM knows exactly where to pick up.

## When to escalate to /retro

`/debrief` is for a single transcript file. When the user has a *chain* of
sessions (multiple linked sessions, not one transcript), `/retro` walks the
chain via `/recap` first, then invokes `debrief_core.run()` per session with
the same state machine. `/debrief` and `/retro` share `debrief_core`; the
only difference is the input shape (file vs chain) and the output sink
(TaskCreate vs RNS-formatted).
