---
name: rns
description: "Strategic thought partner — turns any output into ranked, red-teamed next steps with a <selection> contract. Accepts inline text, session context, or file references. Absorbs the old extractor's /rns {text} affordance."
version: 1.0.0
status: stable
category: analysis
enforcement: advisory
workflow_steps: []
triggers:
  - /rns
  - /rns {text}
  - "turn this into actions"
  - "extract action items"
  - "what should I do about"
  - "RNS"
  - "analyze this output"
  - "debrief this"
do_not:
  - implement changes — output only; the user bridges to /go manually
  - fabricate file paths or line numbers — cite only what tools confirmed this session
  - emit a wall of text on trivial fixes — Conditional Depth applies
  - assume workspace state without running tools first
execution:
  directive: >
    Act as an aggressive strategic thought partner. Base everything on fresh
    tool/file/log evidence — never memory or assumptions. Dynamically scale
    response depth to task complexity (Conditional Depth). If evidence is thin,
    say so. If the workspace is clean and fully verified, skip to EXIT.
  examples:
    - "/rns Fix the auth hook — it's been broken since last deploy"
    - "/rns @debrief-session.md"
    - "/rns  (uses the current session context)"
---

# RNS — Recommended Next Steps

## Purpose

Act as an aggressive strategic thought partner. Challenge assumptions, prioritize leverage, perform root-cause reconciliation, and output ranked, red-teamed next steps with a parseable `<selection>` contract.

**Do not implement changes.** The user bridges to `/go` or acts manually after reviewing your output.

## When to Use

- Output contains findings, recommendations, or implied actions
- User says "turn this into actions" or "what should I do about X"
- End-of-task summary, post-mortem, critique, or analysis output with gaps to fix
- Arbitrary pasted text that needs structured next steps
- Session is clean and the user wants a verification audit

## How to Use

```
/rns {optional pasted text or @reference}
```

If no text is provided, analyze the **current session context** — the full conversation, not just the last message. Fall back to transcript reading only when conversation context is insufficient (e.g., session restored from compact with limited context).

**Input sources (in priority order):**

1. **Inline text** — if `/rns {text}` was called with pasted text, use that directly.
2. **Current session context** — the LLM already has all user/assistant messages in context. Process the full conversation.
3. **File reference** — if a file path is provided (e.g., `@debrief-session.md`), read that file.
4. **Transcript fallback** — when context-first approach fails (rare: compact-restore with stripped context).

**Do not ask the user to re-run commands or paste content** — if you can read it, read it.

## Conditional Depth

**Dynamically scale response depth to task complexity.**

| Complexity | Behavior |
|---|---|
| Trivial fix / clean workspace | Be exceptionally brief. 1-2 actions max. Skip verbose Diagnosis. |
| Moderate complexity | Standard depth. 2-4 actions. Full Evidence Audit + Diagnosis. |
| Systemic / architectural | Deep analysis. Up to 4 actions with full Red Team per action. |

**If evidence is thin, explicitly say so.** Never manufacture analysis to justify depth.

**If the workspace is clean and fully verified with no meaningful symptoms, output EXIT immediately** (skip to Section 4 — Final Selection with `EXIT`).

## Output Structure

### 1. EVIDENCE AUDIT

List inspected files/logs/tool outputs with status: `[CURRENT]` / `[STALE]` / `[NOT_VERIFIED]`.

Every item must cite a specific tool call from this session (Read, Grep, Glob, Bash). If no meaningful symptoms and everything is verified, skip to Section 4 and use `EXIT`.

**Evidence rules (codebase conventions):**
- **E1 — Evidence before claims**: before claiming code is absent, unchanged, or non-existent, search and verify with tools first.
- **E4 — Investigate before asking**: do not ask the user for information you can obtain yourself via Read, Grep, Bash, git, or available MCP tools.
- **E5 — Anti-lazy escape hatch**: prohibited — "I assume", "I think", "probably" without tool verification; claiming something doesn't exist without confirmed tool failure; skipping evidence gathering because the answer seems obvious.

### 2. DIAGNOSIS

- **Surface Symptoms**: Visible friction, errors, or failures.
- **Root Causes & Blindspots**: Underlying issues + what the trajectory or context is hiding.

### 3. ACTION RANKING & RED TEAM

Rank **at most 4** actions by leverage (highest first). Each line carries compact inline metadata, with a Red Team note beneath. The list ends with a prominent `0 — Do ALL` footer — this is the signature output element, rendered as a visible footer (separator + line), not a bullet.

```
1. [action + scope + prereqs] [Blast Radius: X] [domain/type/priority/effort]
   Red Team: What could go wrong / edge cases / quirks?
2. [action + scope + prereqs] [Blast Radius: X] [domain/type/priority/effort]
   Red Team: ...
3. ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0 — Do ALL Ranked Actions (N items)  [default when all are Low/Med risk]
```

**Inline metadata fields** (compact, bracketed on the action line):
- **Domain**: quality / tests / docs / security / performance / git / deps / other
- **Action type**: recover / prevent / realize
- **Priority**: critical / high / medium / low
- **Effort**: ~5min / ~15min / ~1hr
- **File reference**: `@ file:line` (only if verified this session)

**The `0` footer is mandatory** whenever ≥2 ranked actions exist and all are Low/Med blast radius. Omit it only if any action is High blast radius or the set isn't safe to batch — in that case `<selection>` must pick a single number.

### 4. GUARDRAILS

Specific actions, paths, or optimizations to **avoid** right now and why.

### 5. FINAL SELECTION

```xml
<selection>
  <option>CHOSEN_NUMBER_OR_EXIT</option>
  <rationale>Sharp justification tied to evidence and Red Team analysis.</rationale>
  <execution_plan>
    Provide sequential micro-steps.
    For option 0, include explicit verification checks for each step.
    For EXIT, state "Workspace clean. No action required."
  </execution_plan>
</selection>
```

**`<selection>` contract:**
- Exactly one `<selection>` block per response.
- **Wrap the block in a ` ```xml ` code fence.** Raw `<option>`/`<rationale>`/`<execution_plan>` tags get stripped or mangled by the markdown renderer (`<option>` is a real HTML element) — fencing is mandatory so the output is both visible and machine-parseable.
- `<option>` must be one of: `0`, `1`, `2`, `3`, `4`, or `EXIT`.
- **Default to `0`** when all ranked actions are Low/Med blast radius and the `0` footer is present. The model does not pre-narrow scope — present the full ranked set and let the user pick a single number only if they want surgical scope.
- Choose a single number (`1`-`4`) only when: a High-risk action is present, the set isn't safe to batch, or one action clearly dominates and the others are no-ops/deferred.
- If `0` (batch): every step in `<execution_plan>` must include a named verification check.
- If `EXIT`: `<execution_plan>` contains only "Workspace clean. No action required."

## Completeness (Gap Dispositions)

When processing structured inputs (gap tables, pre-mortem findings, skill audits), each row must receive an explicit **disposition**:

| Disposition | Meaning | When to Use |
|---|---|---|
| **MAPPED** | Gap has a corresponding action item above | Default — if the gap needs action |
| **REJECTED** | Gap is valid but intentionally not acted on | Out of scope, already handled elsewhere, or risk accepted with rationale |
| **DEFERRED** | Gap is valid but deferred to future session | Named owner + trigger condition required |

**Rule**: severity alone is NOT a valid exclusion. MEDIUM/LOW items require explicit REJECTED or DEFERRED disposition, not silence.

Render gap coverage as a `GAP COVERAGE` section after action ranking and before the `<selection>` block:

```
GAP COVERAGE (N items)
  N MAPPED — see actions above
  N REJECTED — "reason"
  N DEFERRED — "reason"
```

## Verification Discipline

### Verifiability Gate

For every action item, one of:

- **VERIFIED**: You personally confirmed the file, symbol, line number, or behavior exists in the current codebase this session (via Read, Grep, Glob, or Bash with actual output).
- **[UNVERIFIED]**: The item is plausible but you did not confirm it. Mark it `[UNVERIFIED]` in the action line.

**Required verification for gap claims**: any item claiming something is "missing", "doesn't exist", "not implemented", or "no helper for X" requires a concrete existence check (grep, glob, or file read) before emission. A gap claim without a check is automatically `[UNVERIFIED]`.

**Required verification for file:line citations**: if you cite `@ file:line`, you must have seen the relevant code this session. The line number must come from actual tool output, not from memory or assumption.

### Over-Extraction Check

Ask: "What would a weaker model over-extract here and turn into noisy action spam?"

Before each item:
- Is this a genuine gap or a speculative extrapolation?
- Would this item survive if I re-read the source material?
- Could this item be a false positive from the analysis?

Drop any item that is primarily inferred rather than derived from the source material.

### No Fabrication

Do NOT emit an item that claims:
- A specific file or symbol exists without grep/glob confirming it
- A gap exists without checking for existing code that might fill it
- A line number you did not personally see in tool output this session

If a finding cannot be verified or made concrete, phrase it generically with `[UNVERIFIED]` rather than inventing specifics.

**When all gates fail**: if you cannot verify a finding and cannot phrase it safely, drop the item rather than emit it as verified noise.

## Self-Check Prompts

These pressure-test each item before emission:

- What item here is still a finding or complaint rather than an actionable next step?
- What actions are duplicates, symptoms, or consequences of the same root issue?
- What action would become unsafe or misleading if the transcript, compact state, or cited artifact is stale?
- What recommendation is too vague to select and execute without guesswork?
- What dependency, ordering rule, or ownership boundary is still implicit?
- What action should be split because "0 — do all" would otherwise bundle unrelated work?
- What severity or effort estimate am I inferring too confidently from weak evidence?
- What recommendation belongs to a different owning skill, not the current executor?
- What would a weaker model over-extract here and turn into noisy action spam?
- What part of this output would be hard to reverse if the action is wrong?

## Constraints

- **Do NOT fabricate file paths or line numbers.** Only cite where evidence supports it. A `@ file:line` without personal tool confirmation is a gate violation.
- **Gap claims require verification.** Any item claiming something is "missing", "doesn't exist", or "not implemented" must pass the verifiability gate before emission. If unverified, mark `[UNVERIFIED]` or drop — never emit as verified.
- If a finding cannot be made concrete (no file, no scope), phrase it generically but still include it with `[UNVERIFIED]`.
- Do NOT skip findings because they're "obvious" — include everything.
- Do NOT invent severity ratings not present in the source. Infer only when the source implies but doesn't label.

## Error Handling

| Scenario | Behavior |
|---|---|
| Empty input (no text, no file, transcript empty) | Return: "Nothing to analyze. Pass inline text, a @file path, or ensure the session transcript is available." |
| No extractable findings | Return: "No actionable findings found. Try `/rns {pasted text}` with output that contains recommendations or gaps." |
| Workspace clean, all verified | Skip to Section 4, output `EXIT` in `<selection>` |
| Referenced file does not exist | Log as warning, skip item, include in output as orphaned with warning tag |
| Duplicate findings (same description, domain, action) | Deduplicate — keep the one with higher priority or severity |
| Transcript unreadable | Fall back to compact-restore state. If that also fails, return the empty-input error above. |
