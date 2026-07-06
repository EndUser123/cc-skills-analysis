# Capability-Preservation Check (command consolidation, absorption, stub & alias claims)

Use this whenever a review targets **command consolidation, deprecated skills,
aliases, stubs, absorbed commands, retired commands, or skill overlap** — i.e.
any claim that one command was folded into another. It exists because a past
consolidation run loosely called deprecated commands "stubs" by name; source
inspection later showed only some were true thin stubs, while others still
carried load-bearing engines, and one advertised capability pointed at an
unbuilt backend runner. Reducing the visible command count is not enough —
**every absorbed capability must resolve to an existing parent mode or be
explicitly marked pending.**

This is a judgment procedure grounded by a mechanical scaffold. Run
`scripts/capability_preservation.py` first to get the structural facts
(workflow_steps emptiness, deprecation markers, referenced backend files and
their existence), then apply the classification rubric below to those facts
plus a full read of the source.

## When to run

- Auditing a consolidation, migration, or absorption (the `/skill-audit preserve` subcommand).
- Adversarially reviewing a consolidation/migration/absorption claim under `/red-team`.
- Any time a doc says a command was "shipped", "absorbed", "stubbed", "deprecated", "internalized", "aliased", or "retired".

## Step 1 — Read the old command's actual source

Do not classify by name, header, or the first five lines. Locate and read:

1. `SKILL.md` (full body, not just frontmatter)
2. command markdown (`commands/*.md`) if the entry is a slash command
3. agent markdown (`agents/*.md`)
4. README / reference docs in the skill directory
5. plugin metadata (`.claude-plugin/plugin.json`, package `CLAUDE.md`)
6. **referenced backend scripts/runners** — anything the body points at in `__lib/`, `scripts/`, `runner.py`, `calibrate.py`, `harness_registry.py`, etc.

## Step 2 — Classify as exactly one

| Classification | Definition |
|---|---|
| `true_thin_stub` | No load-bearing engine. Only routes to a retained parent command/mode. No meaningful workflow, contract, reference engine, required artifacts, or backend runner. `workflow_steps: []` and the body is a redirect notice. |
| `retained_engine_with_deprecation_header` | Has a deprecated/redirect header but STILL contains load-bearing workflow, contract, engine description, references, or required artifacts. The engine is the source of truth; the parent reads it. |
| `internalized_engine` | The old command's engine still exists at its old path and is intentionally invoked by the parent command/mode. |
| `alias_only` | A compatibility alias with no separate behavior. |
| `pending_unimplemented` | The old command — OR the parent mode that claims to absorb it — points at a backend, runner, harness, script, or required artifact that does not exist or is explicitly marked pending. |
| `unsafe_to_remove` | The command still owns behavior not preserved by the parent command/mode. Removing it loses capability. |
| `unresolved_source_missing` | Source artifact could not be found or behavior cannot be verified. |

The mechanically-determinable facts (workflow_steps emptiness, deprecation
markers, referenced backend existence) come from the helper script; the
"load-bearing" / "unsafe" judgment is yours after reading the full body.

## Step 3 — Verify every parent absorption claim

For each parent command/mode claiming to absorb the old command:

1. the parent command/mode exists,
2. it documents the absorbed behavior accurately,
3. any referenced backend files exist on disk,
4. required artifacts/contracts still have a producer and a consumer,
5. tests or checks cover the behavior — or the gap is explicitly marked.

## Step 4 — Backend-status language rule

If a backend is pending or missing, parent docs MUST say `pending`,
`unavailable`, or `not yet implemented`. Parent docs MUST NOT say `production`,
`shipped`, `wired`, `available`, or imply working behavior.

## Step 5 — Evidence requirement

Any `shipped` / `absorbed` / `stubbed` / `implemented` / `wired` / `verified`
claim MUST cite:

- old source evidence (file:line),
- parent source evidence (file:line),
- backend existence evidence (path, or `pending` with ticket),
- validation command/output where applicable.

## Output — classification table

Emit one row per old command:

| Old command | New parent/mode | Classification | Evidence | Backend status | Capability preserved? | Required fix |
|---|---|---|---|---|---|---|

- **Backend status**: `exists` · `missing` · `pending` · `not_applicable` · `unverified`
- **Capability preserved?**: `yes` · `partial` · `no` · `unverified`

## Findings

When the check finds a missing/pending backend behind an advertised parent
mode, emit a finding:

- **Finding types**: `false_absorption_claim` (parent advertises working
  behavior the backend does not provide) · `capability_preservation_gap`
  (behavior lost with no parent coverage).
- **Severity**:
  - `BLOCK` — parent docs imply working production behavior behind a missing/pending backend.
  - `REVISE` — parent docs already say pending somewhere but the migration table / mode row is ambiguous.
  - `NIT` — wording only.

Each finding includes: `old command`, `parent command/mode`, `source evidence`,
`missing or pending backend evidence`, `user impact`, `correction`,
`verification step`, `recurrence prevention`.

## Worked example — the regression this was built from

`/adv-review` was listed as "absorbed into `/red-team adversarial`". Source
inspection showed:

- `/adv-review` SKILL.md stated the production runner (`runner.py`,
  `calibrate.py`, `harness_registry.py`) was **pending** (#872/#873/#874).
- `/red-team adversarial` mode row described dispatch to N external harnesses
  with no pending caveat → advertised production behavior.
- `/improve external-second-opinion` already documented a fallback honestly.

Classification of `/adv-review`: **`pending_unimplemented`** (not
`true_thin_stub`). Finding against `/red-team adversarial`:
`false_absorption_claim`, severity **BLOCK** → downgrade mode language to
"pending". (Applied 2026-07-06: red-team 0.2.3.)

## Falsification

This check is wrong or incomplete if a future consolidation review can still
(a) call a deprecated command a stub without reading its full source,
(b) advertise a parent mode as working while its backend is missing,
(c) reduce visible command count while silently losing capability, or
(d) claim a command was absorbed without proving the old behavior is preserved
or explicitly marked pending.
