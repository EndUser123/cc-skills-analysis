# External-Intel Diff Rubric

Used by the `intel` branch of `/skill-audit` after `scripts/external_intel.py` emits its
manifest. The script does detection + mapping (deterministic). This rubric governs the
qualitative diff the LLM runs next: **what does the external skill do that ours doesn't,
and what's the smallest change that closes the gap.**

Sequenced: cheap/structural first, expensive/behavioral last. Stop at the first axis
that produces an actionable gap and write the recommendation — do not run all axes
reflexively.

## Diff Axes

| Axis | Question | Evidence source |
|------|----------|-----------------|
| **A. Capability coverage** | Does the external skill do something ours simply does NOT do (not worse — absent)? | Manifest `observed_signals` + external SKILL.md if available |
| **B. Prompt-pattern presence** | Does it exhibit a P1-P8 pattern (per `prompt-patterns-catalog.md`) ours lacks? | Pattern markers in external skill text vs internal skill's pattern coverage |
| **C. Output structure** | Does it produce a more useful output artifact (schema, report shape, citation)? | External output samples in transcript |
| **D. Guardrails** | Does it carry a check our equivalent lacks (regression guard, fidelity gate, falsification step)? | External SKILL.md guardrail section |
| **E. Intake / dispatch** | Does it route or branch on input in a way ours doesn't (e.g. multi-modal intake)? | External dispatch logic |

## Mapping the gap to an action

Each gap becomes ONE recommendation of the form:

```
GAP: <external-skill> does <X> via <evidence-citation>
OURS: <internal-skill-or-null> currently <state>
FIX: <concrete change>
  → target: <internal skill path>   (if null, → greenfield: /cc-skills-architect:write-a-skill)
  → hand-off: run `/skill-audit improve <target-path>` with the patch below, OR apply directly
```

Tie each fix to an existing rubric category where one exists (Frontmatter, Prompt Patterns,
Agent Design, etc. from `scoring-rubric.md`). If the capability doesn't map to any
category, that's signal — it's genuinely new, and the fix is greenfield, not an edit.

## Confidence handling

The manifest's `internal_match.confidence` + `match_basis` gate how hard to push a fix:

| match_basis | confidence | Action |
|-------------|------------|--------|
| `name` | ≥ 0.7 | Direct diff is safe; propose edits to the matched internal skill |
| `keyword` | 0.35–0.69 | Treat the match as a *hypothesis*. State it as "possibly maps to X — verify before editing" |
| `none` / `< 0.35` | — | No internal counterpart; recommend greenfield via `write-a-skill`, do not edit |
| `no-internal-index` | — | Internal skill index missing/empty; surface as a setup problem, do not guess |

## Out of scope for intel

- Do NOT re-score the internal skill against the 8-category rubric — that's the default
  subcommand's job. Intel produces a *diff*, not a score.
- Do NOT auto-apply edits. Intel proposes; the user picks; Phase 3 (`improve`) executes.
- Do NOT infer capabilities from prose mentions in transcripts — only from structured
  invocation evidence (Skill tool_use blocks, slash commands, or a read of the external
  SKILL.md itself). Prose mentions are noise.
