# Thought Partner Addendum (TPA)

**Canonical owner: `/improve`.** The TPA is a reusable **report-contract
section**, not a command. It surfaces material observations the user did not
explicitly ask for, when those observations would change a decision about
priority, risk, sequencing, scope, confidence, cost, maintainability, or
long-term value. It is co-located with the Completion Evidence Contract in
`debrief/references/` because it is the same kind of artifact — one canonical
reference plus short per-command pointers. `/improve` owns it because it is the
improvement / thought-partner command; the other commands carry pointers only.

**Advisory status:** prompt-advisory only. No runtime hook enforces TPA
emission or shape. A report that omits the TPA when it has nothing material to
say is correct; a report that pads the TPA with generic caveats is wrong. This
document is the contract; the discipline is the model's. A static test
(`tests/test_thought_partner_addendum.py`) pins the contract's invariants
(section presence, fields, urgency enum, examples, no-new-command); it does
NOT prove real reports emit the TPA — that is `prompt_advisory`, not
`runtime_enforced`.

## When to include

Include a `## Thought Partner Addendum` section at the end of a non-trivial
report when there is **at least one material observation the user did not ask
for** that would change a decision. Omit the entire section otherwise. Trivial
work gets no TPA.

## Required shape

Each item is a fenced block with exactly these fields:

```
- observation: <one sentence — what you noticed>
  why_it_matters: <what decision about priority / risk / sequencing / scope /
    confidence / cost / maintainability / long-term value this changes>
  evidence: <file:line, transcript cite, or measurement; mark INFERENCE or
    RISK if not direct inspection>
  recommended_action: <the concrete next step>
  urgency: now | later | watch
```

`urgency` enum (the only allowed values):

- `now` — changes a decision in this session, before the next action.
- `later` — changes a decision in a near-term follow-up; track, do not block.
- `watch` — a risk to monitor; no action yet, but name the tripwire that would
  escalate it.

## Rules

1. Include the section only when ≥1 item is genuinely material. An empty
   addendum is wrong; a missing addendum with nothing to say is correct.
2. Omit generic caveats. "Be careful with scope", "more tests may be useful",
   "consider documentation" are forbidden unless each is tied to a specific,
   decision-changing risk.
3. Omit any item that would not change a decision about priority, risk,
   sequencing, scope, confidence, cost, maintainability, or long-term value.
4. Mark weak evidence explicitly: `INFERENCE` (strong but unverified) or
   `RISK` (speculative). Direct inspection needs no marker.
5. Say plainly when a recommended action is advisory and not runtime-enforced
   (e.g., "no hook gates this — prompt-advisory only").
6. Do not displace the primary answer, verdict, or Completion Evidence
   Contract ledger. The TPA is a trailing aside, never the headline.
7. Keep it short — normally 1–5 items. If you have more, the report is
   probably missing a primary finding; promote that finding instead.

## Per-command placement

| Command | When to emit a TPA | Placement |
|---|---|---|
| `/improve` (owner) | Any non-trivial improvement / thought-partner turn. | After the recommendation / persistence / suggest block. |
| `/go` | Final implementation reports only — surface a broader root cause, a hidden risk, an activation gap (plugin bumped but not enabled), cost-waste, or a deferred prerequisite the task framing did not ask about. Not for trivial tasks. | After the final report, near the evidence block. |
| `/red-team` | After the verdict — surface residual risks that would change trust, sequencing, or scope. Do NOT displace the PROCEED / REVISE / BLOCK verdict or the mandatory CEC ledger. | After the CEC section. |
| `/debrief` | End-of-transcript mining — surface lessons not captured as tasks that affect future efficiency, effectiveness, or trust. Wiki candidates stay candidates; do not auto-write `/wiki`. | After the CEC section. |
| `/skill-audit` | Command/skill drift, duplicate mechanisms, advisory-vs-runtime gaps, or consolidation risk the rubric did not ask about. | After the CEC section. |
| `/claude-audit` | Runtime activation, stale cache, hook/plugin drift, source-vs-cache mismatch, or ground-truth freshness — runtime concerns the audit framing did not center. | After the CEC section. |
| `/review` | ONLY when there is a broader recurring engineering pattern, a test-strategy gap, or a runtime/user-surface verification gap. Not for routine reviews. | After the CEC section. |

## Examples

### Example 1 — bounded implementation report (mapping table + deferred activation)

A reconciliation task delivered a mapping table and a static test. The task
framing asked only for the mapping.

```
- observation: The mapping test passes, but the plugin that owns the
  reconciled rubric was not re-enabled after its version bump.
  why_it_matters: The reconciliation is documented but not active at runtime
  — a future run can still emit the old class set silently. Changes "done"
  into "done except runtime activation".
  evidence: settings.json enabledPlugins has no "<plugin>@local": true
  (INFERENCE — read settings.json to confirm); plugin.json version bumped.
  recommended_action: Add "<plugin>@local": true to enabledPlugins, then
  /reload-plugins. No hook gates this — prompt-advisory follow-up.
  urgency: now
```

### Example 2 — red-team verdict ("BLOCKs reports" overclaim if prompt-mediated)

A `/red-team` run returned BLOCK on the grounds that "the gate can BLOCK
reports." If that gate is a SKILL.md instruction rather than a runtime hook,
"BLOCKs reports" overclaims the enforcement authority.

```
- observation: The cited BLOCK authority is a SKILL.md instruction, not a
  runtime hook — so "BLOCKs reports" is advisory enforcement, not runtime.
  why_it_matters: Calling advisory enforcement "runtime-gated" inflates trust
  in the verdict. It changes the verdict's stated authority, not necessarily
  the verdict itself.
  evidence: No hooks.json or settings.json entry dispatches the gate;
  SKILL.md describes it as advisory (direct inspection).
  recommended_action: Down-classify the claim's protection_level to
  prompt_advisory in the CEC ledger; keep or revise the verdict on its merits.
  urgency: now
```

### Example 3 — transcript / debrief (deterministic-first LLM overuse)

A `/debrief` mining a transcript found many LLM calls where a deterministic
check would have decided.

```
- observation: A cluster of classification calls in the transcript were
  decided by an LLM where a deterministic check (regex/grep over the
  artifact) would have sufficed.
  why_it_matters: Deterministic-first ordering would cut cost and remove a
  class of "looks right" non-determinism from the pipeline. Changes future
  efficiency and confidence.
  evidence: transcript_path lines <range>; the classification is
  pattern-matchable in code at file:line (direct inspection of the
  classifier).
  recommended_action: Add a deterministic pre-pass before the LLM step;
  measure TP/FP on a held-out corpus before letting it block.
  urgency: later
```

### Negative example — what NOT to emit

These are forbidden as standalone items because they do not change a decision:

```
- observation: Be careful with scope.          # FORBIDDEN — generic caveat
- observation: More tests may be useful.        # FORBIDDEN — generic caveat
- observation: Consider documentation.          # FORBIDDEN — generic caveat
```

Each becomes acceptable only when rewritten to name the specific,
decision-changing risk — for example:

```
- observation: The new gate has no regression test pinning the payload shape
  it blocks on.
  why_it_matters: A payload-shape change would silently make the gate inert —
  the same failure mode as the prior regression. Changes maintainability.
  evidence: tests/ has no test asserting the blocked payload shape.
  recommended_action: Add a test that feeds the real runtime payload shape.
  urgency: now
```

## What this is NOT

- **Not a new command.** There is no `/thought-partner`, `/next`, `/reconcile`,
  or `/wiki-ingest`. Emission is a section inside existing reports, enforced
  structurally by `test_no_new_triggers_structural.py`.
- **Not chain-of-thought.** It surfaces conclusions and their evidence, not
  reasoning narration. No "show your work" prose.
- **Not a self-reflection checklist.** No generic "what went well / what could
  improve" — only decision-changing observations.
- **Not a license to broaden every task into an architecture review.** Trivial
  work gets no TPA.
- **Not a `/wiki` write path.** Wiki candidates stay candidates; the TPA never
  auto-writes `/wiki`.

## Falsification

This change is incomplete if future non-trivial reports still satisfy the
literal task while omitting material unasked observations that would change
priority, risk, sequencing, scope, confidence, cost, maintainability, or
long-term value. It is also incomplete if the system starts adding generic
caveats, hidden chain-of-thought, a new command, or noisy "thought partner"
sections to trivial work.
