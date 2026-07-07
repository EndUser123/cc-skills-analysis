# Cross-Skill Transfer Check

When a failure class or fix class is discovered while running any retained
command (`/improve`, `/red-team`, `/review`, `/debrief`, `/claude-audit`,
`/skill-audit`, `/wiki`), answer this question before closing:

> Is this failure/fix **local to the current artifact**, or is it a **reusable
> class** that should be checked across related skills, commands, hooks,
> gates, workflows, or memory/wiki processes?

## Required fields

Emit one Cross-Skill Transfer Check (XSTC) artifact per retained-command run
when the discovery is non-trivial. Fields:

| Field | Required | Definition |
|---|---|---|
| `classification` | yes | One of: `local_only`, `applies_to_related_skills`, `applies_to_hooks_or_gates`, `applies_to_command_routing`, `applies_to_transcript_mining`, `applies_to_external_review`, `applies_to_wiki_or_memory`, `unsure_needs_audit`. |
| `affected_surfaces` | yes | Comma-separated list of retained commands + plugin/hook names the fix could touch. |
| `evidence` | yes | Concrete file:line citations or transcript offsets. **No vibes.** |
| `why_it_transfers_or_not` | yes | One sentence stating why the class is reusable (or why it's local). |
| `owner` | yes | The retained command best positioned to drive the fix. One of: `/improve`, `/red-team`, `/review`, `/debrief`, `/claude-audit`, `/skill-audit`, or "shared routing reference." |
| `recommended_action` | yes | The smallest change that would address the class across the surfaces listed. |
| `validation_step` | yes | One command, test, or read whose output proves the fix worked. |
| `do_now_or_backlog` | yes | Either `do_now` (block current work) or `backlog` (create a tracker task). |

## Rules

1. **Evidence or audit.** No vibes. If you cannot cite a `file:line` or
   transcript offset, mark `classification: unsure_needs_audit`.
2. **No circular routing.** Do not cite another skill's routing text as the
   only evidence. If the fix class affects command choice, run the
   affordance-based routing analysis at
   `debrief/references/routing-by-affordances.md` to determine owner.
3. **Owner selection by layer.** Use this table when the class is not
   local:

   | Class of fix | Owner |
   |---|---|
   | Command-routing / capability-preservation / consolidation claims | `/skill-audit` (or shared routing reference) |
   | Transcript / session mining / bad-LLM-behavior detection | `/debrief` |
   | Runtime hooks / config / MCP / plugin / context-injection | `/claude-audit` |
   | Trust / ship-readiness / adversarial verdict | `/red-team` |
   | Durable system-change recommendation | `/improve` |
   | Routine code/diff review patterns (recurring, not one-off) | `/review` |
   | Reusable lesson worth preserving across sessions | `/wiki` candidate (after evidence + uniqueness + approval) |

4. **One XSTC per run.** Don't emit multiple for the same discovery; one
   check covers all surfaces the discovery touches.

## Where to emit

| Retained command | Emit position |
|---|---|
| `/improve` | After `Recommendation`, before `Persistence` |
| `/debrief` | After `ACCOUNTING:` sentinel + `HANDOFF:` block, before breadcrumb |
| `/red-team` | In `Recommended Next Steps` (after verdict, not above it) |
| `/skill-audit` | In the `recommend` workflow step output |
| `/review` | Only when a recurring code-review/test-quality pattern (≥2 occurrences) is found, in `## Output` |
| `/claude-audit` | In `Phase 2.7: Cross-Skill Transfer` (new section if needed) |
| `/wiki` | N/A — `/wiki` is downstream persistence only |

## Worked examples (canonical, copy-shape)

**Example A — parrot routing.**

Finding: model chose `/debrief` by parroting `/improve`'s docs instead of
reasoning from affordances.

```yaml
classification: applies_to_command_routing
affected_surfaces: /improve, /debrief, /red-team, /review, /skill-audit, /claude-audit
evidence: |
  - cc-skills-analysis/skills/debrief/references/routing-by-affordances.md (anti-parrot section)
  - improve-partner/skills/improve/SKILL.md:39 ("Routing — read before invoking")
owner: /skill-audit (shared routing reference lives under it)
recommended_action: keep the per-command Routing/Boundary/Pre-check/Escalation
  sections + the routing-by-affordances.md doc + the test_routing_by_affordances.py
  regression guard. Verify on the next routing question.
validation_step: |
  cd plugins/cc-skills-analysis/skills/debrief && python -m pytest \
    tests/test_routing_by_affordances.py
do_now_or_backlog: do_now (close already verified, just keep it)
```

**Example B — lazy stub classification.**

Finding: deprecated commands called stubs without reading full source.

```yaml
classification: applies_to_related_skills
affected_surfaces: /skill-audit, /red-team, /improve, /debrief
evidence: |
  - debrief/SKILL.md:197 ("After-action rubric — false absorption / lazy stub classification")
  - skill-audit/scripts/capability_preservation.py (scaffold)
  - skill-audit/references/capability-preservation-check.md (rubric)
owner: /skill-audit
recommended_action: ensure every consolidation/absorption claim cites
  old-source + parent-source + backend-existence evidence before
  classifying as stub/absorbed/deprecated.
validation_step: |
  run skill-audit preserve on one in-flight consolidation plan; verify
  the output cites all three evidence sources.
do_now_or_backlog: do_now (rubric already shipped; verify on next consolidation)
```

**Example C — local one-off.**

Finding: one transcript shows a one-off wording issue.

```yaml
classification: local_only
affected_surfaces: none
evidence: |
  - transcript:line — the specific turn
owner: none
recommended_action: no system-wide change
validation_step: n/a
do_now_or_backlog: backlog (record in breadcrumb; do not promote)
```

## Why this exists

A single artifact, emitted at the right spot in each retained command, turns
"should I generalize this?" from a vibes question into a structured gate. The
classification values are deliberately coarse (8 values, not 30) so the LLM
can decide quickly without inventing new categories.

This is the **transfer** analog of the existing **hierarchy** rules
(routing-by-affordances.md): hierarchy says "which command fits this work";
transfer says "should this work's fix reach other commands." Both are
affordance-driven; both are evidence-gated; both forbid circular justification.