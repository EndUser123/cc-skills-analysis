---
name: retro
description: "Advanced chain mode of /debrief — for when you have a session chain (multiple linked sessions), not a single transcript file. /retro walks the chain via /recap, then runs cc-skills-analysis/skills/debrief/__lib__/debrief_core.py per session for the root-cause extraction step. Output is RNS-formatted with SCORES gate (completeness/optimality/satisfaction 0-10, red-team if <8). For a single transcript file, use /debrief instead — /retro is the multi-session escalation."
version: 1.0.43
category: orchestration
triggers:
  - "retro"
  - "/retro"
  - "run self-contrast"
  - "retrospective protocol"
  - "self-contrast"
  - "session chain"
  - "multi-session retro"
contract_type: workflow
aliases:
  - /retro
  - /self-contrast
suggest: []  # Empty: see /debrief for the integration story.
# depends_on_skills: REMOVED. The dep hook was firing false positives for
# all three (recap/debrief/rns verified PRESENT by direct ls). The
# cross-plugin dep on /pre-mortem is documented in step_3 below.
workflow_steps:
  - step_1: Call /recap — get the session chain (problem/optimal contrast across linked sessions)
  - step_2: For each session in the chain, invoke __lib__/debrief_core.run() with the session transcript + a layer_extractor that asks "where in the code did this session's symptoms originate?" — produces origin-anchored findings, not symptom lists
  - step_3: Resolve /pre-mortem cross-plugin, then call for adversarial validation of the approach (red-team if any SCORES axis < 8)
  - step_4: Evaluate SCORES — completeness/optimality/satisfaction 0-10; red-team if any axis < 6, mandatory if < 6
  - step_5: Aggregate ALL findings from /recap + debrief_core + /pre-mortem
  - step_6: Render RNS output — domain grouping, gap coverage, Do ALL footer; every finding must have a next step or explicit disposition
enforcement: strict
workflow_binding: exclusive
workflow_enforcement: hard
phase_recovery_mode: resumable
user_override: explicit
layer1_enforcement: true
required_phase_artifacts:
  - /recap
  - debrief_core
  - /rns
usage_markers:
  - "RECAP:"
  - "GAPS:"
  - "FRICTION:"
  - "SCORES:"
  - "GAP COVERAGE"
  - "Do ALL Recommended Next Actions"
---

# RETRO — SELF-CONTRAST Orchestrator

## Purpose

Run the full SELF-CONTRAST protocol in sequence: retrospective → gap+friction analysis → adversarial validation → prioritized actions. Produces a structured output with named score axes.

## When to Use

- End of session: "run /retro"
- After major implementation: "let's retrospective this"
- Before planning next phase: "what gaps do we have?"

## FLOW

```
1. /recap          → Session retrospective (what happened, problem vs optimal)
2. /gto            → Gap + friction analysis (code/process gaps from session)
3. /pre-mortem     → Adversarial validation (what WILL fail)
4. /rns            → Action extraction (recover/prevent/realize)
```

### Red-Team Trigger

If any SCORES axis is below 8, invoke `/rns` with adversarial framing before finalizing actions:
- completeness_score < 8 → red-team gaps in coverage
- optimality_score < 8 → red-team approach quality
- satisfaction_score < 8 → red-team process/experience

## OUTPUT Format

```
RECAP: [2-paragraph session summary — problem vs optimal]

GAPS: [top 3 gaps identified]
  1. [gap description]
  2. [gap description]
  3. [gap description]

FRICTION: [top 3 friction points]
  1. [friction description — category: automation/manual/repeated]
  2. [friction description — category]
  3. [friction description — category]

SCORES:
  c:[0-10]  Completeness — were all gaps found?
  o:[0-10]  Optimality  — was the approach best possible?
  s:[0-10]  Satisfaction — smooth process?
```

### RNS Output (Final Section)

The retro ends with an RNS-formatted action list. Follow the `/rns` output format exactly — dynamic domain grouping, domain-numbered items, `@ file:line` references, gap coverage, and the `0 — Do ALL` footer.

```
1 🔧 QUALITY (2)
  1a [recover/high] Fix concurrent save registry integrity test @ test_critique_io_concurrent.py:89
  1b [prevent/med] Add Phase 2/3 filename round-trip tests @ test_critique_io.py

2 📄 DOCS (1)
  2a [realize/low] Update SKILL.md with Phase 1 completion gate @ SKILL.md

📋 GAP COVERAGE (7 items)
  5 MAPPED → see actions above
  1 REJECTED — "MECHANISM_LEAKAGE: hardcoded @gitready is low-risk branding, not a functional issue"
  1 DEFERRED — "ASSURANCE: AGENTS.template.md deferred to /skill-ship (owns skill wiring)"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

0 — Do ALL Recommended Next Actions (3 items)
```

**Format rules** (same as `/rns`):
- Domain sections use emoji headers (🔧 QUALITY, 📄 DOCS, etc.) — no markdown fences
- Items use domain-numbered format: `1a`, `1b`, `2a`
- Each item shows: `[action/priority] Description @ file:line`
- Within each domain sort: recover → prevent → realize, then CRITICAL > HIGH > MEDIUM > LOW
- Gap coverage section accounts for ALL findings with explicit dispositions (MAPPED/REJECTED/DEFERRED)
- Ends with `0 — Do ALL Recommended Next Actions (N items)` — nothing follows after that line

### Domain Emoji Mapping

| Domain | Emoji |
|--------|-------|
| quality / code_quality | 🔧 |
| tests / testing | 🧪 |
| docs / documentation | 📄 |
| security | 🔒 |
| performance | ⚡ |
| git | 🐙 |
| deps / dependencies | 📦 |
| process / workflow | 🔄 |
| other | 📌 |

### RNS Aggregation Rule (Critical)

**The RNS must include ALL findings from ALL chained skills, not just /pre-mortem.**

When building the action list, aggregate findings from:
- `/recap` — work already done, completed, or committed (do not include as actionable unless something was left incomplete)
- `/gto gap` — internal technical debt in the target itself (own by GTO if the target is GTO, otherwise own by the retro's target)
- `/friction` — workflow friction and automation opportunities (include all automation-potential items)
- `/pre-mortem` — adversarial findings by domain
- `/rns` — extracted actions from above
- **Prior retro carryover** — unresolved RNS actions from the previous session's retro. Check the session transcript for the last retro's RNS output and carry forward any items that were not executed. Each carryover item gets the same disposition as new findings (MAPPED/REJECTED/DEFERRED). Carryover items render with `(carryover)` tag in the action line.

**Every finding from every skill must appear in the RNS with an explicit disposition.** Each finding gets exactly one:
- **MAPPED**: Has a corresponding action item above
- **REJECTED**: Valid but intentionally not acted on — state why
- **DEFERRED**: Deferred to future session — name owner + trigger condition

**No finding is silently dropped.** If a finding is excluded, the GAP COVERAGE section states why.

**Failure mode this prevents:** RNS was previously built only from /pre-mortem findings, dropping GTO internal gaps (CAUSE-001/002/003, 7 TODOs in GTO test files) and workflow friction that no upstream skill flagged. The retro felt complete but was systematically incomplete.

## Step Execution

1. **Call `/recap`** — get session summary with problem/optimal contrast
2. **Call `/gto gap`** — extract top gaps from session evidence
3. **Call `/friction`** — identify workflow friction and automation opportunities
4. **Call `/pre-mortem`** — adversarial validation of approach
5. **Evaluate SCORES** — rate each axis 0-10:
   - If any axis < 8: re-run with adversarial framing before proceeding
6. **Aggregate** — merge ALL findings from all chained skills
7. **Render RNS output** — format the aggregated findings using the RNS output format (domain grouping, gap coverage, `0 — Do ALL` footer). Every finding must have a recommended next step or an explicit REJECTED/DEFERRED disposition.

## Red-Team Protocol

When SCORES reveals weakness:
1. Re-examine the weak axis with adversarial framing
2. Incorporate findings into GAPS or FRICTION as appropriate
3. Re-score with new data
4. Proceed to ACTIONS only after gaps are addressed or deferred

## Retrospective-Integrity Prompts

Before finalizing the retrospective, `/retro` should run a short internal retrospective-integrity check:

- What did we treat as a process win even though the outcome was suboptimal?
- What gap or friction point is duplicated across `/recap`, `/gto`, `/friction`, `/pre-mortem`, and `/rns` rather than being synthesized once?
- What score is being inflated or deflated without strong evidence from the chained skills?
- What action list would mis-sequence work by treating symptoms as the primary problem?
- What recommendation becomes misleading if the adversarial review surfaced a deeper failure mode?
- What positive takeaway is actually a workaround that should not be repeated?
- What workflow friction did we treat as normal even though it could be automated or eliminated?
- What would a weaker model smooth over instead of preserving as a real tradeoff or unresolved tension?
- What step in the chain returned weak or partial evidence, and did I compensate for that explicitly?
- What ownership boundary is still unclear between architecture, planning, verification, and implementation?
- What would make this retro feel complete while still teaching the wrong lesson?

These are internal self-check prompts. They are not default user-facing questions and should only surface to the user when `/retro` is genuinely blocked and cannot proceed safely without clarification.

## Trace, Emerge, Graduate, and Friction

`/retro` should use four internal helper passes:

- `trace`: reconstruct how the session or project path evolved, including the moments that most changed the outcome
- `emerge`: identify latent patterns across recap, gap analysis, friction, pre-mortem, and action extraction that no single sub-skill named explicitly
- `graduate`: promote repeated retrospective findings into durable process changes, validators, hooks, or workflow rules when warranted
- `friction`: actively scan chained results for repeated manual steps, missing automations, and workflow gaps that no upstream skill flagged

Use `trace` when the retrospective depends on a sequence of decisions or turning points.
Use `emerge` when multiple chained skills are pointing at the same hidden theme.
Use `graduate` when the same class of retro lesson keeps recurring and should become durable enforcement or policy.
Use `friction` when the session reveals manual patterns that could be automated or eliminated.

Reference: `P://.claude/skills/__lib/sdlc_internal_modes.md`

## Constraints

- Do NOT fabricate scores — derive from evidence in each step
- Do NOT skip steps — each feeds the next
- If a step returns no findings, note "none found" and proceed
- Red-team is advisory if scores are 6-7, mandatory if < 6

## Phase Gates

**GATE 1 (STOP after Step 1: /recap)**: Before moving to Step 2 (/gto gap), verify:
- /recap output received and complete
- Session summary available for next steps

If gate fails: re-run /recap before proceeding.

**GATE 2 (STOP after Step 2: /gto gap)**: Before moving to Step 3 (/friction), verify:
- /gto gap output received
- Top gaps identified and documented

If gate fails: re-run /gto before proceeding.

**GATE 3 (STOP after Step 3: /friction)**: Before moving to Step 4 (/pre-mortem), verify:
- /friction output received
- Workflow friction and automation opportunities identified

If gate fails: re-run /friction before proceeding.

**GATE 4 (STOP after Step 4: /pre-mortem)**: Before moving to Step 5 (Evaluate SCORES), verify:
- /pre-mortem adversarial validation complete
- All findings from upstream skills available for aggregation

If gate fails: complete /pre-mortem before scoring.

**GATE 5 (STOP after Step 5: Evaluate SCORES)**: Before moving to Step 6 (Aggregate) or red-team, verify:
- All three scores (completeness, optimality, satisfaction) rated 0-10
- Red-team triggered if any axis < 8

If gate fails: complete scoring before aggregation.

**STOP between generation (Steps 1-4) and validation (Steps 5-7)**:
- Steps 1-4: Gather findings from /recap, /gto, /friction, /pre-mortem (generation)
- Steps 5-7: Score, aggregate, render RNS (validation)
- Do NOT score until all upstream skills complete

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
