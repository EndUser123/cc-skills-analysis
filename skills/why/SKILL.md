---
name: why
description: Decision archaeology — trace backward through sessions to reconstruct why something exists, what caused it, and the reasoning chain behind it. NOT a debug tool — answers "why are we doing X?"
version: "1.0.0"
status: stable
category: analysis
triggers:
  - /why
---

# /why — Decision Archaeology

**Problem solved:** "I forgot why we're doing this. What caused it? What was the reasoning?"

This is NOT `/recap`. `/recap` tells you what happened chronologically. `/why` traces backward through decisions to reconstruct causal chains — who decided what, why, based on what assumptions.

## Workflow

### STEP 1: Parse the question

Extract the **topic** from the user's input. Strip the "/why" prefix and any question framing.

Classify the question type:

| Type | Pattern | Focus |
|------|---------|-------|
| **Decision chain** | `/why did we change X?`, `/why auth flow` | What decisions led to current state |
| **Existence rationale** | `/why do we have X?`, `/why does X exist?` | What pain point prompted X, what alternatives were considered, why this solution |
| **Self-referential** | `/why are we building a /why skill?` | Meta — trace the skill's own creation |
| **Open** | `/why` (no args) | Ask: "What topic do you want to trace?" |

| Input | Type | Topic |
|-------|------|-------|
| `/why auth flow` | Decision chain | auth flow decisions |
| `/why do we have nlm?` | Existence rationale | nlm |
| `/why are we building a /why skill?` | Self-referential | /why skill creation |
| `/why did we change the notebooklm skill?` | Decision chain | notebooklm skill changes |

### STEP 2: Gather evidence (search in parallel)

Run these data sources in parallel to find all mentions of the topic:

**Tier 1 — Primary (terminal-attributed, authoritative):**

1. **Session history** — `python "$CLAUDE_ROOT/skills\recap\scripts\recap_cli.py" recap`
   - Gets full session chain with problems/fixes/decisions per session
   - Terminal-attributed via `sessionId`/`session_chain_id`

2. **CKS knowledge** — `mcp__search-research__cks_search` with topic keywords
   - Prior decisions, feedback rules, lessons learned

3. **Memory files** — Search `C:\Users\brsth\.claude\projects\P--\memory\` for topic keywords
   - Project context, feedback rules, behavioral expectations

4. **CLAUDE.md + ADRs** — `Grep` for topic in `$CLAUDE_ROOT/CLAUDE.md` and `$__CSF_ROOT/arch_decisions\`
   - Architectural context and documented decisions

**Tier 2 — Supplementary (corroboration only, no terminal attribution):**

5. **Git log** — `git log --oneline --all --grep="{topic}" -20`
   - When changes were committed and what messages say
   - NOTE: Cannot attribute to specific terminal — use only to corroborate transcript evidence

6. **Git blame** — `git log -S "topic" --oneline` and `git log --follow -p -- {file}`
   - Who introduced changes and when (for file-level tracing)
   - NOTE: In multi-terminal environments, you cannot determine which terminal made which commit

### STEP 3: Extract causal markers

From gathered data, identify these signals:

**Decisions** (what was chosen):
- "decided to", "going with", "chose", "recommend", "use X instead of Y"
- User imperatives: "fix X", "add Y", "refactor Z"

**Triggers** (what caused the decision):
- Problem statements: "the issue is", "X doesn't work", "annoying pattern"
- External events: "nlm updated", "dependency changed", "security finding"

**Assumptions** (what the decision rests on):
- "assuming that", "if X then", "the expectation is"
- Implicit assumptions visible from context

**Corrections** (where reasoning changed):
- "actually", "wait", "hold on", "on second thought"
- User corrections: "no, not that", "that's not what I asked"

**Constraints** (what limited options):
- "can't do X because", "limited by", "must work with"
- Solo-dev constraints from CLAUDE.md

**For existence rationale questions, also extract:**

**Pain points** (what hurt before this existed):
- "annoying that", "wasting time on", "keep having to", "frustrating"
- Repeated manual actions that could be automated

**Solution selection** (why THIS solution vs alternatives):
- "considered X but went with Y because", "tried X, didn't work"
- Upstream tool features: "nlm skill install handles", "managed by external tool"

**Maintenance contract** (how it stays current):
- "run X to update", "managed upstream", "don't manually edit"
- Version pinning, update commands, freshness signals

### STEP 4: Reconstruct causal chain

Build backward from current state to origin:

```
Current State → Last Decision → What Triggered It → Earlier Decision → Original Need
```

For each link in the chain, identify:
- **Who**: User directive or AI recommendation?
- **What**: The specific decision made
- **Why**: The trigger/problem that motivated it
- **Based on**: What assumption or constraint
- **Changed by**: Any later corrections or overrides

### STEP 5: Surprise check (iterative drill-down)

After reconstructing the initial chain, examine each link for **surprise** — an answer that doesn't fully explain the link above it, or that raises a new question:

```
For each link in the chain:
  Ask: "Why was THIS specific answer true, and not something else?"
  If the answer is unexpected or unexplained → run a targeted search for that gap
  If the answer is obvious from context → move on
```

This recovers the iterative "ask why about each answer" quality of the five whys. One-shot evidence gathering is efficient but risks anchoring on the first narrative that fits. The surprise check forces a second pass where each layer gets challenged.

**Surprise signals to look for:**
- A decision was made but no one discussed alternatives → why was it the only option?
- A problem was stated but the fix seems disproportionate → was there a hidden constraint?
- The chain skips a step (Current State → Origin with nothing in between) → what happened in between?
- Two sessions contradict each other → what changed between them?
- A user correction appears mid-chain → what assumption was wrong?

**When surprise is found:** Do a targeted search (one of the 6 data sources) specifically for the gap. Don't re-run all searches — just the one most likely to fill the gap.

### STEP 6: Absent evidence check

Before presenting, identify what you **would expect to find but didn't**:

- If a decision was deliberate, you'd expect a user directive or discussion → absent?
- If a change was bug-driven, you'd expect error output or problem statement → absent?
- If an architecture choice was made, you'd expect ADR or CLAUDE.md entry → absent?

Missing expected evidence is itself a signal — it suggests the decision may have been:
- An accidental side effect (not deliberate)
- Made outside this project (imported pattern)
- Predates transcript history
- Made implicitly without conscious choice

Flag absent evidence as `[ABSENT EVIDENCE]` in the output.

### STEP 7: Present as narrative

**For decision chain questions:**

```markdown
## Why: {topic}

### Origin
{What first prompted this work — the original need/problem}

### Decision Chain
1. **{Decision}** — {when} — {rationale}
   - Triggered by: {what caused it}
   - Assumption: {what it rests on}
2. **{Decision}** — {when} — {rationale}
   - Course correction from #1: {what changed and why}

### Branching Analysis (if multiple causes)
If multiple valid causes exist at any decision point:
- **Path A**: {cause + evidence + where it leads}
- **Path B**: {cause + evidence + where it leads}
- **Selected**: {which path was taken and why}

### Current State
{Where things stand now and why}

### Key Assumptions
- {Assumption}: {still valid? yes/no/unknown}

### Verification
{How to confirm this causal chain is correct — what would disprove it?}

### Absent Evidence
{What you'd expect to find but didn't — what this absence suggests}
```

**For existence rationale questions** ("why do we have X?"):

```markdown
## Why: {topic}

### Pain Point (what hurt before this existed)
{The original problem that X was created to solve — what was annoying/broken/missing}

### Solution Selection (why THIS approach)
{What alternatives were considered and why this one was chosen}
- **Considered**: {alternatives found in evidence}
- **Chosen**: {what was selected and the rationale}
- **Rejected because**: {why alternatives didn't work}

### How it works now
{Current state — what it does, how it's maintained}

### Maintenance Contract
{How it stays current: upstream-managed? manually updated? version-locked?}

### Key Assumptions
- {Assumption}: {still valid? yes/no/unknown}

### Verification
{How to confirm this rationale is correct — what would disprove it?}

### Absent Evidence
{What you'd expect to find but didn't}
```

## Phase Gates

**GATE 1 (STOP after Step 2: Gather Evidence)**: Before moving to Step 3 (Extract Causal Markers), verify:
- At least Tier 1 sources attempted (session history, CKS, memory, or CLAUDE.md/ADRs)
- Git evidence gathered only for corroboration, not primary attribution
- No claim made without evidence behind it

If gate fails: re-gather evidence before proceeding.

**GATE 2 (STOP after Step 3: Extract Causal Markers)**: Before moving to Step 4 (Reconstruct Causal Chain), verify:
- At least decisions and triggers identified
- Assumptions documented
- Corrections noted where reasoning changed

If gate fails: extract more causal markers before reconstructing chain.

**GATE 3 (STOP after Step 5: Surprise Check)**: Before moving to Step 6 (Absent Evidence Check), verify:
- Each link in chain has been challenged
- Any surprises identified and targeted searches done
- No link is unexplained or obvious without verification

If gate fails: run surprise check before absent evidence check.

**STOP between generation (Steps 1-4) and validation (Steps 5-7)**:
- Steps 1-4: Parse, gather evidence, extract markers, reconstruct chain (generation)
- Steps 5-7: Surprise check, absent evidence, present narrative (validation)
- Do NOT proceed to Step 5 until causal chain is reconstructed in Step 4

---

## Data Sources

### Tier 1 — Primary (terminal-attributed, authoritative)

| Source | Provides | How to access |
|--------|----------|---------------|
| `/recap` CLI | Session chain + semantic content | `python "$CLAUDE_ROOT/skills\recap\scripts\recap_cli.py" recap` |
| TranscriptParser | Decisions, patterns, corrections | Via recap output or direct grep of transcript |
| CKS | Prior decisions in knowledge base | `mcp__search-research__cks_search` |
| Memory | Feedback rules, project context | Search `C:\Users\brsth\.claude\projects\P--\memory\` |
| CLAUDE.md | Architectural constraints | `Grep` for topic keywords |
| ADRs | Documented architecture decisions | `Glob` in `$__CSF_ROOT/arch_decisions\` |

### Tier 2 — Supplementary (corroboration only, no terminal attribution)

| Source | Provides | How to access |
|--------|----------|---------------|
| Git log | Commit history and messages | `git log --oneline --all --grep="{topic}"` |
| Git blame | Who introduced changes | `git log -S "topic" --oneline`, `git log --follow -p -- {file}` |

**Why git is Tier 2**: In multi-terminal environments, git cannot attribute commits to specific terminals. Git shows author + timestamp but NOT which terminal session produced the change. Use git to corroborate transcript evidence, never as primary source for "which terminal/why."

## Fallback Strategy

If no evidence found for the topic:

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
1. Broaden the search — try related terms, abbreviations, parent concepts
2. Check git blame on relevant files — `git log --follow -p -- {file}`
3. Check CLAUDE.md for constraints that would explain it
4. If truly nothing found: "No decision trail found for '{topic}'. It may predate transcript history or was decided outside this project."

## Important Notes

- **Evidence-first**: Every claim in the output must trace to a specific data source. No speculation.
- **Causal, not chronological**: Order by causation, not by time. A decision from 3 sessions ago may be the root cause of today's work.
- **Include dead ends**: If a path was tried and abandoned, include it — that's valuable context for understanding why the current path was chosen.
- **Respect evidence tiers**: Tier 1 (transcript, CKS, memory) is authoritative. Tier 2 (git) is corroboration only. Tier 4 (unverified assumptions) must be marked `[UNVERIFIED]`.
- **Multi-terminal aware**: Git history cannot attribute commits to specific terminals. In multi-terminal environments, git evidence is supplementary — never use it as primary attribution for "which terminal decided X."
- **Compaction resilient**: If the current transcript is compacted, fall back to `history.jsonl` summaries via `walk_chain_simple()`. Compacted summaries retain decision markers even when full transcripts are garbage-collected.

### Relationship with `/recap`

`/why` traces causal chains. `/recap` provides the chronological overview that feeds into causal analysis:

- After `/why` surfaces a decision chain, use `/recap brief` to get the broader session context around those decisions
- If `/recap` surfaces something interesting (e.g., a recurring problem pattern), use `/why "why did we keep hitting X?"` to dig into the root cause
