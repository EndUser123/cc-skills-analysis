# Cold-Start Handoff: cc-skills-analysis

## Status

`PARTIAL / NEEDS_FIX`

This handoff describes the actual repository state on 2026-07-12. Do not
accept earlier `PR_READY` or "all tests pass" messages without re-running the
commands below. The worktree is intentionally dirty and belongs to the
current task; preserve all existing changes.

## Start here

1. Read this file.
2. Read `CLAUDE.md` in this plugin.
3. Inspect `git status --short` and `git diff --stat` before editing.
4. Treat `HEAD` (`debaf67`) as historical context, not proof that the current
   worktree is complete.
5. Run the focused verification command before making design decisions.

Repository:

```text
P:\packages\.claude-marketplace\plugins\cc-skills-analysis
```

## Current git state

- Branch: `main`, ahead of `origin/main` by 2 commits.
- `HEAD`: `debaf67 chore(hooks,tests): update SKILL.md hook`.
- The worktree currently has a large in-progress migration: `git diff --stat`
  reports 96 tracked paths changed, 186 insertions, and 10,904 deletions. It
  also contains an untracked replacement engine tree and new tests. Do not
  interpret the deletion count as an approved cleanup without checking the
  migration source and registration path.
- Do not stage, commit, push, reset, or revert anything during initial
  investigation.

### Modified workstreams

Debrief/GTO-to-gap-engine migration:

- `.claude-plugin/plugin.json` — version `1.0.114` → `1.0.117`.
- `CLAUDE.md` — describes GTO as an internal engine and routes users through
  `/debrief gaps`.
- `skills/debrief/SKILL.md` — removes `/gto` as a public trigger and updates
  internal-engine wording.
- `skills/debrief/__lib/gto_adapter.py` and
  `skills/debrief/tests/test_gto_adapter.py` — currently deleted.
- `skills/gto/**` — currently deleted in the worktree.
- `skills/debrief/gap_engine/**` — new untracked replacement engine tree.
- `skills/debrief/__lib/gap_engine_adapter.py` and
  `skills/debrief/tests/test_gap_engine_adapter.py` — new untracked adapter
  and tests.
- `skills/debrief/tests/test_no_new_triggers_structural.py` — trigger
  allowlist changes.
- `skills/behave/SKILL.md`, `skills/friction/SKILL.md`,
  `skills/gto/README.md`, `skills/top-problems/references/flags.md` — routing
  and documentation updates.
- `skills/gto/hooks/sessionstart.py` — deleted with the old engine; verify the
  new `skills/debrief/gap_engine/hooks/sessionstart.py` registration and live
  dispatch path before accepting the migration.

Recap pre-handoff check:

- `skills/recap/SKILL.md` — adds `/recap check` and documents its advisory
  evidence scope.
- `skills/recap/__init__.py` — adds `format_pre_handoff_check()` and CLI
  routing for `check`, `--tier`, `--size`, and `--kind`.
- `skills/recap/tests/test_recap.py` — adds pre-handoff checks.
- `skills/recap/risk_calculator.py` — new deterministic tier × size × kind
  risk calculator.
- `skills/recap/tests/test_risk_calculator.py` — new calculator tests.

## Verified current results

`git diff --check` exits 0.

The latest focused commands currently report:

```text
recap + risk calculator: 40 passed, 5 skipped
recursion + trigger checks: 11 passed, 1 failed
gap-engine test collection: failed before running all tests
```

Command:

```powershell
$env:PYTHONPATH='P:\packages\.claude-marketplace\plugins\cc-skills-analysis'
python -m pytest `
  P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\recap\tests\test_recap.py `
  P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\recap\tests\test_risk_calculator.py `
  P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\tests\test_gap_engine_adapter.py `
  P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\tests\test_no_new_triggers_structural.py -q -s
```

The current blockers are:

1. Gap-engine test collection fails in
   `gap_engine/hooks/common.py` because `terminal_id` cannot be imported.
   This is an import/registration failure, not an evidence-based conclusion
   that the replacement engine is broken.
2. `test_no_new_triggers_structural.py::test_no_new_triggers_structural` —
   the live scan finds `/check`, `/dne`, and `/gap` that are not in the current
   allowlist.

These are separate failure surfaces. Do not solve the import failure by
disabling tests, and do not blindly add `/gap`, `/dne`, or `/check` until
their canonical source, intended public status, and active registration path
have been checked.

There is also an obvious source/documentation mismatch: current `debrief/SKILL.md`
and `CLAUDE.md` still describe `gto_adapter.py`, `skills.gto.__lib`, and a
`gto/` home, while the current worktree deletes those paths and introduces
`debrief/gap_engine/`. Resolve this mismatch before claiming the migration is
complete.

The focused debrief recursion file and both debrief self-checks had passed in
the prior verification, but the causal-chain test is too weak to prove the
implementation. See the open blocker below.

## Important debrief blocker

The debrief causal-chain implementation is not proven and is likely still
broken:

- `recurse_layer()` returns child findings.
- `run()` places them in `next_layer` but does not append them to the master
  `findings` list.
- `write_layer()` therefore cannot reconstruct child/parent chains in the
  final output.
- The added three-layer test only checks that the text
  `Causal chain (root cause first)` exists; it does not assert three findings,
  root/mid/top content, or ordering.

Required discriminating test:

```text
Run a three-layer extractor and assert:
- summary.total_findings == 3
- the written task contains root, middle, and top evidence
- the order is root cause → intermediate cause → symptom
- parent_id links resolve for every child
```

Also add a regression test for legacy structured inputs using `text` and
`source`. The current driver recognizes those keys but passes the original
dictionary through, while `debrief_core` reads `symptom_text` and
`symptom_source`; this can create a written finding with empty text/source.

## Recommended next branch

### Branch A — prove/fix debrief recursion

Allowed files:

- `skills/debrief/__lib/debrief_core.py`
- `skills/debrief/tests/test_routing_and_recursion.py`
- `skills/debrief/scripts/debrief.py` only if input normalization requires it

Steps:

1. Add returned child findings to the canonical findings collection, or pass a
   shared accumulator explicitly.
2. Strengthen the three-layer test with content, count, parent-link, and order
   assertions.
3. Normalize legacy `{text, source}` dictionaries into the canonical finding
   shape without losing structured opportunity fields.
4. Run the focused debrief tests, self-checks, and a direct three-layer smoke
   command.

Stop if this requires changes outside the listed files or if the verification
contract must be weakened.

### Branch B — make the gap-engine replacement importable and verifiable

1. Read `skills/debrief/__lib/gap_engine_adapter.py` and the new
   `skills/debrief/gap_engine` package instructions.
2. Trace the `terminal_id` import in `gap_engine/hooks/common.py` against both
   live roots and the active package/router topology.
3. Verify whether the replacement is intended to be a package-internal
   module or a user-facing skill.
4. Re-run the gap-engine tests after fixing only the import/registration
   boundary; do not delete tests to make collection pass.

Do not authorize a broad detector refactor from the current import failure.

### Branch C — resolve trigger-surface migration

Search both live roots before any existence/absence claim:

```powershell
rg --files -g '*gto*' P:/.claude/hooks P:/.claude/scripts P:/packages/.claude-marketplace/plugins
python P:/.claude/scripts/hooks_audit.py --packages P:/packages/.claude-marketplace/plugins
```

Determine separately whether `/gap`, `/dne`, and `/check` are:

- intentional public commands that need allowlist/registry updates;
- deprecated surfaces that need removal or a documented stub; or
- stale trigger entries that should be removed from source.

Do not make the structural test pass by editing only its allowlist.

## Verification gate

Before reporting completion, run:

```powershell
$env:PYTHONPATH='P:\packages\.claude-marketplace\plugins\cc-skills-analysis'
python P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\__lib\debrief_core.py --selfcheck
python P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\scripts\debrief.py selfcheck
python -m pytest P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\tests\test_routing_and_recursion.py -q -s
python -m pytest P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\recap\tests\test_recap.py P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\recap\tests\test_risk_calculator.py -q -s
python -m pytest P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\tests\test_gap_engine_adapter.py P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\gap_engine\tests P:\packages\.claude-marketplace\plugins\cc-skills-analysis\skills\debrief\tests\test_no_new_triggers_structural.py -q -s
git -C P:\packages\.claude-marketplace\plugins\cc-skills-analysis diff --check
git -C P:\packages\.claude-marketplace\plugins\cc-skills-analysis status --short
```

Completion requires the causal-chain smoke test and both current failure
surfaces to be resolved or explicitly classified with evidence. A focused
test pass alone is not sufficient.

## Handoff claim ledger

| Claim | Type | Evidence | Confidence | Allowed action |
|---|---|---|---|---|
| `/recap check` and risk calculator are present in the worktree | `verified_fact` | diff and files listed above | high | run focused recap tests |
| Gap-engine replacement currently fails test collection on `terminal_id` | `verified_fact` | pytest collection traceback | high | repair/import the authoritative module |
| Trigger migration is incomplete or inconsistent | `inference` | live structural scan finds `/check`, `/dne`, `/gap` | medium | inspect canonical registrations before editing |
| Old GTO source deletion is safe | `unsupported` | replacement tree is untracked and docs still reference old paths | high | prove replacement parity and registration before deletion |
| Debrief causal recursion is complete | `unsupported` | current test does not assert chain contents | high that it is unproven | add discriminating test; do not claim complete |

## Final handoff state

The next LLM should begin with Branch A, then Branch B or C depending on the
first verified result. Preserve the dirty worktree and do not commit until the
tests prove the changed behavior.
