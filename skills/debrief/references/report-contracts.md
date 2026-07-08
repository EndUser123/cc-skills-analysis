# Report Contracts (meta-reference)

This is a **meta-reference**: it names a recurring abstraction so future work
chooses it deliberately instead of re-inventing it. It owns no behavior and
enforces nothing at runtime. Every contract it points at is **prompt-advisory
unless a runtime hook or behavior-eval test says otherwise** — read each
contract's own "protection_level" / advisory-status line for the truth.

## The pattern

A **report contract** is a canonical reference that defines a structured output
shape (typed fields, an enum, a classification), plus a short pointer section in
each command that must emit it. Four elements, all required:

1. **Canonical reference** — one file owns the definition (fields, enum, rules,
   worked examples, falsification condition).
2. **Per-command pointer** — each command that must emit the shape carries a
   short section that names the canonical file, restates only the trigger
   condition and the advisory status, and **does not** duplicate the fields.
3. **Advisory status stated plainly** — the canonical file and every pointer
   say whether the contract is prompt-advisory, static-invariant-tested, or
   runtime-enforced. No silent implication that a text-test is a runtime gate.
4. **Static invariant test** — a pytest test asserts the canonical file exists,
   the pointer sections exist where claimed, and the forbidden shapes (new
   command, silent wiki write, displaced verdict) did not appear.

## When to use this pattern instead of duplicating prose

Use the report-contract pattern when **all** are true:

- The same structured output (a ledger, a posture, a classification) must be
  emitted by more than one command.
- The shape has a fixed vocabulary (enum / required fields) that drifts if each
  command re-states it.
- A reader must be able to tell, from the contract alone, whether a given
  command's output is compliant.

Do **not** use it when:

- Only one command emits the shape — put it in that command's own reference.
- The shape is operational prose (a how-to, a diagram, a prompt template), not
  a compliance vocabulary — a normal reference file is enough.
- You want runtime enforcement — a contract is the wrong instrument; write a
  hook or a behavior-eval test and let the contract point at it.

The anti-pattern this replaces: pasting the same field list into seven command
docs, watching them drift, then adding a test that checks seven copies of the
same string. One canonical file + seven one-line pointers + one test is
strictly less code and strictly less drift.

## Registry of existing report contracts

| Contract | Canonical file | Owning command | What it classifies | Runtime status |
|---|---|---|---|---|
| **Completion Evidence Contract (CEC)** | `completion-evidence-contract.md` | `/red-team` (criterion), `/review`, `/skill-audit`, `/claude-audit`, `/ship` | Completion claims → typed `claim_type` + `protection_level` + status | **Prompt-advisory.** No Stop-tier ledger-enforcement hook ships yet (see `#1241`). A static test asserts the doc + pointer invariants. |
| **Thought Partner Addendum (TPA)** | `thought-partner-addendum.md` | `/improve` (canonical owner) | Material thought-partner observations (when to raise priority/risk/sequencing, not generic caveats) | **Prompt-advisory.** No runtime gate. Static test asserts the canonical owner + 7 pointer sections. |
| **Partner Posture Map** | section inside `thought-partner-addendum.md` | `/improve` (canonical) | Each retained command's collaborative posture (Improvement Partner, Adversarial Trust Partner, etc.) | **Prompt-advisory.** Section of the TPA, same status. Static test asserts the 8 command postures + 8 pointer sections. |
| **Cross-Skill Transfer Check (XSTC)** | `cross-skill-transfer-check.md` | `/debrief` (drives), every retained command emits | Whether a failure/fix class is local or reusable across skills/hooks/gates | **Prompt-advisory.** No runtime gate. Static test asserts the required fields + pointer invariants. |
| **Discoverability Classification** | `discoverability-classification.md` | every command that might ask the user for a fact | Missing facts → `DISCOVERABLE` (run the tool) vs `USER_ONLY` (ask) | **Prompt-advisory.** Discipline rule, not a gate. |
| **Routing by Affordances** | `routing-by-affordances.md` | `/debrief` (drives), referenced by XSTC | Work → affordance → command, forbidding circular self-positioning | **Prompt-advisory.** Referenced by the XSTC rule; no runtime gate. |

Adjacent files in `references/` that are **not** report contracts (they do not
follow the canonical + per-command-pointer shape): `bad-behavior-rubric.md`
(an internal classification rubric for `/debrief` mining, single-command),
`handoff-routing.md`, `task_writing_guide.md`, `extraction_prompt.md`,
`loop-diagram.md`. Listed here so a reader does not mistake them for contracts.

## Advisory vs enforced — the rule that keeps this honest

A report contract is a **vocabulary for the model to use when writing a
report.** It is not, by itself, enforcement. Conflating the two is the exact
overclaim the CEC exists to catch (`protection_level: runtime_enforced` claimed
for a doc edit is NOT_PROVEN).

The separation:

- **prompt_advisory / documentation_only** — the contract lives in docs and
  test-asserts its own shape. Nothing forces a live run to emit the shape.
- **static_invariant_tested** — a pytest test asserts the canonical file + the
  pointer sections + the forbidden-shape absence. This proves the contract
  *exists and is wired*, not that any live run *followed* it.
- **runtime_enforced / behavior_eval_tested** — only when a hook fires in the
  live dispatch path or a behavior eval fails when the shape is absent. **None
  of the six contracts above are at this level today.** If you wire one, say so
  in that contract's own status line and cite the hook file:line.

If a contract's status line ever claims `runtime_enforced` without a matching
hook, that is a BLOCK-class overclaim — the same shape the CEC Rule 2 forbids.

## Adding a new report contract

1. Write the canonical reference under `debrief/references/<name>.md` with:
   required fields, enum (if any), rules, a worked example, a negative example,
   and a falsification condition. State the runtime status honestly.
2. Add a short pointer section to each command that must emit it. The pointer
   names the canonical file, restates the trigger + advisory status, and does
   **not** duplicate the fields.
3. Add a static invariant test that asserts: canonical file exists, pointers
   exist in the named commands, no new top-level command was created, no silent
   `/wiki` write was introduced.
4. Add a row to the registry table above.
5. If (and only if) you also wire a runtime hook, update the contract's status
   line to `runtime_enforced` and cite the hook. A test-asserts-text contract
   stays `prompt_advisory` / `static_invariant_tested`.

## Falsification

This meta-reference is wrong if any of the following hold:

- A contract listed as "prompt-advisory" is actually wired to a live runtime
  hook nobody documented here (the registry understates enforcement).
- A command carries a pointer section to a contract that does not exist, or a
  contract exists with zero pointer sections pointing at it (dead contract or
  dead pointer).
- A new structured output shape that *should* be a report contract (multi
  command, fixed vocabulary, compliance-checkable) is instead duplicated as
  prose across command docs — the pattern was available and not chosen.
- A contract's status line claims `runtime_enforced` without a matching hook
  file:line (the central overclaim this reference exists to prevent).
