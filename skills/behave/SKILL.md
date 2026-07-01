---
name: behave
description: Structured behavioral analysis for LLM performance debugging — hypothesis testing for session patterns (loops, context degradation, decision inefficiency, cognitive overload, attention drift)
version: 1.0.43
category: analysis
enforcement: advisory
triggers:
  - /behave
  - "analyze behavior"
  - "session pattern"
  - "LLM behavior"
  - "behavioral analysis"
aliases:
  - /behave
suggest:
  - /diagnose
  - /trace
depends_on_skills: []
workflow_steps:
  - step_1: Generate candidate hypotheses (3-5 per symptom, no filtering)
  - step_2: Design cost-ordered tests (cheap to expensive per hypothesis)
  - step_3: Falsify hypotheses (eliminate, don't confirm)
  - step_4: Calibrate confidence and produce structured output
freedom: medium
---

# /behave — LLM Behavioral Analysis

Structured hypothesis-testing analysis for LLM performance debugging in chat sessions.

## Purpose

Analyze session history to detect and diagnose behavioral patterns that indicate performance issues:
- **Loop detection**: Repeated failed approaches
- **Context degradation**: Lost context, forgotten details
- **Decision inefficiency**: Extended deliberation, reversed choices
- **Cognitive overload signals**: Confusion, excessive clarification requests
- **Attention drift**: Tangential responses, loss of focus

## When to Use

- After a session with unexpected behavior
- When pattern analysis is needed before diagnosis
- Debugging LLM performance issues systematically

## Output Format

**Required**: Bullet structure with explicit hypothesis labels (H₁, H₂, H₃), NOT tables or narrative conclusions.

---

## Step 1: Generate Candidate Hypotheses

For each observed symptom, generate 3-5 competing root cause hypotheses. **No filtering — list all candidates.**

Format:
```
H₁: [specific mechanism]
H₂: [alternative mechanism]
H₃: [third mechanism]
H₄: [fourth mechanism]
H₅: [fifth mechanism]
```

**Rule**: Do NOT suppress or pre-judge any hypothesis.

---

## Step 2: Cost-Order Tests

For each hypothesis, specify:

```
TEST METHOD: How to distinguish this from alternatives
DATA NEEDED: What evidence would falsify this
COST: Execution cost (log search, code trace, re-run, etc.)
```

**Order tests from cheapest to most expensive.**

| Cost Level | Examples |
|------------|----------|
| Cheap | Log search, grep, Read existing files |
| Medium | Add diagnostic print, verify data exists, swap tool |
| Expensive | Re-run in fresh context, cross-environment test |

---

## Step 3: Falsification

State which hypotheses remain **unfalsified** based on available evidence.

**Rule**: DO NOT converge to single hypothesis until alternatives are ruled out.

Format:
```
Unfalsified after available evidence: H₁, H₂, H₃ (H₄ ruled out by [evidence])
```

---

## Step 4: Confidence Calibration

**Self-rated confidence is unreliable without calibration against evidence tiers.**

Calibrate each hypothesis using this table:

| Evidence Source | Confidence Ceiling |
|----------------|---------------------|
| Execution artifacts, logs, test output | 95% |
| Official docs, specs, verified specs | 85% |
| Static analysis, code inspection | 75% |
| Memory entries, unverified claims | ≤50% |

**Calibration rules:**
- Calibrate against evidence tier, not against feel — if your evidence is Tier 4 (memory), your confidence ceiling is 50%, no matter how "certain" you feel
- State the evidence tier explicitly: "Confidence: MODERATE (Tier 3 evidence — code inspection only)"
- When multiple hypotheses remain, the confidence ceiling is set by the *lowest* evidence tier among unfalsified candidates
- Distinguish between *plausible* (mechanism fits the data) and *supported* (evidence confirms mechanism) — don't conflate the two

| Remaining Candidates | Confidence Level |
|----------------------|------------------|
| 1 hypothesis | HIGH (H rejected) |
| 2-3 hypotheses | MODERATE (list candidates) |
| 4+ hypotheses | LOW (cannot converge without more data) |

**Only after Steps 1-4**: Produce structured output with confidence qualifier and explicit evidence tier.

---

## Output Template

```markdown
Finding: [brief description of observed symptom]

Hypotheses:
  H₁: [specific mechanism]
  H₂: [alternative mechanism]
  H₃: [third mechanism]
  H₄: [fourth mechanism]

Test sequence:
  [Cheapest] [test description] → [expected distinguishing evidence]
  [Medium] [test description] → [expected distinguishing evidence]
  [Expensive] [test description] → [expected distinguishing evidence]

Unfalsified after available evidence: H₁, H₂, ...

Confidence: [HIGH/MODERATE/LOW] ([reason])

Finding: [restated with appropriate confidence qualifier]
```

---

## Analysis Categories

### 1. LOOP DETECTION

Symptoms:
- Repeated tool calls with same parameters
- Same error recurred multiple times
- Back-and-forth on same issue

Hypotheses for loops:
- H₁: Query succeeded but returned no useful data → retry with different params
- H₂: Code path not reached (wrong conditional) → verify condition evaluation
- H₃: Stdout capture failed (environment issue) → verify capture mechanism
- H₄: Silent failure in code execution → check exit codes, logs
- H₅: State not propagated between turns → verify state file updates

### 2. CONTEXT DEGRADATION

Symptoms:
- Forgetting earlier stated constraints
- Asking for information already provided
- Contradicting previous statements

Hypotheses for context degradation:
- H₁: Context window overflow → check token count vs limits
- H₂: Session compaction triggered → verify compaction events
- H₃: Handoff lost critical context → verify handoff completeness
- H₄: Implicit assumption not captured → check for unstated constraints
- H₅: Cross-session state stale → verify state file timestamps

### 3. DECISION INEFFICIENCY

Symptoms:
- Extended deliberation on simple choices
- Reversed decision after implementation
- Repeated refinement cycles

Hypotheses for decision inefficiency:
- H₁: Threshold too strict → analyze boundary conditions
- H₂: Missing decision criteria → trace criteria propagation
- H₃: Conflicting objectives → map objective hierarchy
- H₄: Information asymmetry → identify unknown unknowns
- H₅: Premature commitment → verify decision gate timing

### 4. COGNITIVE OVERLOAD SIGNALS

Symptoms:
- Excessive clarification requests
- Inconsistent reasoning between steps
- Missed obvious alternatives

Hypotheses for cognitive overload:
- H₁: Too many concurrent concerns → count active variables
- H₂: Analogous problems not recognized → check pattern matching
- H₃: Domain knowledge gap → identify unfamiliar constructs
- H₄: Output format too complex → measure output complexity
- H₅: Input noise overwhelming signal → check signal-to-noise ratio

### 5. ATTENTION DRIFT

Symptoms:
- Response addresses wrong aspect
- Tangential suggestions introduced
- Topic scope creep

Hypotheses for attention drift:
- H₁: Prompt intent unclear → analyze prompt structure
- H₂: Implicit scope not established → verify scope boundaries
- H₃: Distraction诱 introduced mid-response → check for injected context
- H₄: Topic boundaries fuzzy → identify boundary violations
- H₅: Response template mismatch → verify template fit

---

## Example

**Finding**: Lines 41-54 empty Python output

```
Hypotheses:
  H₁: Query succeeded but returned no matching data
  H₂: Code path not reached (wrong conditional)
  H₃: Stdout capture failed (environment issue)
  H₄: Silent failure in code execution

Test sequence:
  [Cheapest] Add print("REACHED") before query → check logs for execution confirmation
  [Medium] Verify target data exists before querying → ls/Read confirmation
  [Medium] Swap diagnostic tool → test with grep/glob alternative
  [Expensive] Re-run in fresh terminal context → cross-environment comparison

Unfalsified after available evidence: H₁, H₂, H₃ (H₄ ruled out by RC:0 exit)

Confidence: MODERATE (3 candidates remain; cannot converge without re-execution)

Finding: Model ran empty diagnostic without confirming prerequisites
```

---

do_not:
  - Converge to single hypothesis before falsification
  - Present LOW confidence as fact
  - Skip hypothesis generation (need 3+ per symptom)
  - Use tables or narrative for hypothesis output
  - State findings without confidence qualifier
  - Skip STOP after Step 1 (before moving to Step 2)

## Phase Gates

**GATE 1 (STOP after Step 1)**: Before moving to Step 2, verify:
- At least 3 hypotheses generated per symptom
- No filtering or pre-judgment applied
- All hypotheses are distinct mechanisms

If gate fails: regenerate missing hypotheses before proceeding.

**GATE 2 (STOP after Step 2)**: Before moving to Step 3, verify:
- Tests are ordered cheapest to most expensive
- Each hypothesis has a distinct test (no identical tests)

If gate fails: reorder tests before proceeding.

**GATE 3 (STOP after Step 3)**: Before moving to Step 4, verify:
- At least one hypothesis was falsified with evidence
- No premature convergence to single hypothesis

If gate fails: note which hypotheses remain and proceed with MODERATE confidence.

**STOP between generation (Steps 1-2) and validation (Steps 3-4)**:
- Steps 1-2 generate hypotheses and design tests (generation phase)
- Steps 3-4 falsify and calibrate confidence (validation phase)
- Do NOT proceed to Step 3 until Step 2 tests are cost-ordered

---

## Related Skills

- `/diagnose` — Structured diagnostic protocol for code bugs
- `/trace` — Manual trace-through verification
- `/gto` — Gap/Task/Opportunity analysis

**Version**: 1.0.0

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