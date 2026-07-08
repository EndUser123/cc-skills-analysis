# Report-Contract Vocabularies (cross-command field reference)

This is a **cross-command reference** for the fields and values that report
contracts require every retained command to emit when its primary job produces
a "done / fixed / verified / live / shipped / audited / classified" claim.
The full registry lives in `report-contracts.md`; this file is the field-level
cheat-sheet each command's pointer section can cite without restating.

**Advisory status:** every vocabulary here is `prompt_advisory` unless a
runtime hook explicitly says otherwise. Static-invariant-tested at most. The
register in `report-contracts.md` is the source of truth for which contracts
are at which protection level.

## Coverage Authority (canonical owner: `/ask`)

Any audit/claim that names its evidence breadth must pick one of:

| Value | Means |
|---|---|
| `sampled` | A subset of the named surface was inspected; results may not generalize. |
| `targeted` | Named surfaces (specific files / skills / hooks) were grep'd or read; non-named surfaces were not. |
| `whole_repo_static` | The marketplace tree was enumerated (Glob) and every named file was inspected. |
| `runtime_surface` | A live process or hook dispatch path was exercised; behavior is observed, not inferred. |
| `live_behavior` | A real user path (slash command → orchestrator → output) was driven end-to-end and observed. |

Prohibited: "full coverage" without an authority label. Prohibited: "the
codebase" without a Glob result. Prohibited: "every skill has X" without an
enumerated check. Default for any audit that did not enumerate: `sampled`.

Canonical location: `cc-skills-architect/skills/ask/SKILL.md` (`### Coverage Authority`).

## Activation Truth Model (canonical owner: `/ask`)

Any "live / active / shipped / wired / behavior-changed" claim must identify
which layer is actually proven:

| Layer | Proves |
|---|---|
| `source_changed` | A file was edited in source. Nothing more. |
| `cache_rebuilt` | The version-keyed plugin cache was rebuilt from the new source. |
| `plugin_loaded` | The plugin is loaded into the running Claude Code session. |
| `command_resolves` | The slash command resolves to a real implementation (`claude plugin list` / dispatcher output). |
| `behavior_observed` | The user path (slash command → orchestrator → output) was driven end-to-end and the expected behavior was observed. |

Prohibited: claiming "wired" or "live" from a source edit alone. Prohibited:
claiming "shipped" from a cache rebuild without confirming plugin load. Each
layer requires its own evidence; the CEC `claim_type` enum's
`source_changed` / `plugin_bumped` / `cache_rebuilt` / `runtime_behavior_changed`
/ `user_visible_behavior_verified` rows map onto this ladder directly.

Canonical location: `cc-skills-architect/skills/ask/SKILL.md` (`### Activation Truth Model`).

## Bounded Action Continuation (canonical owner: `/ask`)

When all four of these are true, complete the bounded action directly instead
of stopping to re-ask:

1. The user has clearly authorized the goal (explicit request, not inferred).
2. The next action is bounded — one file edit, one grep, one test run, one
   small script execution, no blast radius beyond the stated scope.
3. The action is reversible or trivially correctable (git-edit, not git-reset).
4. The action is directly implied — there is no reasonable alternative path
   that would change the user's intent.

Do **not** continue when: the action is destructive (delete, drop, rm -rf),
unclear (two valid interpretations), outside stated scope, or when the user's
prior message signals they want a plan or report rather than execution.

Canonical location: `cc-skills-architect/skills/ask/SKILL.md` (`### Bounded Action Continuation`).

## Manifest generator (canonical owner: `/ask`)

Before any abstraction-opportunity audit or "the whole repo" claim, run the
deterministic manifest generator:

```bash
python cc-skills-architect/skills/ask/lib/abstraction_audit_manifest.py \
  --repo-root <marketplace-root>
```

It writes `manifest.json` + `manifest.md` with inventory counts, search hits,
risk flags, and a recommended read set. Coverage authority is
`whole_repo_static` only when this script ran from the repo root; otherwise
downgrade to `sampled` or `targeted`.

Canonical location: `cc-skills-architect/skills/ask/lib/abstraction_audit_manifest.py`.

## Pointer section template (what each command adds)

Every retained command that emits a "done / fixed / verified / shipped / live"
claim should add a section like this, near the existing CEC/TPA/XSTC sections:

```markdown
## Report-Contract Vocabularies

This skill emits claims under the cross-command report contracts. The
canonical field definitions live at
`debrief/references/report-contract-vocabularies.md`:

- **Coverage Authority** — name `sampled | targeted | whole_repo_static |
  runtime_surface | live_behavior` on any audit claim (no bare "full coverage").
- **Activation Truth Model** — name one of `source_changed | cache_rebuilt |
  plugin_loaded | command_resolves | behavior_observed` on any "live / wired"
  claim. Do not claim live behavior from a source/cache evidence alone.
- **Bounded Action Continuation** — when the goal is authorized and the next
  action is bounded + reversible + directly implied, complete it directly
  instead of ending with "say the word."
- **Manifest generator** — before claiming `whole_repo_static` evidence breadth,
  run `cc-skills-architect/skills/ask/lib/abstraction_audit_manifest.py` and
  cite the produced `manifest.json`.

Advisory status: prompt-advisory. Static-invariant-tested at most. No runtime
hook enforces these fields.
```

This is the only addition required — the pointer does not duplicate the
canonical fields, per the report-contract pattern.