# Discoverability Classification — DISCOVERABLE vs USER_ONLY

**Problem.** Agents ask the user for facts they could discover through cheap
safe read-only tool use. This is a contract violation equal to inventing the
fact — both offload work the agent should do itself.

**The split.** Before asking the user for a missing fact, classify it:

## DISCOVERABLE

A read-only command, grep, file read, filesystem search, repo search, or
web/search tool can answer it.

**Action:** run the tool and report what was searched. Do NOT ask the user.

Examples:
- "Please provide the transcripts" → run `find`/`Glob` for `*.jsonl` under the project.
- "Tell me where the config is" → grep known config paths (`settings.json`, `.claude/`, plugin roots).
- "Should I run grep?" → if grep is safe, cheap, and read-only, just run it.
- "Paste the file" → if the file is in the workspace, `Read` it.
- "What line is X on?" → `Grep` for the symbol.

## USER_ONLY

Preferences, approvals, credentials, intent, private facts, destructive
permissions, budget decisions, or inaccessible systems.

**Action:** ask the user with a precise `NEED: <question>`. Do NOT guess.

Examples:
- "Approve this destructive edit?" (permission)
- "What's your API key?" (credential)
- "Which of these three approaches do you want?" (preference)
- "Is this an external system we don't control?" (inaccessible)

## The rule

> Asking the user for a DISCOVERABLE fact is a contract violation equal to
> inventing it.

Both offload work the agent should do. Both skip verification.

## Detection cue (the pushback test)

If the model asks the user for X, the user pushes back, and the model then
finds X using tools **without receiving new information** from the user,
classify it as `discoverable_fact_offloading`.

The pushback is the signal: if the model could find X after the pushback, it
could have found X before asking. The only difference is that the model
defaulted to asking instead of searching.

## What this is NOT

This rule does NOT weaken verification discipline. The good behavior —
refusing to act on unverified facts — is preserved. The split is:

- **Do** refuse to act on unverified facts (run the tool first).
- **Do NOT** ask the user for facts you could verify yourself.

A model that runs grep before asserting a line number is showing good
interrogation-before-design, NOT laziness. A model that asks the user to
paste the file it could Read is offloading.

## Ownership

| Command | Role |
|---|---|
| `/go` | **Primary owner.** Before declaring blocked, emit `missing_input` + `discoverability: DISCOVERABLE \| USER_ONLY \| UNKNOWN` + `discovery_attempted` + `evidence` + `remaining_need`. If DISCOVERABLE, run the discovery before emitting blocked. |
| `/debrief` | Add `discoverable_fact_offloading` to the bad-LLM-behavior rubric. Mine transcripts for the pushback-test pattern. |
| `/improve` | When the pattern recurs in a workflow, route to workflow/hook/skill improvement. Do NOT absorb `/debrief`. |
| `/skill-audit` | Audit skills for instructions that ask the user for files/configs/transcripts before attempting local discovery. Flag as a rubric violation. |
| `/claude-audit` | Ensure known transcript/log/config locations can be injected as runtime ground truth (so agents have fewer excuses to ask). |
| Stop hook | WARN/SHADOW detector for responses that ask the user to provide/paste/tell where X is, when no same-turn discovery evidence appears. **Advisory initially** — calibrate against transcripts before promoting to BLOCK. |

## Worked examples

**Positive example (the violation):**
User asks for Phase 1 transcript corpus. Model says "transcripts not provided,
please provide them." User pushes back. Model finds them by filesystem search.

Classification: `discoverable_fact_offloading`. The model could have run the
filesystem search on the first turn.

**Negative example (good behavior):**
Model refuses to code against unverified line numbers and runs grep/read first.

Classification: good interrogation-before-design. NOT lazy. The model verified
before asserting.

**Valid blocker (USER_ONLY):**
Model needs approval for destructive edits, credentials, or user preference.

Classification: `USER_ONLY` / `VALID_BLOCKER`. The model correctly asked
because the fact is not discoverable.