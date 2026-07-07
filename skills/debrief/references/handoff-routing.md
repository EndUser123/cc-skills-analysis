# /debrief Handoff Routing

When `/debrief` produces structured findings, classify each into the right
destination. The classification is part of the `/debrief` state machine output;
the next-stage invocation is left to the user or to a follow-up skill that
reviews the breadcrumb.

## Per-finding destination rules

| Finding kind | Routes to | Why |
|---|---|---|
| Concrete code change or workflow fix | **Task** | Tracker entry the next LLM picks up |
| Durable lesson worth persisting | **`/wiki` candidate** | Approval-gated ingest — never auto-written |
| Root-cause is a skill's design (rubric violation, wrong affordance, false claim about capability) | **`/skill-audit`** | 8-category rubric scoring + contract check |
| Root-cause is hook/config/MCP/plugin/runtime context | **`/claude-audit`** | Settings/hooks audit surface |
| Root-cause is trust/verification (specialist output accepted unverified, fake completion pattern) | **`/red-team`** | Adversarial pass with Health Score |
| Concrete code/diff issue with file:line (not a design problem) | **`/review`** | Routine review with appropriate mode (pr/diff/file) |
| Multiple findings cluster into a durable system change worth prioritizing | **`/improve`** | Options + recommendation + falsification |
| Single occurrence, low severity, no durable value | **reject** | Recorded in breadcrumb body, not task |

## Handoff emission in `/debrief` output

After the `ACCOUNTING:` sentinel and before the breadcrumb task body, `/debrief`
emits a `HANDOFF:` block listing each finding's destination. Format:

```
HANDOFF:
  #1201 → /improve (durable system-change prioritization)
  #1202 → /skill-audit (debrief rubric violation — see bad-behavior-rubric.md)
  #1203 → /review (concrete diff issue, file:line)
  #1204 → /wiki candidate (durable lesson — subject to approval)
  #1205, #1206, #1207 → task (concrete code/workflow fix)
```

This block is the explicit handoff. Reviewers use it to invoke the next stage
without re-deriving the routing.

## Wiki gate

`/debrief` produces **candidates** for `/wiki`. It does NOT invoke `/wiki`. The
criterion-6 acceptance check in `P:/docs/consolidation-acceptance-checklist.md`
enforces this. Any future change that wires `/debrief → /wiki` ingest as
auto-fired is a regression.

## Why this is a `/debrief` responsibility

`/debrief` already classifies findings (B/C/D accounting buckets in
`task_writing_guide.md`): verified-fixed, deferred, external. The handoff
classification extends that pattern with concrete destination commands instead
of abstract buckets. The state machine's `/truth` gate ensures each routing
decision is grounded in evidence, not naming heuristics.

## Worked example (recap)

If the transcript-mining question produces:

- **Finding A** — "use `/debrief` for transcript mining because the work
  requires extraction + bad-behavior rubric + task schema": this is a routing
  observation. Routes to `/skill-audit` because it's a missing affordance
  analysis rubric in the routing layer.
- **Finding B** — "no evidence the routing reference doc existed before this
  audit": this is a documentation gap. Routes to **task** (write the doc).
- **Finding C** — "every prior transcript-mining answer cited authority without
  affordance analysis": recurring pattern. Routes to `/improve` for durable
  system-change prioritization (how to make the routing question *force*
  affordance analysis).
- **Finding D** — "the affordance mapping itself": durable lesson. Routes to
  `/wiki` candidate.

The user sees four handoff destinations in the breadcrumb, picks which to
invoke next, and is not silently routed by `/debrief`.