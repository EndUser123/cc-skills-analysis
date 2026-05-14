---
name: gto
description: "GTO v4.2 \u2014 Session-aware gap-to-opportunity analysis with RNS-compatible\
  \ output"
version: 4.2.0
triggers:
- /gto
- gap analysis
- find gaps
- gap to opportunity
category: analysis
enforcement: advisory
workflow_steps:
- Run deterministic analysis + session transcript analysis (orchestrator)
- Spawn gap reviewer subagent for structured reasoning beyond detectors
- Re-run orchestrator to merge gap reviewer results
- Display findings in RNS domain-grouped format with Do ALL footer
required_artifacts:
  - ".claude/.artifacts/{terminal_id}/gto/outputs/artifact.json"
  - ".claude/.artifacts/{terminal_id}/gto/gap_reviewer_result.json"
response_requirements:
  format: "RNS domain-grouped with Do ALL footer"
  must_have:
    - "RNS|D| markers for domain sections"
    - "RNS|Z| marker for footer"
    - "gap_reviewer_result.json merged into final output"
contract_type: workflow-execution
---

# GTO v4.2 — Session-Aware Gap-to-Opportunity Analysis

## Overview

GTO analyzes the current session's work — what was discussed, what was attempted, what remains incomplete — and produces RNS-compatible findings. It reads chat transcripts, handoff files, and session goals rather than doing heavy codebase scanning (that's /code, /test, /diagnose's job).

## Execution Directive

### Step 1: Run Session-Aware Analysis

```bash
cd "P:\\\\\\packages/cc-skills-analysis" && python -m skills.gto.orchestrator --terminal-id "console_${WT_SESSION}" --session-id "$CLAUDE_SESSION_ID" --root .
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
ARTIFACTS_ROOT="${CLAUDE_ARTIFACTS_ROOT:-P:\\\\\\.claude/.artifacts}"
test -f "$ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_handoff.json" && echo "GAP_REVIEW_NEEDED" || echo "NO_GAP_REVIEW"
```

If `GAP_REVIEW_NEEDED`, spawn a subagent:

```python
Agent(
    subagent_type="general-purpose",
    description="GTO gap reviewer",
    prompt="""You are a gap-to-opportunity reviewer. You receive pre-populated detector evidence and produce a structured review.

Read the handoff file at: $ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_handoff.json

The handoff JSON contains:
- detected_facts: concrete observations from deterministic detectors
- signals_absent: detectors that ran but found nothing (absence as evidence)
- session_context: terminal_id, session_id, git_sha, files edited this session
- findings: current findings from the deterministic pipeline

Produce a JSON object with two fields and write it to: $ARTIFACTS_ROOT/$WT_SESSION/gto/gap_reviewer_result.json

1. "review": an object with these sections:
   - "facts": list of concrete observations grounded in the detector evidence. Each entry is {"claim": "...", "source": "detector_name or file:line"}
   - "inferences": list of hypotheses about failure modes or friction points. Each entry is {"hypothesis": "...", "confidence": "low|medium|high", "evidence": "what supports this"}
   - "unknowns": list of important questions that cannot be answered from the evidence. Each entry is {"question": "...", "why_it_matters": "..."}
   - "recommendations": list of specific next actions, ranked by impact. Produce as many as the evidence supports. Each entry is {"action": "...", "goal": "...", "assumption": "...", "rationale": "..."}

2. "findings": a JSON array of any NEW gaps you discovered that are NOT already in the input findings, following the standard finding schema:
   {"id": "GAPR-{domain}-{number}", "title": "...", "description": "...", "domain": "...", "gap_type": "...", "severity": "...", "action": "realize", "priority": "...", "evidence": [...]}

3. "weakest_assumption": the single assumption most likely to be wrong, with:
   {"assumption": "...", "if_wrong": "...", "mitigation": "...", "verification_status": "verified|unverifiable|partially_confirmed"}

Rules:
- Do not duplicate findings already present in the input
- Prefer issues predictable from system structure (overlapping validators, mode flags, format constraints)
- Do not propose large refactors without a concrete pain point from the evidence
- Mark confidence honestly — do not inflate inferences to facts
- If the session was exploratory with no clear trajectory, say so rather than forcing predictions
- Frame recommendations as actions the user can take, not obligations""",
)
```

After the subagent completes, re-run the orchestrator to merge the gap reviewer results:

```bash
cd "P:\\\\\\packages/cc-skills-analysis" && python -m skills.gto.orchestrator --terminal-id "console_${WT_SESSION}" --session-id "$CLAUDE_SESSION_ID" --root .
```

The second run reads `gap_reviewer_result.json` and merges its findings into the final artifact.

### Step 1.6: Additional Agent Enrichment (Optional)

The gap reviewer is the only mandatory agent. The remaining agents are optional enrichment — spawn them only if the user requests deeper analysis or if the gap reviewer identifies gaps that need further validation.

**Optional agents** (spawn sequentially if needed):

| Agent | Handoff | Result | Purpose |
|-||--||
| Domain Analyzer | `domain_analyzer_handoff.json` | `domain_analyzer_result.json` | Domain-specific health assessments |
| Findings Reviewer | `findings_reviewer_handoff.json` | `findings_reviewer_result.json` | Validate severity, reject false positives |
| Action Normalizer | `action_normalizer_handoff.json` | `action_normalizer_result.json` | Normalize into canonical RNS actions |
| Session Reviewer | `session_reviewer_handoff.json` | `session_reviewer_result.json` | Classify ambiguous session outcomes |

If any optional agents run, re-run the orchestrator afterward to merge their results.

### Step 2: Display Results

Read the artifact:
```bash
cat ".claude/.artifacts/{terminal_id}/gto/outputs/artifact.json"
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
- Footer: `0 — Do ALL Recommended Next Actions (N items)`
- No markdown fences around the RNS output

### Step 2.5: Forward-Looking Opportunity Analysis + Self-Reflection

After rendering the deterministic findings, produce a structured gap-to-opportunity review. This is now partially automated via the **Gap Reviewer** (Step 1.5) which receives pre-populated detector evidence and produces a FACT/INFERENCE/UNKNOWN/RECOMMENDATION review plus any new findings.

**If the Gap Reviewer ran successfully** (check `gap_reviewer_result.json`), incorporate its review into the display. The review appears as a structured section after the RNS findings.

**If the Gap Reviewer did not run** (first pass, no agent results yet), perform the analysis manually based on these signals:

| Signal | What to notice |
|--|-|
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
5. **Weakest assumption challenge**: *Which assumption am I MOST confident about that I HAVEN'T verified?* What would happen if it is wrong? What's the smallest check to falsify it?

For each predicted next action, render it as a `realize` action item in the RNS output with:
- **Specific description**: not "add tests" but "write integration tests for agent handoff/result round-trip in domain_analyzer.py"
- **Confidence indicator**: HIGH (dependency chain, explicitly deferred), MEDIUM (trajectory pattern), LOW (speculative)
- **Evidence**: cite the transcript turn or finding that supports the prediction

Display order:
1. **Signals observed** — list each signal detected in the transcript with the specific evidence (turn number, finding ID, file reference)
2. **Predicted opportunities** — the actions that follow from those signals, rendered as RNS `realize` items
3. Evidence precedes prediction, not the reverse — the reader should see the reasoning before the recommendation

Rules:
- Do NOT surface predictions that duplicate existing findings (those already appear as gaps)
- Prefer 3-5 high-specificity predictions over 10 generic ones
- If the session was exploratory with no clear trajectory, say so rather than forcing predictions
- Frame predictions as opportunities the user can act on, not obligations

## Session Data Sources

GTO reads from session-scoped sources (not global git state):

| Source | Purpose |
|--||
| `identity.json` | Hook-captured session_id, transcript_path, cwd |
| `session_registry.jsonl` | Terminal-scoped session chain history |
| `~/.claude/projects/*.jsonl` | Chat transcripts (tool call extraction, goal/outcome detection) |
| `.claude/.artifacts/{terminal_id}/gto/carryover.json` | Persisted findings across runs |
| `.claude/.artifacts/{terminal_id}/gto/*_handoff.json` | Agent input files |
| `.claude/.artifacts/{terminal_id}/gto/*_result.json` | Agent output files |

## Agent System Prompts

Agent prompts are defined in `skills/gto/agents/prompts.py`:

| Agent | Prompt Constant | Purpose |
|-|-||
| Domain Analyzer | `DOMAIN_ANALYZER_SYSTEM` | Enrich findings with domain-specific health assessments |
| Findings Reviewer | `FINDINGS_REVIEWER_SYSTEM` | Validate severity, reject false positives, dedupe |
| Action Normalizer | `ACTION_NORMALIZER_SYSTEM` | Normalize into canonical RNS action items |
| Session Reviewer | (in session_reviewer.py) | Classify ambiguous session outcomes |
| Gap Reviewer | `GAP_REVIEW_SYSTEM` | Structured FACT/INFERENCE/UNKNOWN/RECOMMENDATION review with context injection |

## Gap-to-Skill Routing

Findings are automatically routed to owning skills:

| Gap Type | Routes To |
|-|--|
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
