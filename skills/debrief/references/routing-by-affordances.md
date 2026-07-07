# Routing by Affordances (read before quoting another skill's routing rule)

**Purpose.** Stop answering routing questions by quoting a skill's own docs.
Skill docs say "use X for Y" because that's the skill's self-positioning — not
because someone independent verified the routing. The rule below forces the model
to reason from the *work* to the *affordance* to the *command*, and to flag the
skill docs for audit when they disagree with the affordance analysis.

## The rule

When deciding between `/debrief`, `/improve`, `/red-team`, `/review`,
`/claude-audit`, `/skill-audit`, and `/wiki`:

1. **Identify the work** the user request requires (in one sentence).
2. **Identify the affordances** the work requires (use the categories below).
3. **Map affordances → command** by which command's machinery *actually has* them
   (not which command's docs say it handles them).
4. **State the handoff sequence** if more than one command is needed.
5. **Forbid circular justification.** "Use X because X's docs say to use X" is
   not a reason. If the only argument is the command's own self-positioning,
   name the affordance analysis explicitly or flag the docs for audit.

## Affordance categories and which command actually has them

| Affordance | What it requires | Command(s) that have it |
|---|---|---|
| **transcript/session extraction** | reads transcripts, walks session chain, parses session boundaries | `/debrief`, `/recap` (recap = no task output) |
| **source/evidence anchoring** | every claim → file:line citation, /truth gate | `/debrief` (per-finding `/truth`), `/improve` (provenance tags) |
| **bad LLM behavior detection** | rubric for false claims, name-based inference, sycophancy, goal drift | `/debrief` (internal rubric, see `bad-behavior-rubric.md`) |
| **compact/goal drift detection** | pre-compact vs post-compact behavior comparison | `/debrief` (internal compact-drift check) |
| **task/breadcrumb creation** | writes TaskCreate with 9-field template + MUST RE-VERIFY semantics | `/debrief` only |
| **durable lesson candidate extraction** | classifies findings → wiki candidate vs task vs reject | `/debrief` (mining) → `/wiki` (review/approval only) |
| **recommendation/options generation** | ≥3 options, falsification condition, confidence level | `/improve` only |
| **adversarial trust verdict** | PROCEED/REVISE/BLOCK with Health Score, specialist dispatch | `/red-team` |
| **routine code/diff review** | file:line findings against current diff | `/review` (modes: pr/diff/file/tests/errors/types) |
| **skill/command audit** | 8-category rubric scoring, contract compliance | `/skill-audit` |
| **Claude environment/config audit** | settings.json/hooks/MCP/plugins/runtime context | `/claude-audit` |
| **wiki/long-term memory candidate promotion** | writes approved durable lessons to wiki | `/wiki` only (review-gated, never auto-fired) |

## Worked example (the transcript-mining question)

User: *"I have a bunch of transcripts full of bad LLM behavior and decisions and
things that should be remembered. What's the best way to mine them?"*

**Work required:** extract bad-behavior findings, classify them, anchor them to
origin (where in code or which mechanism), decide what's a task vs a wiki
candidate vs noise.

**Affordances needed:** transcript/session extraction, source/evidence anchoring,
bad LLM behavior detection, compact/goal drift detection, task/breadcrumb
creation, durable lesson candidate extraction. **Not** needed: recommendation/
options generation (that's for already-structured artifacts), routine code/diff
review, adversarial trust verdict.

**Mapping:** all six affordances live in `/debrief`. No other retained command
has the *combination* (transcript extraction + bad-behavior rubric + task
schema + durable-lesson classification). `/improve` lacks transcript extraction
and task schema. `/recap` produces a handoff doc, no task output. `/red-team`,
`/review`, `/claude-audit`, `/skill-audit` are not transcript-mining commands.
`/wiki` is downstream of `/debrief`'s classification.

**Handoff sequence:** `/debrief` produces findings + tasks + wiki candidates →
`/improve` on the structured output if the user wants durable system-change
prioritization → `/wiki` only after human review of the candidates.

**Anti-pattern (don't do this):** "Use `/debrief` because `/improve` says not
to use `/improve` for retrospectives." That's citing `/improve`'s self-positioning
as the only reason. Correct: `/debrief` because the work requires transcript
extraction + evidence anchoring + bad-behavior rubric + task schema + lesson
classification, all of which live there.

## When docs and affordance analysis disagree

State the disagreement and prefer affordances. Examples of likely disagreements:

- A skill's docs say "use me for X" but its machinery doesn't actually do X.
  → Flag the docs for `/skill-audit` review.
- Affordance analysis says command A but docs say command B with no machinery
  basis. → Use A; flag B's docs.
- Two commands share an affordance. → Pick by the *other* affordances in the work
  (the deciding affordance usually wins).

## Anti-patterns

- **"Use X because Y says to use X."** Cite X's machinery, not X's neighbors.
- **"Use X because it has the keyword."** Trigger phrases ≠ affordances.
- **"Use the most-recent command added."** Recency ≠ fitness.
- **"Use whatever I used last time."** Memory ≠ analysis.