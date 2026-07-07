---
name: skill-audit
description: Unified skill audit + improvement orchestrator. Audits any Claude Code skill against an 8-category rubric (frontmatter, instructions, agent design, directory, over-engineering, references, prompt patterns P1-P8, contract compliance), produces a scored report with ranked recommendations, applies selected fixes through a 5-phase pipeline (diagnose → plan → execute → evaluate → gate), and generates skill hook packages (generate-hooks mode; absorbs /av). Use when improving an existing skill, auditing for quality, migrating frontmatter to the evidence-first contract, or generating hooks for a skill.
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion
argument-hint: <skill-path | artifact> [score|patterns|contract|partition|improve|migrate-ef|intel|generate-hooks]
enforcement: advisory
workflow_steps:
  - intake
  - diagnosing
  - planning
  - executing_fixes
  - evaluating
  - gating
---

## Routing anti-pattern: "use X because X says so"

When reviewing routing logic (skill descriptions, `## Suggest` blocks, trigger
phrases, /ask table entries), apply this anti-pattern check:

**Bad behavior to flag:**
- A skill's routing rule justifies itself by quoting another skill's
  self-positioning ("use `/debrief` because `/improve` says not to use `/improve`
  for retrospectives").
- A routing entry cites only the target skill's docs as evidence.
- A `triggers:` list contains phrases whose routing intent contradicts the
  skill's actual machinery (the skill's docs claim to do X but its scripts/
  workflow_steps show it does not).
- "Use X because X's name suggests X" — name-based inference without
  affordance evidence.

**Good behavior to recommend:**
- Routing entry states the *affordance* the work requires and which command's
  machinery actually has it.
- If two commands share an affordance, the deciding affordance is named.
- If the skill's docs and affordance analysis disagree, the entry flags the
  docs for audit (a finding, not a silent override).
- Cross-references the shared routing reference at
  `debrief/references/routing-by-affordances.md` (or the equivalent canonical
  routing doc in this repo).

**Detection cue:** any routing sentence where removing the target skill's own
docs would leave no remaining argument. Each instance becomes a `rubric_violation`
finding pointing at the specific routing sentence, with `evidence` = the quoted
routing rule and `correction` = the affordance-based rewrite.

This check is internal to `/skill-audit`'s existing rubric — no new mode, no
new command. It activates whenever the target's text contains routing claims.

# skill-audit — Unified Skill Audit + Improvement

Consolidates the prior `/quickstop:audit`, `/quickstop:improve`, `/cc-skills-sdlc:prompt-audit`,
`/cc-skills-architect:skill-craft`, `/skill-guard:migrate_skill_ef`, and `/cc-skills-sdlc:av`
skills. One entry point, one rubric, eight subcommands.

## Subcommands

Parse `$ARGUMENTS` for the subcommand. Default subcommand when only a path is given: **full audit**.

| Subcommand | Effect |
|------------|--------|
| `<path>` | Full audit: 8-category score + ranked recommendations + 5-phase improve plan |
| `score <path>` | Rubric-only — no plan, no fixes |
| `patterns <path>` | P1-P8 prompt-pattern coverage only (per the original `/prompt-audit`) |
| `contract <path>` | EF / execution-contract frontmatter compliance only |
| `partition <path>` | Determinism partition only — per-component review of whether each part should be deterministic Python, TypeScript, LangGraph, or LLM |
| `improve <path>` | Apply selected fixes from a previous audit, then re-score |
| `migrate-ef <path>` | One-shot EF migration (delegates to `skill_guard._skill_frontmatter_loader`) |
| `intel <artifact>` | Detect external skills referenced in a transcript/log/file/dir, map to our internal skills, diff, and emit ranked improvement recommendations. No rubric score — produces a *diff*, not a grade. |
| `generate-hooks <path>` | Classify skill type (EXECUTION / KNOWLEDGE / PROCEDURE) + score complexity (multi-phase / state-transitions / critical-enforcement) → recommend a hook package and write it on confirmation. Absorbs `/av`. |
| `preserve <path\|plan>` | Capability-preservation check for command consolidation / absorption / stub / alias / retirement claims. Source-backed: reads each old command's full source + referenced backends, classifies (`true_thin_stub` / `retained_engine_with_deprecation_header` / `internalized_engine` / `alias_only` / `pending_unimplemented` / `unsafe_to_remove` / `unresolved_source_missing`), verifies the parent mode and its backends, emits the classification table + `false_absorption_claim` / `capability_preservation_gap` findings. Runs `scripts/capability_preservation.py` for the mechanical scaffold; rubric in `references/capability-preservation-check.md`. |
| `prune <plugin\|all>` | Skill-sprawl triage — scans for retire (stub/deprecated/empty), merge (high token-overlap dupes), and review_primitive (single-tool wrappers) candidates. Runs `scripts/prune_scan.py` (scan-only — never deletes). **DRY-RUN by design**; archival is a manual, reviewed step (see the `prune` section). Use to attack the 167-skill sprawl without auto-deleting anything. |

## Intake — route the request

First decide audit-vs-intel. This is one branch, not a separate command.

1. If the subcommand is `intel <artifact>` **OR** the first argument is not a skill path
   (it's a `.jsonl` transcript, a `.log`/`.txt` file, an arbitrary dir of external skill
   files, or a non-skill `SKILL.md` from outside this repo) → run **`intel`** (see its
   section below). Do not score it.
2. Otherwise → resolve the target as a skill and run the audit phases.

**Intake classifier (use it)**: a path is an *artifact* (→ intel) when it is a `.jsonl`,
`.log`, `.txt`, or any `SKILL.md` whose path is NOT under
`P:/packages/.claude-marketplace/plugins/`. Everything else resolves as a skill target.

## Locate the skill

Resolve the target path:
1. If `path` is absolute and contains `SKILL.md` → use it.
2. If `path` is a directory → look for `SKILL.md` inside.
3. If `path` is a bare name (e.g. `gto`, `plugin-installer`, `cc-skills-analysis:gto`) →
   search `P:/packages/.claude-marketplace/plugins/*/skills/<name>/SKILL.md`
   (namespaced forms scope the search to the named plugin).
4. If multiple matches → use AskUserQuestion to disambiguate.

## Subcommand: prune

Triage skill sprawl without destroying anything. **Scan-only** — the scaffold
script emits candidates; archival is always a manual, human-reviewed step.

1. Run the scaffold:
   `python ${SKILL_ROOT}/scripts/prune_scan.py <plugin|all> --json` (or omit `--json`
   for the default JSON). Targets a single plugin (`cc-skills-sdlc`), a skill dir, or `all`.
2. Read the three candidate lists:
   - **retire** — stub/deprecated/empty-body (mechanical: description markers or <80-char body).
     Provenance: `INFERENCE` from a marker; confirm with `/skill-audit preserve` before removing.
   - **merge** — pairs with Jaccard ≥ 0.4 over ≥3 shared significant tokens (advisory dedupe).
     Provenance: `INFERENCE`; confirm which is canonical via `/similarity` + `/skill-audit preserve`.
   - **review_primitive** — single-tool wrappers (reuses `primitive_smells`); see Phase-1 check 6.
3. Emit an OPP-XXX-style report ( retire / keep / merge ) with provenance tags
   (`FACT(self-verified)` / `INFERENCE` / `RISK`), one row per candidate, citing the scan JSON.
4. **Never auto-archive.** If the user confirms specific retirements, archive (don't delete) by
   moving the skill dir to `P:/.data/skill-archive/<YYYY-MM-DD>/`, then run
   `plugin-audit-and-fix.py --bump <affected-plugin>` + `/reload-plugins`. Matches
   `/similarity`'s "does NOT delete" discipline and user memory #1005 ("don't auto-clean,
   confirm first").

## Verification (cold-start)

A cold-start LLM can prove the `prune` + `primitive_smells` detectors work with:

```bash
# 1) The test suite for this skill (catches the noise that drove the first
#    33-finding false-positive run; pins the wrapper signal on required patterns only):
python -m pytest plugins/cc-skills-analysis/skills/skill-audit/tests/ -q
# expect: 10 passed (5 primitive_smells + 5 prune_scan)

# 2) The CLI selfchecks (quick, no pytest):
python plugins/cc-skills-analysis/skills/skill-audit/scripts/primitive_smells.py selfcheck
python plugins/cc-skills-analysis/skills/skill-audit/scripts/prune_scan.py selfcheck

# 3) A real prune pass on this plugin (smoke):
python plugins/cc-skills-analysis/skills/skill-audit/scripts/prune_scan.py cc-skills-analysis
# expect at least: 3 retire candidates (gto, retro, top-problems — all DEPRECATED stubs).
```

The detectors are advisory only — review every finding before any archive, and never auto-apply.

## Phase 1 — Diagnose

For the default and `score` subcommands, run all six checks:

1. **Rubric scoring** — apply `${SKILL_ROOT}/references/scoring-rubric.md` (8 categories, weights).
   Includes the **adaptive-pathing** sub-check under Instruction Quality: for any skill with 3+
   phases or `workflow_steps`, grep the SKILL.md body for escape-hatch signals (`--skip-`,
   `--quick`, `--no-`, `--force`, `--dry-run`, `--legacy`, `--minimal`) and conditional-routing
   prose (`if ... fails`, `fallback`, `otherwise`, `when X`, `unless`, `on error`). Zero hits →
   apply the "Brittle single-path workflow" -10 deduction; hits → consider the +5 adaptive bonus.
   Single-purpose / knowledge / meta / <3-phase skills are exempt.
2. **Prompt pattern coverage** — grep SKILL.md and scripts for P1-P8 markers per the
   `prompt-patterns-catalog.md` at `P:/packages/cc-skills-sdlc/prompt-patterns-catalog.md`.
3. **Contract compliance** — invoke
   `python -c "from skill_guard._skill_frontmatter_loader import classify_migration_status, build_migration_result; import json, sys; print(json.dumps(build_migration_result('<path>'), indent=2))"`
   to classify frontmatter (`UNMIGRATED` / `PARTIALLY_MIGRATED` / `MIGRATED`) and list missing fields.
4. **Cross-reference integrity** — grep for `${SKILL_ROOT}` and `${CLAUDE_PLUGIN_ROOT}`
   references; verify each resolves to an existing file.
5. **Determinism partition** — apply `${SKILL_ROOT}/references/determinism-partition-rubric.md`.
   Enumerate the skill's components (each script, workflow step, agent dispatch, gate/matcher,
   output-formatter) and for each classify its *current home* vs *recommended home* across
   **{deterministic Python, TypeScript, LangGraph, LLM}**. The rubric is a top-down ladder
   (one-correct-answer → code; stateful ≥3-node branching workflow → LangGraph; judgment/prose
   → LLM). **LangGraph is a first-class option, not an afterthought** — a Python `if/elif` chain
   encoding retries + conditional routing over many nodes is a graph problem in imperative
   clothing. Emit one row per component + the summary count. `Confidence: low` rows are
   surfaced as hypotheses, never auto-applied (partition changes are architectural and hard to
   reverse). Skip for `score`-only runs if the user asked a narrower question.
6. **Primitive smells** — run `python ${SKILL_ROOT}/scripts/primitive_smells.py <skill-dir>`.
   Emits the mechanically-checkable "wrong primitive" signal: a skill whose
   `required_first_command_patterns` bind it to a single external CLI (a *wrapper*),
   cross-referenced against configured MCP servers. A wrapper with an MCP candidate →
   consider the MCP connector (hands) over a skill (habit); a wrapper with no MCP →
   confirm the skill adds LLM judgment a bare CLI/permission wouldn't. Advisory only —
   the fuzzier "deterministic body → should be a hook" judgment stays in check 5's rubric.
   Zero output until invoked, so it costs nothing on skills that don't match.

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

Determinism Partition: N components → Python: a | TS: b | LangGraph: c | LLM: d | review: e
  Top mismatches (current → recommended):
    <component>  LLM → Python   (deterministic work parked in wrong layer)
    <component>  Python(if/elif x6) → LangGraph   (stateful workflow in imperative clothing)
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

## Subcommand: `partition <path>`

Determinism partition review only (Phase-1 check #5 in isolation). Read
`${SKILL_ROOT}/references/determinism-partition-rubric.md`, then enumerate every
component of the target skill (scripts, workflow steps, agent dispatches,
gates/matchers, formatters) and classify each as **current home → recommended home**
across `{deterministic Python, TypeScript, LangGraph, LLM}`. Apply the rubric's
top-down ladder per component; cite the ladder step that fired as the `Basis`.

Rules:
- **LangGraph is a first-class candidate**, not just Python vs TS vs LLM. A workflow
  with conditional edges, retry cycles, fan-out+join, or shared mutable state across
  many nodes earns graph orchestration; a linear pipeline does not.
- **Never auto-apply** partition recommendations — they are architectural and hard to
  reverse. Emit them ranked; the user picks; Phase 3 executes (if ever).
- `Confidence: low` rows (ambiguous, needs human judgement) are stated as hypotheses
  and excluded from the "actionable" count.
- Output: one row per component per the rubric's `Output format`, then the summary
  count, then ranked recommendations of the form
  `COMPONENT / CURRENT → RECOMMENDED / BASIS → hand-off`.

## Subcommand: `intel <artifact>`

Detect external skills referenced in an evidence artifact, map each to our nearest
internal skill, diff, and emit ranked improvement recommendations. This is the only
subcommand whose input is **not** one of our skills — it's a transcript, log, text file,
external `SKILL.md`, or a directory of them. It produces a *diff*, never a rubric score.

### Flow

1. **Detect + map (deterministic)** — run
   `python "${SKILL_ROOT}/scripts/external_intel.py" <artifact> [<artifact> ...]`
   The script emits a JSON manifest: per external skill, its `invocations`, `citations`
   (`file:line`), `sources`, and a proposed `internal_match` with `confidence` +
   `match_basis` (`name` ≥0.7 / `keyword` 0.35–0.69 / `none` <0.35 / `no-internal-index`).
   Detection uses **structured signals only**: Skill tool_use blocks and `/command`
   patterns in transcripts; `SKILL.md` path mentions and slash commands in text/logs;
   directory walks for skill files. Prose mentions are NOT counted (noise).
2. **Diff (LLM judgment)** — apply `${SKILL_ROOT}/references/external-intel-rubric.md`.
   Walk axes A→E (capability, prompt-pattern, output structure, guardrails, dispatch);
   stop at the first axis that yields an actionable gap per external skill. Gate the
   strength of each recommendation on `match_basis` per the rubric's confidence table —
   weak matches are stated as hypotheses, not edited.
3. **Recommend (actionable)** — each gap becomes one recommendation of the form
   `GAP / OURS / FIX → target-path → hand-off`. The hand-off for an internal target is
   `run /skill-audit improve <target-path>`; for no target (`match_basis: none`), it's
   greenfield via `/cc-skills-architect:write-a-skill`. **Do not auto-apply** — intel
   proposes, the user picks, Phase 3 executes.
4. **Read external SKILL.md when available** — if the artifact is or contains external
   skill files, Read them before diffing; structured capability evidence beats invocation traces.

### Output shape

```
EXTERNAL-INTEL REPORT
Artifacts: <path> (kind: transcript|text|skillmd|dir, N signals)

External skill: <name>   [×N invocations]   citations: file:line, ...
  Internal match: <ours|none>   confidence: 0.XX   basis: name|keyword|none
  Gaps (axis A first):
    A. <capability ours lacks>  → FIX: ...  → /skill-audit improve <path> | write-a-skill
    ...
Ranked recommendations: [Critical/High/Medium/Low as in the rubric]
```

### Self-check

`python "${SKILL_ROOT}/scripts/external_intel.py" selfcheck` validates detection
(Skill tool_use + slash captured; drive-letter paths rejected; weak-match labeling).
Run it once after any edit to the script.

## Subcommand: `generate-hooks <path>`

Absorbs `/av` (Skill Improvement Tool). Reads the target SKILL.md, classifies it, scores hook need, then recommends + writes a hook package on confirmation.

**Engine source:** `/av`'s classification + templates remain canonical at `P:/packages/.claude-marketplace/plugins/cc-skills-sdlc/skills/av/references/` (`hook-templates.md`, `validation-checklist.md`, `output-package-and-architecture.md`, `integration-checklist.md`). This subcommand reads them; it does not vendor.

### Flow

1. **Read** the target SKILL.md.
2. **Classify** skill type:
   - `EXECUTION` — runs external tool/CLI, delegates to subagent → needs execution directive + anti-substitution block + registry entry.
   - `KNOWLEDGE` — provides reference info → no execution, no hooks.
   - `PROCEDURE` — multi-step workflow with decision points → phase gates + success criteria.
3. **Score hook need** (per `/av` complexity rubric):
   - Multi-phase workflow? +3
   - State transitions? +3
   - Critical enforcement needed? +2
   - Single command? −2
   - Reference/documentation only? −2
   - Score ≥1 → hooks recommended; ≤0 → simple recommended.
4. **Recommend** one of three packages (Simple / Hooks / Both) using the templates at `av/references/hook-templates.md` (7 templates: PostToolUse validator, state manager, PreToolUse gate, PostToolUse transition, + EXECUTION/KNOWLEDGE/PROCEDURE SKILL.md scaffolds). Output the package plan with the basis (which signals fired, the score, the chosen templates).
5. **Wait** for user choice (AskUserQuestion). Default = Simple (no hooks) when score ≤0.
6. **Write** the selected package: hook files under `<skill>/hooks/` + the `hooks:` frontmatter block (PreToolUse + PostToolUse matchers per the templates). For EXECUTION skills, also update `StopHook_skill_execution_gate.py`.
7. **Sanity check** — Read the modified SKILL.md, flag inconsistencies/missing elements/broken links, fix and report.

**Note on the `--legacy-agents` flag (#497):** rolled back agent-format migrations stay out of scope here; this subcommand generates new hook packages only.

## Subcommand: `preserve <path|plan>`

Capability-preservation check for **command consolidation, absorption, stub, alias, and retirement claims**. Use this whenever a review targets a migration table, a deprecated-skill list, an absorption map, or any doc claiming a command was "shipped / absorbed / stubbed / deprecated / internalized / aliased / retired". Reducing visible command count is not enough — every absorbed capability must resolve to an existing parent mode or be explicitly marked pending.

**Why this exists:** a past consolidation loosely called deprecated commands "stubs" by name. Source inspection later showed only some were true thin stubs; others carried load-bearing engines, and one advertised capability pointed at an unbuilt runner. See the worked example in `references/capability-preservation-check.md`.

**Procedure:**

1. Enumerate every old command the plan marks absorbed / deprecated / aliased / internalized / retired / stubbed.
2. For each, run the mechanical scaffold to get structural facts:
   ```
   python "${SKILL_ROOT}/scripts/capability_preservation.py" <old-skill-dir> --json
   ```
3. Apply the classification rubric in `references/capability-preservation-check.md` to those facts PLUS a full read of the old command's source (SKILL.md body, command markdown, agents, references, plugin metadata, referenced backend scripts). Do not classify by name or header.
4. For every parent mode claiming to absorb the old command, verify the parent exists, documents the behavior accurately, its referenced backends exist, and required artifacts still have a producer and consumer.
5. Emit the classification table and any `false_absorption_claim` / `capability_preservation_gap` findings (severity BLOCK / REVISE / NIT per the rubric). Every `shipped / absorbed / stubbed / wired` claim must cite old-source, parent-source, and backend-existence evidence.

**Discrimination cheat-sheet** (the three regression shapes, pinned by `tests/test_capability_preservation.py`):

- empty `workflow_steps` + short redirect body + no missing backend → `true_thin_stub`
- empty `workflow_steps` + deprecation header + LONG body describing an engine → `retained_engine_with_deprecation_header` (NOT a stub)
- empty `workflow_steps` + referenced `runner.py`/`calibrate.py`/`harness_registry.py` that do not exist → `pending_unimplemented` (NOT a stub)

## Error Handling

- Skill not found → report and stop.
- `--write true` not given → default is dry-run for `migrate-ef`.
- Patches fail → report error, continue with remaining, surface any partial state.
- Skill itself is in the middle of being migrated → skip if `category=meta`.

## Cross-Skill Transfer Check (XSTC)

`/skill-audit` is the canonical owner of the Cross-Skill Transfer Check
when the discovery is in the skill/command/capability-preservation layer.
Emit one XSTC in the `recommend` workflow-step output (after Phase 4). For
command-routing / consolidation / absorbed-command claims, XSTC is the
strongest discipline — owner is `/skill-audit` unless the routing itself
disagrees with the affordance analysis, in which case flag for audit.

**Advisory status:** XSTC discipline is currently prompt-advisory only.
No runtime hook enforces XSTC emission. Runtime enforcement is a future
enhancement, not a current guarantee. Any future report that claims
XSTC is `runtime_enforced` is `NOT_PROVEN` per the CEC.

## Completion Evidence Contract — required for `capability_preserved`

When reviewing skill/command consolidation, capability preservation,
aliases, stubs, absorbed commands, or any "shipped / absorbed / stubbed /
deprecated" claim, the Completion Evidence Contract is the acceptance
criterion for `capability_preserved`. The contract lives at
`debrief/references/completion-evidence-contract.md`. Required evidence:

- old-source file:line (the absorbed command's SKILL.md / command file)
- parent-source file:line (where the absorption is claimed)
- backend existence (engine / runner / harness / script path that
  actually serves the absorbed capability — not just a mention)
- behavior evidence OR explicit `pending` + `DEFERRED` status

Any one missing → `NOT_PROVEN`. Two or more missing → BLOCK. The
`scripts/capability_preservation.py` scaffold runs the four-way check; the
review's job is to demand the four pieces of evidence, not to accept a
"documented absorption" claim alone.

## Thought Partner Addendum

At the end of a non-trivial `/skill-audit` run, emit a Thought Partner
Addendum (TPA) when the audit surfaced something material the user did not ask
about — command/skill drift, duplicate mechanisms, advisory-vs-runtime gaps,
or consolidation risk the rubric did not center. Each item carries
`observation`, `why_it_matters`, `evidence`, `recommended_action`,
`urgency: now | later | watch`. Omit the section when nothing material was
found; never displace the audit verdict or the CEC ledger. Canonical contract
+ worked examples at `debrief/references/thought-partner-addendum.md`
(canonical owner: `/improve`). The TPA is prompt-advisory only.

## Partner Posture

`/skill-audit`'s posture is **Skill / Command Governance Partner** (see the
Partner Posture Map in `debrief/references/thought-partner-addendum.md`).
`/skill-audit` audits skills, commands, agents, prompts, triggers, overlaps,
aliases, stubs, capability preservation, and consolidation risk, owns
source-first classification of skill/command behavior, catches drift between
claimed and actual command behavior, and checks whether skills ask the user
for discoverable facts or duplicate shared contracts. Posture is
prompt-advisory.

## Source-first classification rule

For skill/command classification, consolidation, aliasing, stub
classification, absorbed commands, and capability preservation, every
claim requires old-source + parent-source + backend-existence evidence.
A doc-only "this command was absorbed" without all three is `NOT_PROVEN`
under the Completion Evidence Contract. The pre-flight for any
"absorbed/stub/alias" claim:

1. Read the old source. State file:line.
2. Read the parent source. State file:line.
3. Verify the backend engine/runner exists. State path.
4. Demonstrate behavior OR mark `pending` + `DEFERRED` with task id.

If any step is skipped, the claim is `NOT_PROVEN`. The
`scripts/capability_preservation.py` rubric enforces this; the
`references/capability-preservation-check.md` is the audit procedure.
Emit one XSTC in the `recommend` workflow-step output (after Phase 4). For
command-routing / consolidation / absorbed-command claims, XSTC is the
strongest discipline — owner is `/skill-audit` unless the routing itself
disagrees with the affordance analysis, in which case flag for audit.

## Discoverability audit criterion

When auditing a skill/command/agent/prompt, flag as a rubric violation any
instruction that tells the agent to ask the user for files, configs,
transcripts, line numbers, or repo facts **before** attempting local
discovery. The skill's instructions should default to: run the read-only
tool first (grep, Read, Glob, find), then ask only if the fact is
`USER_ONLY` (preference, approval, credential, intent).

Full rule at `debrief/references/discoverability-classification.md`.
A skill that instructs "ask the user for X" where X is discoverable is a
`discoverable_fact_offloading` enabler — emit as a finding with severity
REVISE (BLOCK if the instruction is load-bearing for the skill's workflow).

## Notes

- One skill, one rubric, one report. Don't rephrase the rubric — copy it from
  `references/scoring-rubric.md` so all skill audits stay comparable.
- This skill replaced `/quickstop:audit`, `/quickstop:improve`, `/cc-skills-sdlc:prompt-audit`,
  `/cc-skills-architect:skill-craft`, `/skill-guard:migrate_skill_ef`, and `/cc-skills-sdlc:av`
  (all retired or stubbed). `/av` is now a deprecation stub → `/skill-audit generate-hooks`;
  its hook templates + validation checklist stay canonical at `cc-skills-sdlc/skills/av/references/`.
- Distinct intent skills (kept separate): `/cc-skills-architect:write-a-skill` (greenfield),
  `/cc-skills-analysis:doc-compiler` (HTML output), `/cc-skills-analysis:similarity` (search).

## Suggest

`/skill-audit` cross-suggests after a run:
- `/claude-audit` — when findings implicate the runtime env (settings.json, hooks, MCP) rather than skill design.
- `/improve` — when the finding is a design or process improvement, not a skill defect.
- `/review` — when the skill has shippable code and the fix touches implementation quality.
- `/red-team` — when the skill change is high-risk (gate/hook/contract edits) and deserves adversarial review before commit.