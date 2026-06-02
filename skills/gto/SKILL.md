---
name: gto
description: "GTO v4.4 — Session-aware gap-to-opportunity analysis with execution-contract runtime. Reads session transcripts to produce RNS-formatted findings. Uses haiku model for gap reviewer and merge-only re-runs for speed. Contract: workflow-execution with artifact as completion object."
version: "4.4.0"
triggers:
  - "/gto"
category: analysis
contract_type: workflow-execution

# Hard gate: Bash is the first tool to invoke the orchestrator.
# All other tools are blocked until the orchestrator runs.
allowed_first_tools:
  - Bash

# Artifact is the single completion criterion for workflow-execution.
# The skill-guard runtime tracks this via execution-state.json.
required_artifacts:
  - ".claude/.artifacts/{terminal_id}/gto/outputs/artifact.json"

# Tools available after orchestrator starts.
# Bash: orchestrator itself and sub-shells.
# Read/Grep/Glob: session and artifact analysis.
# Agent: gap reviewer and enrichment subagents.
# Skill/WebSearch/WebFetch: investigation.
# Write/Edit: artifact and session-scoped files only.
allowed_tools_now:
  - Bash
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - Skill
  - Agent
  - WebSearch
  - WebFetch
  - Write
  - Edit
  - Task
---

### Operating Contract

You are working inside a repository where GTO implements a full gap‑analysis and verification pipeline. Your job is to work **within** that pipeline, not to invent parallel workflows or formats.

- Treat the GTO orchestrators, models, detectors, hooks, and artifact writers as the **contract of record** for how gap analysis, verification, and session state work. When you change them, you must preserve existing JSON shapes, run‑state phases, and RNS machine output unless explicitly asked to change the contract.
- For any change that touches GTO quality gates, gap reviewer wiring, or their tests, use the automated quality flow instead of manually sequencing prompts. The canonical flow is: (1) implementer step, (2) pytest for `gto` suite, (3) verifier step, (4) gate on `FINALVERDICT.status`. Use `gto/orchestrator.py` as the single entry point.
- When adding new behavior, prefer new deterministic detectors in the existing `lib/` modules that feed the orchestrator, or new verification logic that uses the existing `GTOArtifact` structure and RNS machine output — rather than new top‑level artifacts, file formats, or one‑off drivers.
- The agents (domain analyzer, findings reviewer, action normalizer, gap reviewer, session reviewer) have stable prompts and JSON schemas. You may change prompts and tests freely, but you must not change agent I/O schemas unless explicitly requested and all consumers are updated together.
- Hooks (PreToolUse, PostToolUse, SessionStart, Stop) are boundary layers, not orchestration systems. Hook changes should focus on validating artifacts and run state, and must not bypass the orchestrator, mutate artifacts by hand, or introduce new hidden state.
- Do **not** assume utilities like `stripscaffoldingblocks`, turn‑mode routers, or per‑mode message schemas exist. If you need that behavior, implement it explicitly in shared modules rather than referencing unknown helpers.
- When in doubt, reuse existing detectors, orchestrator entry points, and artifact contracts. Enforce quality via the automated implement → pytest → verify → verdict flow rather than adding configuration layers or runner scripts.

# GTO v4.4 — Session-Aware Gap-to-Opportunity Analysis (Contract Runtime)

## Overview

GTO analyzes the current session's work — what was discussed, what was attempted, what remains incomplete — and produces RNS-compatible findings. It reads chat transcripts, handoff files, and session goals rather than doing heavy codebase scanning (that's /code, /test, /diagnose's job).

## Execution Directive

### Step 1: Run Session-Aware Analysis

```bash
cd "P://packages/cc-skills-analysis" && python -m skills.gto.orchestrator --terminal-id "$WT_SESSION" --session-id "$CLAUDE_SESSION_ID" --root .
```

This runs:
1. **Deterministic detectors** — .git presence, README existence
2. **Transcript resolution** — from identity.json (hook-captured, no scanning)
3. **File edit extraction** — Edit/Write tool calls from session transcript
4. **Session chain** — from session registry (terminal-scoped, no globbing)
5. **Session goal detection** — extracts stated goals from user messages
6. **Session outcome detection** — finds uncompleted goals, open questions, deferred items
7. **Completion filtering** — removes outcomes that were actually completed
8. **Carryover resolution** — marks findings as resolved if files were edited
9. **Agent handoff writing** — writes handoff files for enrichment agents
10. **Agent result reading** — merges any available agent enrichment results
11. **Merge, dedupe, route** — combine all sources, route to owning skills

Artifacts written to `.claude/.artifacts/{terminal_id}/gto/`.

### Step 1.5: Gap Reviewer (Mandatory)

After the orchestrator writes its artifact, spawn the **Gap Reviewer** subagent. This is NOT optional — it is the only agent that can reason beyond deterministic detectors (producing facts, inferences, unknowns, and recommendations from the accumulated evidence).

```bash
ARTIFACTS_ROOT="${CLAUDE_ARTIFACTS_ROOT:-P://.claude/.artifacts}"
test -f "$ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_handoff.json" && echo "GAP_REVIEW_NEEDED" || echo "NO_GAP_REVIEW"
```

If `GAP_REVIEW_NEEDED`, check whether the findings warrant a full agent review. **Skip the gap reviewer** when all deterministic findings are trivial — defined as fewer than 3 findings AND all findings have `severity: "low"`. In that case, print "GAP_REVIEW_SKIPPED: trivial findings only" and proceed directly to Step 2.

Otherwise, spawn a subagent with the faster haiku model:

```python
Agent(
    subagent_type="general-purpose",
    model="haiku",
    description="GTO gap reviewer",
    prompt="""You are a gap-to-opportunity reviewer. You receive pre-populated detector evidence and produce a structured review.

Read the handoff file at: $ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_handoff.json

The handoff JSON contains:
- detected_facts: concrete observations from deterministic detectors
- signals_absent: detectors that ran but found nothing (absence as evidence)
- session_context: terminal_id, session_id, git_sha, files edited this session
- findings: current findings from the deterministic pipeline

Produce a JSON object with two fields and write it to: $ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_result.json

IMPORTANT: Use the Write tool to write the result file. Do NOT use `python -c` with inline JSON — nested quoting breaks on Windows/bash. If the Write tool reports a CROSS-WORKTREE error, use Bash instead: write content to a temp variable and call `python -c "from pathlib import Path; Path('$ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_result.json').write_text(content, encoding='utf-8')"`.

1. "review": an object with these sections:
   - "facts": list of concrete observations grounded in the detector evidence. Each entry is {"claim": "...", "source": "detector_name or file:line"}
   - "inferences": list of hypotheses about failure modes or friction points. Each entry is {"hypothesis": "...", "confidence": "low|medium|high", "evidence": "what supports this"}
   - "unknowns": list of important questions that cannot be answered from the evidence. Each entry is {"question": "...", "why_it_matters": "..."}
   - "recommendations": list of specific next actions, ranked by impact. Produce as many as the evidence supports. Each entry is {"action": "...", "goal": "...", "assumption": "...", "rationale": "..."}

2. "findings": a JSON array of any NEW gaps you discovered that are NOT already in the input findings, following the standard finding schema:
   {"id": "GAPR-{domain}-{number}", "title": "...", "description": "...", "domain": "...", "gap_type": "...", "severity": "...", "action": "realize", "priority": "...", "evidence": [...]}

Rules:
- Do not duplicate findings already present in the input
- Prefer issues predictable from system structure (overlapping validators, mode flags, format constraints)
- Do not propose large refactors without a concrete pain point from the evidence
- Mark confidence honestly — do not inflate inferences to facts
- If the session was exploratory with no clear trajectory, say so rather than forcing predictions
- Frame recommendations as actions the user can take, not obligations""",
)
```

After the subagent completes, run a **merge-only** pass (skips all detectors, just merges agent results into the artifact):

```bash
cd "P://packages/cc-skills-analysis" && python -m skills.gto.orchestrator --merge-only --terminal-id "$WT_SESSION" --session-id "$CLAUDE_SESSION_ID" --root .
```

The merge-only pass reads `gap_reviewer_result.json` and incorporates its findings without re-running detectors.

### Step 1.6: Additional Agent Enrichment (Optional)

The gap reviewer is the only mandatory agent. The remaining agents are optional enrichment — spawn them only if the user requests deeper analysis or if the gap reviewer identifies gaps that need further validation.

**Optional agents** (spawn sequentially if needed):

| Agent | Handoff | Result | Purpose |
|-------|---------|--------|---------|
| Domain Analyzer | `domain_analyzer_handoff.json` | `domain_analyzer_result.json` | Domain-specific health assessments |
| Findings Reviewer | `findings_reviewer_handoff.json` | `findings_reviewer_result.json` | Validate severity, reject false positives |
| Action Normalizer | `action_normalizer_handoff.json` | `action_normalizer_result.json` | Normalize into canonical RNS actions |
| Session Reviewer | `session_reviewer_handoff.json` | `session_reviewer_result.json` | Classify ambiguous session outcomes |

If any optional agents run, re-run with `--merge-only` afterward to merge their results.

### Step 2: Display Results

**WAIT for Gap Reviewer before displaying.** Do NOT render RNS output until Step 1.5 (Gap Reviewer) has completed and the orchestrator has merged its results. The "0 — Do ALL Recommended Next Actions (N items)" footer must be the LAST line shown — predicted opportunities come BEFORE it, not after.

Read the artifact with the **Read tool** (not `cat` or `python -c`):
```
Read file: .claude/.artifacts/{terminal_id}/gto/outputs/artifact.json
```

Render the findings using the **RNS display format**. Read the canonical format spec before rendering:

```
Read file: skills/gto/__lib/machine_render.py
```

This module defines the domain map, emoji assignments, subletter numbering, and the full RNS pipe-delimited machine format. Use the same domain groupings and emoji when rendering the human-readable display.

The display must follow the `/rns` output format:
- Domain-grouped sections with emoji headers: `{num} {emoji} {DOMAIN} ({count})`
- Domain-numbered items: `{num}{letter} [{action}/{priority}] Description @ file:line`
- Sort within domain: recover > prevent > realize, then CRITICAL > HIGH > MEDIUM > LOW
- **The "0 — Do ALL Recommended Next Actions (N items)" footer is the LAST line** — predicted opportunities appear BEFORE it
- No markdown fences around the RNS output

### Step 2.5: Forward-Looking Opportunity Analysis + Self-Reflection

**This section appears BEFORE the final "0 — Do ALL" footer.**

After rendering the deterministic findings, produce a structured gap-to-opportunity review. This is now partially automated via the **Gap Reviewer** (Step 1.5) which receives pre-populated detector evidence and produces a FACT/INFERENCE/UNKNOWN/RECOMMENDATION review plus any new findings.

**If the Gap Reviewer ran successfully** (check `gap_reviewer_result.json`), incorporate its review into the display. The review appears as a structured section between the RNS findings and the predicted opportunities.

**If the Gap Reviewer did not run** (first pass, no agent results yet), perform the analysis manually based on these signals:

| Signal | What to notice |
|--------|----------------|
| **Incomplete work** | Features half-implemented, functions with TODO bodies, tests commented out, branches unmerged |
| **Dependency chains** | A was completed but B depends on A and wasn't started — B is the natural next step |
| **Deferred decisions** | "We'll deal with that later", "skip for now", "not in scope" — these are future work queued by the user |
| **Work trajectory** | The pattern of what was done implies what comes next (wired agents → test them; created module → document it) |
| **Avoidance signals** | Something mentioned once then skirted around — usually the hard or uncertain parts that will surface again |
| **Recurring themes** | Same concern raised across multiple turns or sessions — high-confidence prediction it will come up again |

**Self-reflection prompts (open-ended)** — use when the session involved building, fixing, or documenting a feature, system, or workflow:

1. **Goals / Functions / Outcomes audit**: For any documented capability, stated goal, or expected outcome: *Is it tested? How would we test for it? Is this reflected in unit, regression, and integration tests?* If testing is missing or partial: surface as a `realize` finding.
2. **Boundary uncertainty**: *What is the smallest discriminating check that would resolve remaining uncertainty?* Name the falsification condition — the specific counterexample or signal that would prove the recommendation wrong.
3. **Failure mode first**: *Before celebrating a fix, ask: what is the likely failure mode? What discriminating test would falsify it? Could this overfire?*
4. **Implementation vs capability**: *Is the current implementation telling us the true capability, or just one way it was built?* Challenge assumed limits that are actually just current-impl constraints.

Display order:
1. **RNS findings block** — domain-grouped, action-sorted, priority-sorted
2. **Gap Reviewer synthesis** (if available) — facts, inferences, unknowns, recommendations
3. **Predicted opportunities** — HIGH/MEDIUM/LOW confidence next actions derived from session evidence
4. **"0 — Do ALL Recommended Next Actions (N items)"** — final footer line

Rules:
- Do NOT surface predictions that duplicate existing findings (those already appear as gaps)
- Prefer 3-5 high-specificity predictions over 10 generic ones
- If the session was exploratory with no clear trajectory, say so rather than forcing predictions
- Frame predictions as opportunities the user can act on, not obligations

## Session Data Sources

GTO reads from session-scoped sources (not global git state):

| Source | Purpose |
|--------|---------|
| `identity.json` | Hook-captured session_id, transcript_path, cwd |
| `session_registry.jsonl` | Terminal-scoped session chain history |
| `~/.claude/projects/*.jsonl` | Chat transcripts (tool call extraction, goal/outcome detection) |
| `.claude/.artifacts/{terminal_id}/gto/carryover.json` | Persisted findings across runs |
| `.claude/.artifacts/{terminal_id}/gto/*_handoff.json` | Agent input files |
| `.claude/.artifacts/{terminal_id}/gto/*_result.json` | Agent output files |

## Agent System Prompts

Agent prompts are defined in `skills/gto/agents/prompts.py`:

| Agent | Prompt Constant | Purpose |
|-------|----------------|---------|
| Domain Analyzer | `DOMAIN_ANALYZER_SYSTEM` | Enrich findings with domain-specific health assessments |
| Findings Reviewer | `FINDINGS_REVIEWER_SYSTEM` | Validate severity, reject false positives, dedupe |
| Action Normalizer | `ACTION_NORMALIZER_SYSTEM` | Normalize into canonical RNS action items |
| Session Reviewer | (in session_reviewer.py) | Classify ambiguous session outcomes |
| Gap Reviewer | `GAP_REVIEW_SYSTEM` | Structured FACT/INFERENCE/UNKNOWN/RECOMMENDATION review with context injection |

## Gap-to-Skill Routing

Findings are automatically routed to owning skills:

| Gap Type | Routes To |
|----------|-----------|
| missingdocs | /docs |
| techdebt | /code |
| runtime_error, bug | /diagnose |
| security | /security |
| perf | /perf |
| invalidrepo | /git |
| session_* | Review and act |

## Artifact Location

All artifacts are terminal-scoped:
```
.claude/.artifacts/{terminal_id}/gto/
├── state/run_state.json
├── outputs/artifact.json
├── logs/failures.jsonl
├── carryover.json
├── domain_analyzer_handoff.json
├── domain_analyzer_result.json
├── findings_reviewer_handoff.json
├── findings_reviewer_result.json
├── action_normalizer_handoff.json
├── action_normalizer_result.json
├── session_reviewer_handoff.json
├── session_reviewer_result.json
├── gap_reviewer_handoff.json
└── gap_reviewer_result.json
```

## Verification

The stop hook verifies completion by checking:
1. State phase == "completed"
2. Artifact file exists with valid JSON
3. Machine output has RNS|D| and RNS|Z| markers
4. All expected artifacts are present

## Critical Rules

- Do NOT parse prose output for completion detection
- Use state-driven verification only
- Terminal-scoped artifacts prevent cross-terminal conflicts
- Session findings come from transcript analysis, not codebase scanning
- Heavy codebase analysis should be routed to /code, /test, /diagnose — not done by GTO
- The gap reviewer agent is mandatory — it provides reasoning beyond deterministic detectors
- Other agents (domain_analyzer, findings_reviewer, action_normalizer, session_reviewer) are optional enrichment
- Agent results are merged on the next orchestrator run, not inline
- Do NOT use `python -c` for artifact I/O — nested JSON quoting breaks on Windows/bash. Use the Read tool to read JSON artifacts and Write tool to write JSON results. Use pre-written scripts in `__lib/` for rendering.

## Phase Gates

**GATE 1 (STOP after Step 1: Run Orchestrator)**: Before moving to Step 1.5 (Gap Reviewer), verify:
- Orchestrator ran successfully
- Artifact file written to expected path
- Deterministic detectors completed
- Session goal/outcome detection completed

If gate fails: re-run orchestrator before spawning agents.

**GATE 2 (STOP after Step 1.5: Gap Reviewer)**: Before moving to Step 1.6 (Optional Agents) or Step 2 (Display), verify:
- Gap Reviewer completed (mandatory)
- gap_reviewer_result.json written
- Review findings incorporated into artifact

If gate fails: re-run gap reviewer before proceeding.

**GATE 3 (STOP after Step 2: Display Results)**: Before moving to Step 2.5 (Forward-Looking), verify:
- RNS|D| markers present in output
- RNS|Z| footer present
- Domain-grouped format correct

If gate fails: correct display format before self-reflection.

**STOP between generation (Steps 1-1.6) and validation (Steps 2-2.5)**:
- Steps 1-1.6: Run orchestrator, spawn gap reviewer, optional agents (generation)
- Steps 2-2.5: Display results, forward-looking analysis (validation)
- Do NOT display results until all agents complete and orchestrator merges their output

---

## Evidence-First Principles

### E1 — Evidence before claims
Before claiming code is absent, unchanged, or non-existent — search the codebase and verify with tools first. Claims of absence are only valid after confirmed Read/Grep/git failures.

### E4 — Investigate before asking
Do NOT answer without reading relevant source files first. Do not ask the user for information you can obtain yourself via Read, Grep, Bash, git, or available MCP tools.

### E5 — Anti-lazy escape hatch
Prohibited:
- "I assume", "I think", "probably" without tool verification
- Claiming something doesn't exist without confirmed tool failure
- Skipping evidence gathering because the answer seems obvious
