---
name: friction
description: Detect interaction friction and workflow automation opportunities from chat history and session evidence.
version: 2.0.0
status: stable
category: analysis
enforcement: advisory
triggers:
  - /friction
  - "friction analysis"
  - "workflow friction"
  - "what could be automated"
  - "manual steps"
aliases:
  - /friction
suggest:
  - /retro
  - /recap
---

# /friction — Interaction & Workflow Friction Detector

Detect two categories of friction: LLM interaction problems (errors, corrections, confusion) and workflow automation gaps (repeated manual steps, missing automations, commands that should be hooks).

Works standalone via `/friction` or embedded as a step within `/retro`.

## When to Use

- `/friction` — standalone analysis of recent friction
- Embedded in `/retro` between `/gto` and `/ideas`
- End of session: "what friction did we hit?"
- Investigating repeated manual steps or corrections

## Detection Modes

### Mode 1: Interaction Friction

Search chat history for correction patterns, errors, and LLM mistakes.

**Pattern markers**:
- "I disabled hooks" — Hook system friction
- "You are confused" — Context loss
- "enterprise bloat" — Solo-dev mismatch
- "wrong directory" — Path issues
- "errors in another terminal" — Cross-terminal contamination
- "you didn't call Skill" — Skill dispatch failures
- "old data", "cached data" — Stale data
- "same problem again" — Repeated problems without learning

**Categories**:

| Category | Root Cause |
|----------|-----------|
| Hook Contract Friction | Enforcement not distinguishing user-directed from autonomous work |
| Context Loss | Agents not reading conversation history before acting |
| Pattern Mismatch | Enterprise/team patterns in solo-dev environment |
| Path Issues | No path validation, inconsistent separators |
| Cross-Terminal | Shared state without terminal isolation |
| Skill Dispatch | Commands not triggering Skill() calls |
| Stale Data | Skills using caches instead of live reads |
| Repeated Problems | No learning loop from corrections |

### Mode 2: Workflow Friction

Scan session evidence and chat patterns for automation opportunities.

**Detection signals**:
- Same command run 3+ times in a session — candidate for a hook or skill
- Manual verification step repeated for each file — candidate for batch automation
- User explicitly approves the same category of action repeatedly — candidate for auto-allow
- Gaps between what skills produce and what user needs to do manually (copy results, reformat, re-run)
- Multi-step manual sequences that always appear in the same order — candidate for a workflow skill
- Manual cleanup after automated operations — missing post-processing in the automation

**Categories**:

| Category | Signal |
|----------|--------|
| Repeated Commands | Same bash/command invoked 3+ times |
| Manual Approval Loops | User approves same category repeatedly |
| Missing Automation | Deterministic steps done manually |
| Skill Output Gaps | User reformats or adapts skill output |
| Cleanup After Automation | Manual fixes after automated runs |
| Orphaned Work | Results produced but never consumed downstream |

## Analysis Workflow

### Phase 1: Gather Evidence

Use `/search` for chat history, or analyze conversation context directly when embedded in `/retro`:

```
/search "recent errors"              # Interaction friction
/search "repeated commands"           # Workflow friction
```

When embedded in `/retro`, use the already-gathered recap and gap context — do not re-run `/search`.

### Phase 2: Detect Patterns

For **interaction friction**, search for correction markers (errors, wrong approaches, user redirects).

For **workflow friction**, scan for:
- Repeated tool calls with same patterns
- Manual steps between automated ones
- User doing work that a hook or skill could handle

### Phase 3: Categorize and Score

For each finding, assign:
- **Category**: Which friction type (from tables above)
- **Frequency**: How many times it occurred in the analysis window
- **Automation potential**: HIGH (clear deterministic fix), MED (needs judgment), LOW (needs human input)
- **Effort to fix**: Estimated complexity of eliminating the friction

### Phase 4: Output Findings

## Output Format

### Standalone Mode

```
FRICTION FINDINGS:

Interaction Friction:
  1. [category] "[quote]" (N occurrences, effort: HIGH)
  2. [category] "[quote]" (N occurrences, effort: MED)

Workflow Friction:
  1. [category] [description] (N occurrences, automation: HIGH)
  2. [category] [description] (N occurrences, automation: MED)

Top 3 Recommendations:
  1. [specific fix] — eliminates [N] manual steps per session
  2. [specific fix] — prevents [category] friction
  3. [specific fix] — automates [description]
```

### Embedded Mode (within /retro)

Produce compact output for the FRICTION section:

```
FRICTION: [top 3 friction points]
  1. [description] — [category: automation/manual/repeated]
  2. [description] — [category]
  3. [description] — [category]
```

## Phase Gates

**GATE 1 (STOP after Phase 1: Gather Evidence)**: Before moving to Phase 2 (Detect Patterns), verify:
- Evidence source identified (chat history, session context, or embedded from /retro)
- Analysis window defined
- No duplicate re-gathering if embedded in /retro

If gate fails: gather evidence before proceeding.

**GATE 2 (STOP after Phase 2: Detect Patterns)**: Before moving to Phase 3 (Categorize and Score), verify:
- Interaction friction patterns detected (at least one category identified)
- OR workflow friction patterns detected (at least one automation candidate identified)
- Pattern citations from evidence present

If gate fails: continue detecting patterns until at least one finding is ready for scoring.

**STOP between phases**:
- Phase 1 (Gather) → Phase 2 (Detect): Must collect evidence before pattern detection
- Phase 2 (Detect) → Phase 3 (Categorize): Must detect patterns before categorizing and scoring
- Phase 3 (Categorize) → Phase 4 (Output): Must score before outputting findings

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

---

## Tips

1. Count occurrences — frequency determines priority
2. Quote directly from chat when available — evidence over inference
3. Distinguish interaction friction (LLM mistakes) from workflow friction (process gaps)
4. Every workflow friction finding should suggest a concrete automation (hook, skill, or config change)
5. When embedded in `/retro`, skip re-gathering evidence — use what upstream skills already collected
