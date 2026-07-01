# Opportunity Task Template

Used by `debrief_core.write_opportunity_layer()`. Lateral lifecycle
(`FindingKind.OPPORTUNITY`) — distinct from the defect template
(`assets/task_template.md`). A defect task is anchored at a code
line that has to change; an opportunity task is anchored at a
transcript moment that has to be promoted.

```
TLDR:       <opportunity in one line — what's reusable>
TITLE:      <opportunity as an imperative: "Promote ... to ...">
TASK_KIND:  opportunity-full   (or opportunity-lite for trivial)
PARENT_TASK: <#<id> if an existing task is the right anchor>
SEED:       <exact transcript moment + line citation>
IDEA:       <the reusable pattern / workflow / heuristic discovered>
WHY:        <expected future leverage — what value does this generalize?>
EVIDENCE:   explicit_user_ask | user_correction | repeated_pattern | inferred | weak
PROMOTE_TO: cks | skill | memory | docs | backlog | reject
GENERALIZATION_TEST: <how to prove this works beyond this one chat>
ACTION:     <concrete next step — what task to create, what file to update, what memory entry to write>
APPLIES_TO: coding | research | writing | debugging | workflow | tool | unknown
PROMOTION_TARGET: <the existing artifact or hook this should land in, if any>
```

## Field notes

- **PROMOTE_TO** is the routing decision. Six values, ranked by urgency:
  - `skill` — generalize into a skill update (e.g., update `SKILL.md`,
    add a new task template).
  - `hook` — codify as a PreToolUse / PostToolUse hook that fires
    automatically.
  - `docs` — update `CLAUDE.md` / README / handbook with the rule.
  - `memory` — durable user-specific or session-specific preference
    (e.g., "I always want opportunity findings to skip the breadcrumb
    pattern").
  - `cks` — constitutional knowledge entry that future sessions will
    retrieve.
  - `backlog` — worth doing but not now; a deferred task.
  - `reject` — not worth preserving. Use this when `EVIDENCE` is
    `weak` or `inferred` without supporting `GENERALIZATION_TEST`.

- **EVIDENCE strength** matters a lot. A finding with `EVIDENCE:
  explicit_user_ask` plus a `GENERALIZATION_TEST` that has a
  discriminating step is the gold standard. A finding with `EVIDENCE:
  weak` and no generalization test should be rejected, not promoted.

- **APPLIES_TO** is the cross-domain transfer flag. The original user
  ask said ideas should improve quality "in any domain." If the
  opportunity is domain-specific (e.g., "this prompt-engineering trick
  works for code"), say so. If it generalizes, name the other domains.

- **PROMOTION_TARGET** names the specific artifact the opportunity
  should land in, when known: a skill name, a hook name, a memory
  filename, a doc path. Empty if the promotion target is "TBD."

## Promotion anti-patterns (rejection rules)

Reject or downgrade an opportunity when:

- `EVIDENCE` is `weak` and `GENERALIZATION_TEST` is empty.
- The idea is vague praise with no reusable behavior.
- The idea is based on one hallucinated claim.
- The idea duplicates an existing skill behavior.
- The idea is a user-specific preference incorrectly generalized.
- The idea would create more interruptions or process drag.

A finding with anti-patterns should be `PROMOTE_TO: reject` with a
one-line reason. Don't pad the promotion list with weak candidates.

## Distinction from the defect template

| Aspect | Defect (task_template.md) | Opportunity (this file) |
|--------|--------------------------|------------------------|
| Anchor | file:line (code) | transcript moment (idea) |
| Origin | symptom → cause → code | seed → generalization → promotion |
| Test | `read <file> around line N` | `does it generalize?` |
| Action | `fix <file>` | `promote to <target>` |
| Failure | failing repro gone | weak ideas get rejected, not promoted |
| Anti-pattern | padding empty DEAD ENDS | padding empty GENERALIZATION_TEST |

Both templates share: `TLDR`, `PARENT_TASK` semantics, the
cold-start requirement that the next LLM can pick up the task cold
and act on it without re-reading the source transcript.

## What to write in the SEED field

The seed is the **exact transcript moment** the idea came from, with
line citation. Format:

```
SEED: transcript L4823 ("this trick really worked — we should
      generalize it to all code patterns")
```

The SEED field is the audit trail. Without it, the opportunity is
just an ungrounded assertion and the next LLM has to take it on
faith. With the SEED, the next LLM can verify the opportunity
against the source.
