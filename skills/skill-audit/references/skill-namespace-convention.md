# skill-* Namespace Convention

## Rule

A skill takes the `skill-*` name prefix **iff its primary operand is another skill** — it
authored, audits, measures, searches, converts, or governs Claude Code skills. Skills whose
operand is something else (code, docs, sessions, config) do not take the prefix.

## Current family

| Name | Plugin | Instrument |
|---|---|---|
| `skill-audit` | cc-skills-analysis | Audit + improve + migrate + generate-hooks (governance) |
| `skill-write` | cc-skills-architect | Create-side super-skill: author + eval + benchmark + description-optimize + tournament (absorbed skill-creator) |
| `skill-similarity` | cc-skills-analysis | Find functionally similar skills (search) |
| `skill-from-docs` | cc-skills-architect | Convert docs/PDFs/URLs/repos → skill (conversion) |

## Excluded (by intent, not operand)

- `skill-to-page` — operand is *HTML output*, not a skill's behavior. Transform, not governance.
- `skill-guard` — this is a **plugin name**, not a skill-name pattern. The plugin's skills
  (e.g. `migrate_skill_ef`) do not take the `skill-*` skill-name prefix.
- `plugin-dev:skill-development` — operand is the *plugin authoring workflow*, broader than skills.

## Naming discipline

When adding a new skill that operates on skills, use the `skill-*` prefix and update this table.
When a skill does NOT operate on skills, do not cargo-cult the prefix — the prefix signals
affordance to routing and to `/skill-audit`'s governance scope.

## Related

- `dangling-reference-check.md` (planned) — runtime gate: every skill name in a CLAUDE.md
  table, `/ask` routing entry, or `Suggest` block must resolve to an enabled skill.
  This is the structural fix for the "dormant duplicate" class (the skill-creator
  consolidation found 4 orphan forks across 3 plugins before convergence).
