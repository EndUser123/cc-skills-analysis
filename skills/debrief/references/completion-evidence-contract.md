# Completion Evidence Contract

## Bump evidence convention

When bumping plugins with `plugin-audit-and-fix.py --bump`, capture **full
stdout** (not just the tail) by redirecting to a log file:

```bash
python plugins/cc-skills-utils/scripts/plugin-audit-and-fix.py \
  --bump <plugin> --marketplace-root P:/packages/.claude-marketplace \
  2>&1 | tee /tmp/bump-<plugin>.log
```

In the Completion Evidence Ledger, cite the log file and quote the
`Zero drift confirmed` literal — not just the `=== Done ===` line.

Recommended report format:
```
claim_type: plugin_bumped / cache_rebuilt / drift_checked
evidence_provided: /tmp/bump-<plugin>.log → "Zero drift confirmed for <plugin>."
status: PROVEN
protection_level: runtime_enforced
```

A `=== Done ===` line alone (without the `Zero drift confirmed` literal) is
PARTIAL at best.

# Completion Evidence Contract

Every final implementation report must include a **Completion Evidence Ledger** —
one row per completion claim, each typed and proven from the correct authority.

## Report-time enforcement (Close-the-Loop Phase 4)

This contract is enforced at report time, not only at `/debrief` after-action
mining. The mechanical check lives in
`cc-aca-epistemic/hooks/stop/Stop_fake_done_detector.py` (Tier 4, WARN mode):
a response is implementation-report-shaped when it carries a completion claim
("done", "fixed", "verified", "shipped", "complete") AND either (a) the output
mentions concrete code artifacts (file paths, plugin names, hook names, packet
sections) or (b) follows an `/improve`/`/claude-audit`/`/red-team`/`/skill-audit`
output shape. When the shape matches but **no ledger is present** (no markdown
table whose header row contains `claim` + `claim_type`/`status`/`evidence`, and
no fenced yaml block with `claim_type:` + `evidence_provided:`), the detector
WARNs:

> MISSING COMPLETION LEDGER — you claimed completion on an
> implementation-report-shaped response but did not include a Completion
> Evidence Ledger (per `completion-evidence-contract.md`). Add one row per
> completion claim.

The delta vs. the existing Tier 1/1.5/2 tiers: those check whether **evidence
exists** for a single claim. This tier checks whether **the report itself is
structured to make every claim auditable** — the contract's structural
requirement, not a per-claim verification. It does NOT re-verify any claim.
That authority stays with `/red-team` (BLOCKs ledger-less reports on review)
and the existing claim-verification gates.

Promotion to BLOCK requires measured corpus signal (Phase 6 yield review,
earliest ~2026-07-21): ≥5 real implementation-report-shaped completions where
the ledger presence correlated with the report's eventual verdict (REVISE for
ledger-less, PROCEED for ledger-bearing). Until then the tier is WARN, advisory.



The contract exists because bare "done," "tests green," "zero drift,"
"constraints satisfied," and "guardrail enforced" claims all conflate different
authorities. A SKILL.md edit is not runtime enforcement. A text-existence test
is not a behavior eval. A `plugin-audit-and-fix.py --bump` exit code is not
user-visible command activation. This contract forces the disambiguation.

## Completion Evidence Ledger (one row per claim)

| Field | Required | Definition |
|---|---|---|
| `claim` | yes | The completion statement exactly as it appears in the report. |
| `claim_type` | yes | One of the 16 enum values below. |
| `authority_required` | yes | Who/what must produce the evidence for this claim to be PROVEN. |
| `evidence_provided` | yes | The exact command output, file:line citation, or test result. No vibes. |
| `status` | yes | One of: `PROVEN`, `PARTIAL`, `NOT_PROVEN`, `DEFERRED`, `NOT_APPLICABLE`. |
| `protection_level` | yes | One of the 6 enum values below. |
| `remaining_gap` | yes (or `none`) | What would have to change to upgrade `status`. |
| `next_action` | yes (or `none`) | The smallest next step that closes the gap. |

### `claim_type` enum (16 values)

| Claim type | What it asserts | Authority required |
|---|---|---|
| `file_changed` | A file was edited in this work. | Edit/Write tool receipt + Read of the modified lines. |
| `test_passed` | A test ran green. | pytest output line `N passed`. |
| `plugin_bumped` | Plugin version incremented and cache rebuilt. | `plugin-audit-and-fix.py --bump` exit code + the `=== Done ===` line. |
| `cache_rebuilt` | The plugin cache is current. | Bump output + the `Zero drift confirmed` literal line. |
| `drift_checked` | Source and cache match. | `plugin-audit-and-fix.py --drift` exit 0 OR the `Zero drift confirmed` literal. |
| `command_surface_changed` | A user-visible slash command was added/removed/changed. | Structural diff of `triggers:` blocks (not just a token regex) AND/OR `claude plugin list` before/after. |
| `runtime_behavior_changed` | A live hook/state-machine/orchestrator now behaves differently. | Live smoke proof or recorded behavior change. |
| `user_visible_behavior_verified` | A user path (slash command → orchestrator → output) was driven end-to-end. | Executed command + observed output. |
| `wiki_not_written` | `/wiki` was not auto-written to. | Grep across `plugins/` for `/wiki ingest` in `workflow_steps:`/`triggers:` + no `wiki_after_write` import wired. |
| `external_model_available` | An external LLM call succeeded. | Actual call stdout with model id + response excerpt. |
| `guardrail_added` | A new gate/hook/check exists in source. | File:line of the new gate + Read of its activation path. |
| `guardrail_runtime_enforced` | The gate fires in the live dispatch path. | Live smoke test OR direct invocation `python gate.py < sample.json` showing the gate output. |
| `capability_preserved` | An absorbed/stubbed/aliased command preserves the source capability. | Old-source file:line + parent-source file:line + backend existence (engine/script path) + behavior evidence OR explicit `pending`. |
| `documentation_updated` | A doc was added/edited. | Edit receipt + Read of the new lines. |
| `deferred_work` | An item was intentionally deferred to a tracker. | Tracker task id (`#NNN`) or `pending (no task yet)`. |
| `unresolved_gap` | An item is acknowledged but unaddressed. | The unaddressed item itself + the smallest path to address. |

### `status` enum

- `PROVEN` — `evidence_provided` is sufficient to assert the claim from `authority_required`.
- `PARTIAL` — Some evidence exists but a weaker authority than required (e.g., text-test instead of behavior-eval).
- `NOT_PROVEN` — No evidence exists or the evidence is from the wrong authority.
- `DEFERRED` — Evidence exists but is intentionally deferred to a later run; cite the task id.
- `NOT_APPLICABLE` — The claim does not apply to this work; state why.

### `protection_level` enum

- `documentation_only` — A doc or reference was edited; nothing else.
- `prompt_advisory` — A SKILL.md section instructs the model; not enforced.
- `static_invariant_tested` — A pytest test asserts text/file existence.
- `behavior_eval_tested` — A pytest test asserts output from a real execution.
- `runtime_enforced` — A hook/gate fires in the live dispatch path.
- `runtime_enforced_and_regression_tested` — Runtime-enforced AND covered by a regression test that fails when the gate regresses.

## Rules (hard)

1. **No bare "done."** Every completion claim must have a row. "Done" without a row is PROHIBITED.
2. **A SKILL.md / reference doc edit is NOT runtime enforcement.** If you edit a doc and call it a guardrail, the row's `claim_type` is `documentation_updated` with `protection_level: documentation_only` or `prompt_advisory`, NOT `guardrail_runtime_enforced`.
3. **A test that checks text exists is NOT proof future LLMs follow it.** Text-tests prove the text exists. They do not prove behavioral compliance. Use `protection_level: static_invariant_tested`, not `behavior_eval_tested`.
4. **Plugin bump ≠ user-facing activation.** A `plugin-audit-and-fix.py --bump` exit code proves the bump ran. It does NOT prove the user's `/` command menu now contains the new command. For that, you need a `claude plugin list` before/after, or an actual command invocation.
5. **"Zero drift" requires the literal `Zero drift confirmed` line in command output.** A bump that exited 0 is not the same as a drift check that printed the literal.
6. **"No new commands" requires a structural `triggers:` diff OR a `claude plugin list` before/after.** A static test forbidding a few token strings is `PARTIAL`, not `PROVEN` — new commands can use new tokens.
7. **"Capability preserved" requires all four pieces of evidence.** Old source file:line + parent source file:line + backend existence (engine / runner / harness script path) + behavior evidence OR explicit `pending` + `DEFERRED` status. Any one missing is `NOT_PROVEN`.
8. **"External model available" requires an actual call.** If the call was not made, mark `NOT_PROVEN` or `DEFERRED`; do not claim availability from docs.
9. **Unresolved items appear as `PARTIAL`, `NOT_PROVEN`, or `DEFERRED` rows — NOT under "constraints satisfied."** The Verdict must reflect the ledger: if any non-`NOT_APPLICABLE` row is `NOT_PROVEN`, the verdict is REVISE.
10. **If a guardrail is advisory only, say so.** `claim_type: guardrail_added` + `protection_level: prompt_advisory` is honest. `protection_level: runtime_enforced` for an advisory-only gate is an overclaim.

**Example E — retrofitted ledger on a prior report.**

A retrospective run of the contract against a report that previously claimed
"✅ constraints satisfied." The honest ledger surfaces what was PROVEN, what
was PARTIAL, and what was NOT_PROVEN. The verdict derived from this ledger
is REVISE — not PROCEED — even though the original report carried ✅ on
every line.

```yaml
- claim: "no new top-level commands created"
  claim_type: command_surface_changed
  authority_required: structural triggers: diff OR claude plugin list before/after
  evidence_provided: "test_no_new_top_level_command_added forbade 4 tokens (/wiki-ingest, /transcript-mine, /debrief-miner, /mine-transcripts); test passed"
  status: PARTIAL
  protection_level: static_invariant_tested
  remaining_gap: token-regex misses new commands with new tokens; no structural diff; no claude plugin list snapshot
  next_action: replace the 4-token regex with a structural triggers-diff test; run claude plugin list before/after

- claim: "XSTC discipline is enforced by SKILL.md sections + text-existence tests"
  claim_type: guardrail_runtime_enforced
  authority_required: live hook + behavior eval that fails when XSTC absent
  evidence_provided: "6 SKILL.md files have ## Cross-Skill Transfer Check (XSTC) sections; 24 pytest tests assert text existence"
  status: NOT_PROVEN
  protection_level: prompt_advisory
  remaining_gap: no behavioral eval; no runtime hook
  next_action: add Stop-tier XSTC emission check OR re-label sections as prompt_advisory

- claim: "4 plugins bumped, zero drift on all four"
  claim_type: drift_checked
  authority_required: literal "Zero drift confirmed" line in plugin-audit-and-fix.py output
  evidence_provided: "only the === Done === tail line captured per plugin; the explicit Zero drift line not in evidence"
  status: PARTIAL
  protection_level: documentation_only
  remaining_gap: bump stdout was tailed (last 3 lines), not full-stdout captured
  next_action: capture full --bump stdout (not just tail) in future reports

- claim: "wiki not auto-written"
  claim_type: wiki_not_written
  authority_required: grep across plugins/ for /wiki ingest in workflow_steps/triggers + no wiki_after_write import wired
  evidence_provided: "test_no_debrief_to_wiki_auto_wire (single-skill scope) passed"
  status: PARTIAL
  protection_level: static_invariant_tested
  remaining_gap: scope is single-skill; whole-repo grep would be stronger
  next_action: extend test to whole plugins/ tree

- claim: "all 24 routing tests pass"
  claim_type: test_passed
  authority_required: pytest output line "N passed"
  evidence_provided: "tests/test_routing_by_affordances.py: '24 passed in 1.82s'"
  status: PROVEN
  protection_level: behavior_eval_tested
  remaining_gap: none
  next_action: none
```

Verdict from this ledger: **REVISE** (3 PARTIAL + 1 NOT_PROVEN rows). The
original report's "✅ constraints satisfied" line is itself the overclaim
the contract catches.

## Worked examples (canonical, copy-shape)

**Example A — overclaim of "enforcement."**

Claim: "XSTC discipline is enforced by SKILL.md sections and tests that text exists."

```yaml
- claim: XSTC discipline is enforced by SKILL.md sections + text-existence tests
  claim_type: guardrail_runtime_enforced
  authority_required: live hook + behavior eval that fails when XSTC absent
  evidence_provided: "6 SKILL.md files have ## Cross-Skill Transfer Check (XSTC) sections; 24 pytest tests assert text existence."
  status: NOT_PROVEN
  protection_level: prompt_advisory
  remaining_gap: no behavioral eval; no runtime hook
  next_action: add Stop-tier XSTC emission check OR re-label as prompt_advisory
```

**Example B — partial "no new commands."**

Claim: "No new top-level commands created."

```yaml
- claim: No new top-level commands created
  claim_type: command_surface_changed
  authority_required: structural triggers diff OR claude plugin list before/after
  evidence_provided: "test_no_new_top_level_command_added forbids 4 tokens (/wiki-ingest, /transcript-mine, /debrief-miner, /mine-transcripts); the test passed."
  status: PARTIAL
  protection_level: static_invariant_tested
  remaining_gap: token-regex misses new commands with new tokens; no structural triggers diff; no claude plugin list snapshot
  next_action: replace the 4-token regex with a structural triggers-diff test + run claude plugin list before/after
```

**Example C — unproven "zero drift."**

Claim: "Zero drift confirmed."

```yaml
- claim: Zero drift confirmed
  claim_type: drift_checked
  authority_required: literal "Zero drift confirmed" line in plugin-audit-and-fix.py output
  evidence_provided: "bump output tail line: 'Run /reload-plugins to activate cc-skills-analysis 1.0.84.'"
  status: NOT_PROVEN
  protection_level: documentation_only
  remaining_gap: only the === Done === line shown, not the explicit Zero drift line
  next_action: capture the full plugin-audit-and-fix.py --bump stdout (not just the tail) and quote the literal line
```

**Example D — unproven "capability preserved."**

Claim: "Capability absorbed into /debrief."

```yaml
- claim: /retro capability absorbed into /debrief
  claim_type: capability_preserved
  authority_required: old source + parent source + backend existence + behavior evidence
  evidence_provided: "old source: skills/retro/SKILL.md:1-15; parent source: debrief/SKILL.md:198 (mentions absorption); backend existence: ???"
  status: NOT_PROVEN
  protection_level: prompt_advisory
  remaining_gap: no behavior evidence; no proof the runner/engine exists in /debrief that actually serves /retro's former use case
  next_action: run /retro through /debrief once with a representative transcript; if runner unbuilt, mark DEFERRED + create task
```

## Where to emit

| Retained command | Emit position | Status |
|---|---|---|
| `/red-team` | **Mandatory** when reviewing implementation reports, plugin changes, skill changes, hook changes, or any "done" claim | The contract is a CRITERION — `/red-team` BLOCKs reports that lack a ledger or that mis-classify protection levels. |
| `/skill-audit` | When reviewing skill/command consolidation, capability preservation, aliases, stubs, absorbed commands, and skill docs | Mandatory for `capability_preserved` rows. |
| `/claude-audit` | When reviewing plugin activation, hook/runtime/config changes, cache rebuilds, mechanism manifests, command-surface claims | Mandatory for `plugin_bumped`, `cache_rebuilt`, `drift_checked`, `command_surface_changed` rows. |
| `/review` | For code/test/diff completion claims | Mandatory for `file_changed`, `test_passed` rows. |
| `/ship` | For deploy-readiness and runtime-snapshot completion claims — pre/post/status verification that the deploy surface is live. | Mandatory for `plugin_bumped`, `cache_rebuilt`, `drift_checked`, `runtime_behavior_changed`, `user_visible_behavior_verified` rows. |
| `/improve` | Do NOT own enforcement of this contract. Add a routing note: when the issue is unsupported completion claims, suggest `/red-team` (if the report is the artifact), `/skill-audit` (if it's about skill consolidation), `/claude-audit` (if it's about hooks/config/plugins), or `/review` (if it's about code/diff). | Routing-only. |
| `/debrief` | Use the contract as the **after-action** rubric for transcript-mined bad-LLM-behavior findings. Each discovered overclaim gets classified as one of: `overclaimed_completion`, `fake_verification`, `static_test_runtime_confusion`, `user_surface_verification_gap`. | Internal rubric, not new mode. |

### Note on the `/ship` claim-type set (honest gap)

`/ship`'s deploy-readiness work conceptually wants a claim type called
`activation_verified` (the slash command is live and reachable end-to-end after
a deploy). **That enum value does not exist.** The closest existing authority is
`user_visible_behavior_verified` ("slash command → orchestrator → output driven
end-to-end"), which is what `/ship` must use. If a future deploy surface needs
to distinguish "command present" from "command driven to output," add
`activation_verified` as a 17th enum value rather than overloading
`user_visible_behavior_verified`.

## Why this exists

The pattern the contract breaks: **LLMs hide unresolved items under ✅ headers.** Risk: a future session reads the report and trusts the ✅ block, skipping the unresolved items in the "Risks" section. The ledger forces every claim onto its own row with its own authority, so a reader cannot bundle "✅" into "all done" without reading the `status` values. If three rows are `NOT_PROVEN`, the verdict is REVISE — not PROCEED.

The contract is the **classification** analog of the affordance routing rule. Affordance routing says "pick the command by what it can actually do." Completion evidence says "prove the claim by what can actually prove it." Both forbid citing the wrong authority.