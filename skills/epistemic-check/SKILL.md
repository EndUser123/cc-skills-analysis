---
name: epistemic-check
description: Validate any Q&A response against the 4-section epistemic contract. Runs 3-phase audit (format → causal → comparative), reports violations and minimal repairs.
enforcement: advisory
workflow_steps:
  - parse
  - audit
  - report
triggers:
  - /epistemic-check
  - audit answer
  - check epistemic
  - validate response structure
  - epistemic audit
inputs:
  - name: question
    type: string
    description: The original question being answered
  - name: answer
    type: string
    description: The response to validate
outputs:
  - name: verdict
    type: string
    description: "allow | warn | block — the validation decision"
  - name: phase_issues
    type: array
    description: "Phase-level issue summary {phase, passed, issues[]}"
  - name: repairs
    type: array
    description: "Minimal edit suggestions per violation"
---

# /epistemic-check — Epistemic Contract Validator

Validate any Q&A response against the 4-section epistemic contract using the same three-phase logic the Stop hook uses.

## Inputs

- **question** — The original question
- **answer** — The response to validate

## Outputs

Verdict (`allow` | `warn` | `block`) + per-phase issues + minimal repair suggestions.

## Phase 1: Format & Structure

Parse the response into sections. Check:

- All four sections present: `[FACT]`, `[INFERENCE]`, `[UNKNOWN]`, `[RECOMMENDATION]`
- Correct section order
- No text outside sections
- All bullets start with `- `
- **Diagnostic Metric: Contradiction Detection**: Ensure [FACT] sections do not contradict [INFERENCE] or [RECOMMENDATION] sections.

Report format issues here.

## Phase 2: Causal Claims

Check causal language (`because`, `causes`, `leads to`, `is caused by`, `due to`, `the reason is`, etc.):

- **[FACT]**: Causal claims require evidence citation `(source: ...)` or must move to INFERENCE
- **[INFERENCE]**: Causal claims require uncertainty markers (`may`, `might`, `could`, `seems`, `appears`)
- **[UNKNOWN]**: Must NOT contain causal claims
- **[RECOMMENDATION]**: Hard assertion verbs (`is`, `are`, `ensures`, `guarantees`) require rationale markers (`because`, `so that`, `in order to`, `to ensure`, `based on`)

## Phase 3: Comparative Claims

Check comparative/superlative language (`best`, `optimal`, `safest`, `most efficient`, `lowest risk`, `simplest`, etc.):

- **Diagnostic Metric: Semantic Ambiguity**: Flag vague comparatives that lack a measurable technical signal or criterion.
- **[FACT]**: Comparatives require citation or external reference, otherwise move to INFERENCE
- **[INFERENCE]**: Superlatives require uncertainty markers, otherwise flag
- **[UNKNOWN]**: Must NOT contain comparative claims
- **[RECOMMENDATION]**: Superlatives require either assumption markers (`given`, `assuming`, `if your goal is`) OR rationale markers — state the criterion: "best **for** X" or "optimal **given** Y"

## Output Format

```
EPISTEMIC CHECK
Question: {truncated question}
Verdict: {allow|warn|block}

--- Phase 1: Format ---
[pASS] All four sections present in correct order
[FAIL] UNKNOWN section missing

--- Phase 2: Causal ---
[pASS] No causal violations
[FAIL] [INFERENCE] bullet 2 lacks uncertainty marker

--- Phase 3: Comparative ---
[pASS] No comparative violations
[FAIL] [RECOMMENDATION] bullet 0: superlative without criterion

--- Minimal Repairs ---
[UNKNOWN] bullet 0 — remove causal claim or move to INFERENCE
  Current: "X causes Y"
  Fix: "X may cause Y" (add uncertainty) or "X is associated with Y"
[RECOMMENDATION] bullet 0 — add criterion for superlative
  Current: "Use the simplest approach"
  Fix: "Use the simplest approach for minimal code churn"
```

## Rule Reference

| Section | Causal rule | Comparative rule |
|---------|------------|-----------------|
| FACT | Requires citation | Requires citation or external quote |
| INFERENCE | Requires uncertainty marker | Superlatives require uncertainty |
| UNKNOWN | **BLOCKED** | **BLOCKED** |
| RECOMMENDATION | Hard assertions require rationale | Superlatives require criterion/assumption |

## Phase Gates

**GATE 1 (STOP after Phase 1: Format & Structure)**: Before moving to Phase 2 (Causal Claims), verify:
- All four sections present: [FACT], [INFERENCE], [UNKNOWN], [RECOMMENDATION]
- Correct section order
- No text outside sections
- All bullets start with `- `
- No contradiction between [FACT] and other sections

If gate fails: report format violations before proceeding to causal analysis.

**GATE 2 (STOP after Phase 2: Causal Claims)**: Before moving to Phase 3 (Comparative Claims), verify:
- [FACT] causal claims have evidence citation or moved to INFERENCE
- [INFERENCE] causal claims have uncertainty markers
- [UNKNOWN] has no causal claims
- [RECOMMENDATION] hard assertions have rationale markers

If gate fails: report causal violations before proceeding.

**STOP between phases**:
- Phase 1 (Format) → Phase 2 (Causal): Must validate structure before checking causal language
- Phase 2 (Causal) → Phase 3 (Comparative): Must complete causal analysis before comparative

---

## When to Use

- `/epistemic-check "what is X?" "X works because..."`
- After receiving a structured response and wanting independent validation
- Before accepting recommendations that contain causal or comparative language

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