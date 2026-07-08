# Behavioral Memory Lifecycle Reference

The decision framework for **memory entries of `metadata.type: feedback`** —
behavioral/working-style rules (e.g. "verify before recommending," "retract
when contradicted," "source-fixes over guards"). This is the subclass of
memory Phase 2.5's default logic mishandles, because the default liveness
test assumes incident/reference memory anchored to a file path or gate.

## The core mismatch (why this reference exists)

Phase 2.5's "Future-mistake test" asks: *"is this mistake now structurally
blocked (a hook, test, gate, CLAUDE.md rule)?"* For **incident/reference**
memory, "not structurally blocked" correctly signals the entry still earns
its slot — the lesson is live.

For **behavioral** memory, the answer is *"no, by definition"* — these rules
are prompt-advisory discipline, not enforcement shadows. Applying the default
prompt verbatim would archive every behavioral entry on the next audit, which
is the wrong verdict. Behavioral rules are meant to live in attention; their
liveness test must be different.

## The behavioral-specific liveness test

For `metadata.type: feedback` entries, replace "structurally blocked?" with
**"has the underlying failure mode recurred in recent sessions?"** —
detectable via `/debrief` transcript mining for the pattern.

- Recurrence present (≥1 recent instance) → the rule is live, **keep**, and
  consider whether the failure has graduated (see ladder below).
- No recurrence in a long window (≥30 sessions / ≥90 days) → two hypotheses,
  both valid, flag for the user to choose:
  1. The rule worked (discipline held) → keep, but it's a candidate for
     tightening or merging with a sibling.
  2. The failure mode is gone (context changed) → **archive** (reversible).

Do **not** auto-archive on either hypothesis — Phase 4 requires per-item user
approval regardless. The test changes the *recommendation*, not the gate.

## The memory → hook graduation ladder

A behavioral rule graduates to a hook only when it clears all four gates, in
order. Skipping a gate is the documented failure mode (see
`feedback_gate_discrimination_rule.md` — measure TP/FP on real corpus before
shipping any gate).

1. **Recurring + specific.** `/debrief` finds ≥3 instances across recent
   sessions, not one. A single session is not a pattern; one instance is the
   recency-bias trap (the rule optimizes for the last failure, not the class).

2. **Deterministic trigger exists.** You can name the exact signal — a file
   pattern, a tool-call sequence, a string in output — with low ambiguity.
   "Claude recommended adding a hook" is ambiguous (judgment-required).
   "Claude wrote to `extensions/*.ts` without a prior `grep` for the event
   name" is deterministic (grep-checkable).

3. **FP rate is measurable and acceptable.** Run the proposed check against a
   real corpus (≥3 non-discrimination cases) before it blocks anything. A
   gate that fires 0 real positives stays advisory forever.

4. **Advisory first, blocking later.** The path is memory → advisory hook
   (warns, doesn't block) → blocking hook (only after advisory measured
   clean). `diagnostic-gate-warn-mode-class-a-leak.md` documents the cost of
   shipping a gate directly in block mode.

If a rule fails any gate, it stays prompt-advisory. Failing gate #1
(single-session evidence) makes gates #2–#4 premature — the question of
hook-transfer is not yet reachable.

## Anti-pattern: the reflex toward more code

The most common failure mode around behavioral rules is **building tooling to
manage them before the rules have been observed in the wild.** A rule written
from one session's evidence has zero demonstrated behavior. Enhancing the
audit (new rubric branch, recurrence-checker integration, etc.) for such
rules is premature — it has real maintenance cost for a problem that may not
exist.

**Lazy move is correct here:** let the next `/claude-audit memory` run hit
behavioral entries with existing Phase 2.5 logic. If it misfires (wrongly
archives behavioral rules because they look like non-blocked enforcement
shadows), *then* enhance — with evidence of the actual misfire. Not before.
This reference exists so the graduation ladder and the liveness-test nuance
are not lost between sessions; it is not a mandate to build.

## Worked example (2026-07-08)

Three behavioral rules written from one session:
`feedback_verify_build_surface_before_recommending`,
`source-fixes-over-guards-default`, `retract-when-contradicted`.

| Rule | Deterministic trigger? | Gate #1 (≥3 instances)? | Verdict |
|---|---|---|---|
| Verify-before-recommending | No — "is this recommendation additive + was verification sufficient?" needs an LLM judge (expensive, high-FP, itself unverified) | No — single session | Stay advisory |
| Source-fixes-over-guards | Partial — "wrote a guard when source was editable" is detectable, but the source-fixable judgment is contextual; overfires on legit guards | No | Stay advisory |
| Retract-when-contradicted | No — conversational discipline, no clean hook surface | No | Stay advisory |

None clear gate #1, so graduation is premature for all three. Decision:
leave as prompt-advisory, add a 30-day provisional re-check (scheduler
pattern: `2026-08-05 Tier-1 watch`), and defer any audit enhancement until a
real audit run demonstrates a misfire on behavioral entries.

## Provenance

Originated 2026-07-08 from a session that produced three behavioral memory
rules and then almost over-engineered tooling to manage them. This reference
exists to preserve the graduation ladder and the liveness-test nuance without
encoding them as premature code.
