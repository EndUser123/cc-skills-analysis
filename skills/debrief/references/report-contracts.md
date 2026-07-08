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
| **Deeper Abstraction Check** | inside `/ask/SKILL.md` (`## Deeper Abstraction Check`) | `/ask` (owns) | Local concept → reusable class / ownership map → disposition | **Prompt-advisory.** A static test pins the canonical fields + 6 disposition enum values; no runtime gate. |
| **Coverage Authority** | inside `/ask/SKILL.md` (`### Coverage Authority`) | `/ask` (owns) | Every audit/claim must name its evidence-breadth authority (sampled → live_behavior) | **Prompt-advisory.** Static test asserts the five values + the "no bare full coverage" rule; no runtime gate. |
| **Activation Truth Model** | inside `/ask/SKILL.md` (`### Activation Truth Model`) | `/ask` (owns) | Every "live / active / shipped" claim names which of 5 layers is actually proven | **Prompt-advisory.** Static test asserts the five layers + the source-only-overclaim prohibition; no runtime gate. |
| **Bounded Action Continuation** | inside `/ask/SKILL.md` (`### Bounded Action Continuation`) | `/ask` (owns) | Decide whether to complete a small reversible action or stop to re-ask, using 4 conditions | **Prompt-advisory.** Discipline rule, not a gate. |

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

## Feedback Loop / Harness Calibration Addendum

This addendum names the **feedback mechanisms** that keep the report-contract
discipline calibrated to reality. It is not a new contract and adds **no
commands, no `/wiki` write, and no BLOCK-level gate.** Each mechanism is filed
at its honest runtime status — none of the seven is a BLOCK gate today.

| Mechanism | Canonical artifact | Rule / schema | Runtime status |
|---|---|---|---|
| **Runtime Ground Truth Freshness** | `P:/.claude/hooks/analysis/runtime-ground-truth.md` (schema table) + SessionStart injection block | Each fact carries `fact` / `source` / `verification_command` / `last_verified` / `expiry_trigger`; a stale row renders `[STALE — reverify: <cmd>]` instead of silently dropping | `runtime_surface`, **advisory** — injection fires at SessionStart; no block on stale facts |
| **Public Baseline Taxonomy + Local Diff** | `completion-evidence-contract.md:114-121` (`protection_level` enum) + the ledger row | Every local claim is diffed against the 6-value taxonomy (`documentation_only` → `runtime_enforced_and_regression_tested`); a claim landing below its required level becomes an overclaim row | `prompt_advisory` — enforced only at `/red-team` / `/review`; no live gate |
| **Two-Layer Gold Corpus** | `P:/.data/evals/gold/` + `replay_eval.py` (replay layer); `shadow_eval.py` + `shadow_hits.jsonl` (shadow layer) | Layer 1: deterministic regression replay against gold fixtures. Layer 2: live SHADOW detection writing non-blocking telemetry | replay `behavior_eval_tested` (real fixtures through real detectors, when run); shadow `runtime_surface`, advisory |
| **Disallowed Conclusions** | `completion-evidence-contract.md:123-134` (Rules 1–10) + `cc-skills-architect/skills/ask/SKILL.md:432-435,451-455` ("Prohibited:" lines) | Forbidden verdicts: "full coverage" without an authority, "live" from a source edit alone, "done" without a ledger row, "zero drift" without the literal, "shipped" from a cache rebuild alone | `prompt_advisory` — except `Stop_fake_done_detector.py` enforces the **ledger-presence** requirement at **WARN** (not BLOCK) |
| **Epistemic Hook Calibration Before Blocking** | `completion-evidence-contract.md:59-62` ("Promotion to BLOCK" paragraph) + the gate-discrimination discipline | A behavioral gate must measure TP/FP on a real corpus (≥3 non-discrimination cases) before promotion from WARN to BLOCK; the close-the-loop ladder ships WARN first, BLOCK only after corpus signal (earliest ~2026-07-21) | `documentation_only` — pre-ship discipline; nothing at runtime enforces the discipline itself |
| **Local JSONL Verification Packets** | `P:/.claude/hooks/analysis/phase_0_5_*`, `phase_1_*`, `phase_1_5_*`, `phase_2_*`, `phase_3_*_evidence_packet_*.md`; plus `P:/.data/evals/misses.jsonl`, `shadow_hits.jsonl` | Per-phase markdown packets cite the JSONL streams they summarize; each carries its own status (DONE / SHADOW / RETIRED) and re-calibration numbers | `documentation_only` — packets are hand-authored post-hoc; the JSONL they cite is runtime-generated |
| **Deterministic-First / LLM-Last** | `cc-skills-architect/skills/ask/lib/abstraction_audit_manifest.py` + `cc-skills-architect/skills/ask/SKILL.md:349-372` | Deterministic whole-repo enumeration (file inventory + term search + risk heuristics) runs first; the LLM inspects only the ranked recommended-read set last, and must say so before claiming `whole_repo_static` | `prompt_advisory` (the instruction) + `runtime_surface` (the script, when invoked) |

**Coverage authority for this addendum:** `targeted` — each cited path was read
or `ls`-verified during authoring; non-cited surfaces were not enumerated. This
is not `whole_repo_static`.

**Falsification:** This addendum is wrong if (a) any mechanism is filed at a
stronger runtime status than it actually has, (b) a cited artifact no longer
exists at the named path, or (c) a future BLOCK-level gate is wired without the
corpus measurement the calibration rule requires.
