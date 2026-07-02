---
name: skill-audit
description: Unified skill audit + improvement orchestrator. Audits any Claude Code skill against an 8-category rubric (frontmatter, instructions, agent design, directory, over-engineering, references, prompt patterns P1-P8, contract compliance), produces a scored report with ranked recommendations, and applies selected fixes through a 5-phase pipeline (diagnose → plan → execute → evaluate → gate). Use when improving an existing skill, auditing for quality, or migrating frontmatter to the evidence-first contract.
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion
argument-hint: <skill-path> [score|patterns|contract|improve|migrate-ef]
enforcement: advisory
workflow_steps:
  - locating_skill
  - diagnosing
  - planning
  - executing_fixes
  - evaluating
  - gating
---

# skill-audit — Unified Skill Audit + Improvement

Consolidates the prior `/quickstop:audit`, `/quickstop:improve`, `/cc-skills-sdlc:prompt-audit`,
`/cc-skills-architect:skill-craft`, and `/skill-guard:migrate_skill_ef` skills. One entry
point, one rubric, six subcommands.

## Subcommands

Parse `$ARGUMENTS` for the subcommand. Default subcommand when only a path is given: **full audit**.

| Subcommand | Effect |
|------------|--------|
| `<path>` | Full audit: 8-category score + ranked recommendations + 5-phase improve plan |
| `score <path>` | Rubric-only — no plan, no fixes |
| `patterns <path>` | P1-P8 prompt-pattern coverage only (per the original `/prompt-audit`) |
| `contract <path>` | EF / execution-contract frontmatter compliance only |
| `improve <path>` | Apply selected fixes from a previous audit, then re-score |
| `migrate-ef <path>` | One-shot EF migration (delegates to `skill_guard._skill_frontmatter_loader`) |

## Locate the skill

Resolve the target path:
1. If `path` is absolute and contains `SKILL.md` → use it.
2. If `path` is a directory → look for `SKILL.md` inside.
3. If `path` is a bare name (e.g. `gto`, `plugin-installer`, `cc-skills-analysis:gto`) →
   search `P:/packages/.claude-marketplace/plugins/*/skills/<name>/SKILL.md`
   (namespaced forms scope the search to the named plugin).
4. If multiple matches → use AskUserQuestion to disambiguate.

## Phase 1 — Diagnose

For the default and `score` subcommands, run all four checks:

1. **Rubric scoring** — apply `${SKILL_ROOT}/references/scoring-rubric.md` (8 categories, weights).
2. **Prompt pattern coverage** — grep SKILL.md and scripts for P1-P8 markers per the
   `prompt-patterns-catalog.md` at `P:/packages/cc-skills-sdlc/prompt-patterns-catalog.md`.
3. **Contract compliance** — invoke
   `python -c "from skill_guard._skill_frontmatter_loader import classify_migration_status, build_migration_result; import json, sys; print(json.dumps(build_migration_result('<path>'), indent=2))"`
   to classify frontmatter (`UNMIGRATED` / `PARTIALLY_MIGRATED` / `MIGRATED`) and list missing fields.
4. **Cross-reference integrity** — grep for `${SKILL_ROOT}` and `${CLAUDE_PLUGIN_ROOT}`
   references; verify each resolves to an existing file.

## Phase 2 — Plan

Output the unified report. Format per `references/scoring-rubric.md` §"Report Format",
with two extra category rows (Prompt Patterns, Contract Compliance) and the P1-P8
coverage table.

```
╔══════════════════════════════════════════════════════════╗
║                 SKILLET QUALITY REPORT                   ║
║  Skill: <name>  | Overall: XX/100  Grade: X  (Label)    ║
╚══════════════════════════════════════════════════════════╝

Frontmatter              ████████████████████░░░░░  XX/100  X
Instruction Quality      ████████████████████░░░░░  XX/100  X
Agent Design             ████████████████████░░░░░  XX/100  X
Directory Structure      ████████████████████░░░░░  XX/100  X
Over-Engineering         ████████████████████░░░░░  XX/100  X
Reference & Tooling      ████████████████████░░░░░  XX/100  X
Prompt Pattern Coverage  ████████████████████░░░░░  XX/100  X
Contract Compliance      ████████████████████░░░░░  XX/100  X

Prompt Patterns (P1-P8):
  P1 <name>   PRESENT | PARTIAL | MISSING
  ...
Contract Status: MIGRATED | PARTIALLY_MIGRATED | UNMIGRATED
  Missing fields: contract_type, required_artifacts, response_requirements
```

Then rank recommendations (Critical / High / Medium / Low per the rubric's ranking table).

## Phase 3 — Execute (interactive)

Use AskUserQuestion (multiSelect) to let the user pick which recommendations to apply.
Then apply each: Read the target file, Edit/Write the fix, briefly explain what changed.

Skip this phase entirely for `score` / `patterns` / `contract` subcommands (read-only).

## Phase 4 — Evaluate

After applying fixes, re-score the affected categories only. Show a delta block:

```
Score Delta:
  Frontmatter     65 → 85  (+20)
  Contract Compliance 30 → 100  (+70)  (was UNMIGRATED, now MIGRATED)
  Overall         72 → 84  (+12)  Grade: C → B
```

For `migrate-ef`, the "delta" is just the migration result (status before → after,
list of fields added).

## Phase 5 — Gate

Fidelity gate — verify the changes are consistent with the skill's own contract:
- If the skill has `enforcement: strict` or `layer1_enforcement: true`, the audit must
  not relax those fields.
- If the skill declares `contract_type`, the `migrate-ef` action must not remove it.
- The new score must be ≥ the old score on every category that was modified (regression
  guard). If any category dropped, surface it and offer to revert.

Print `craft-done` when the gate passes.

## Subcommand: `migrate-ef <path>`

Delegates to `skill_guard._skill_frontmatter_loader`:
- `classify_migration_status(frontmatter)` → UNMIGRATED / PARTIALLY_MIGRATED / MIGRATED
- `build_migration_result(skill_dir)` → dict with `status`, `missing_fields`, `suggested_patches`

Apply patches only when `--write true` is in the arguments; otherwise print the diff
plan. Default is dry-run.

## Subcommand: `patterns <path>`

Read `P:/packages/cc-skills-sdlc/prompt-patterns-catalog.md` to get P1-P8 definitions.
For each pattern, grep the target SKILL.md and any scripts in the skill directory
for pattern markers (keywords, function names, output format strings). Report
PRESENT / PARTIAL / MISSING per pattern.

## Subcommand: `contract <path>`

Read the target's frontmatter. Call `classify_migration_status` directly. Report:
- status (UNMIGRATED / PARTIALLY_MIGRATED / MIGRATED)
- missing fields
- whether `category` is `knowledge` or `meta` (which are exempt from contract enforcement)

## Error Handling

- Skill not found → report and stop.
- `--write true` not given → default is dry-run for `migrate-ef`.
- Patches fail → report error, continue with remaining, surface any partial state.
- Skill itself is in the middle of being migrated → skip if `category=meta`.

## Notes

- One skill, one rubric, one report. Don't rephrase the rubric — copy it from
  `references/scoring-rubric.md` so all skill audits stay comparable.
- This skill replaced `/quickstop:audit`, `/quickstop:improve`, `/cc-skills-sdlc:prompt-audit`,
  `/cc-skills-architect:skill-craft`, and `/skill-guard:migrate_skill_ef` (all retired).
- Distinct intent skills (kept separate): `/cc-skills-architect:write-a-skill` (greenfield),
  `/cc-skills-analysis:doc-compiler` (HTML output), `/cc-skills-analysis:similarity` (search).