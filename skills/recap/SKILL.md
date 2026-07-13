---
name: recap
description: Generate a handoff-ready session recap across the full session chain, with an optional evidence-scoped pre-handoff check
version: 1.0.43
status: stable
category: session
contract_type: hybrid
enforcement: strict
triggers:
  - /recap
required_artifacts:
  - session_chain_output
response_requirements:
  - handoff document with Context/Completed/In Progress/Blocked/Next Actions/Risks sections
  - per-session narrative with origin tags (full mode only)
  - structured synthesis fields
  - routing suggestions
workflow_steps:
  - id: resolve_terminal_and_session
    first_tool: Bash
  - id: walk_session_chain
    first_tool: Bash
  - id: parse_transcripts
    first_tool: Read
  - id: aggregate_context
  - id: synthesize_findings
  - id: present_summary
    first_tool: Write
execution:
  directive: Run the recap CLI script to parse transcript files and extract session history, then synthesize findings
  default_args: ""
  examples:
    - "/recap"
    - "/recap check"
    - "/recap brief"
---

# /recap — Terminal-Wide Session Catch-Up

**Problem solved:** "I have 10 sessions compaction-deep in this terminal and I need to know what happened."

## Core Concept

`/recap` aggregates context from ALL sessions in this terminal by walking the full session chain (handoff files + mtime-gap fallback) and parsing each transcript. Session boundaries within each transcript are detected via `sessionId` changes.

`/recap` uses `session_chain.walk_session_chain()` to walk the full session chain via handoff files, then parses each transcript in oldest-to-newest order.

**LLM Executor: ALWAYS walk the chain via `session_chain.walk_session_chain()`. Never skip the transcript walk.** Do not assume "I have full conversation context in memory" — post-compaction, in-memory context is a lossy subset of the transcript and feels complete while missing items. The transcript at `transcript_path` is the only authoritative source. (This clause replaces an earlier "skip if you have context" shortcut that caused recaps to silently omit work dropped by compaction.)

1. **Get current session ID (MANDATORY — derive explicitly, never auto-detect).** Do NOT rely on any "current session" file or terminal-keyed auto-detection. Under concurrent Claude sessions in one Windows Terminal, `WT_SESSION` is shared, `~/.claude/active-session-{terminal_id}.txt` and `~/.claude/.artifacts/{terminal_id}/identity.json` are last-writer-wins, and mtime/size fallbacks resolve to a sibling session. Wrong session_id → wrong chain walked → silent miss (same failure class as the post-compaction skip trap). Derive it directly:
   - **Preferred:** from the live `transcript_path` in your most recent hook payload — `C:\Users\<user>\.claude\projects\P--\<session_id>.jsonl` (or `<session_id>-<model>.jsonl`). The stem minus the optional `-<model>` suffix is the session_id.
   - **First prompt of a session (no hook payload yet):** run `/status` or inspect `~/.claude/projects/P--/` for the `.jsonl` whose mtime is newest and whose content includes your current first message. Do NOT guess from memory or from the active-session file.
   - Pass the derived id as the sole key into `walk_session_chain()` in Step 2.
2. **Walk the session chain**: Call `session_chain.walk_session_chain(session_id)` — Strategy 1 uses handoff files (`n_1_transcript_path`), Strategy 2 uses mtime-gap + semantic fallback
3. **Parse each transcript**: Load each transcript path, detect session boundaries via `sessionId` changes, extract goals/message counts
4. **Aggregate context**: Extract goals, message counts from each session
5. **Present summary**: Shows chronological session history

> **`session_chain` module**: `P:/packages/.claude-marketplace/plugins/search-research/core/session_chain.py` — exports `walk_session_chain()` (unified entry), `walk_handoff_chain()` (Strategy 1), `walk_sessions_index_chain()` (Strategy 2). All synchronous.

> **Always parse the transcript.** Even when compaction context is available, the transcript contains the authoritative full session chain and detailed working state. Compaction summaries are lossy — they capture goals and outcomes but not the exact sequence of working decisions, errors encountered, or file states mid-edit.

> **⚠️ Fallback behavior**: If `session_chain` import fails, fall back to reading only the current terminal's transcript file directly — it cannot reconstruct the full multi-session terminal history. The synthesis step will have less context to work with.

## Output Structure

The script extracts structured data via regex and presents it in a format compatible with handoff best practices.

### Script Output (aligned with `/handoff` template)
```
# Terminal Recap: {terminal_id}

## Session Metadata
- **Total Sessions**: {count}
- **Terminal ID**: {terminal_id}
- **Current Session**: {session_id}
- **Project**: {project_path}

## Session History

[Session 1] {session_id}
- **User messages**: {n} / Assistant messages: {n}
- **Duration**: {duration if available}

### Modified Files
- `{file_path}`
- `{file_path}`

### Original Request
- **User Request**: "{extracted request}"
- **Trigger**: {trigger context}

### Session Objectives
- **Objective 1**: {objective} ({status})
- **Objective 2**: {objective} ({status})

### Final Actions Taken
- **Action A** ({priority})
- **Action B** ({priority})

### Outcomes
- **Outcome 1**: ({status})
- **Outcome 2**: ({status})

### Active Work At Handoff
- **Currently Working On**: {work description}
  - **Current Status**: {status}
  - Files Modified: {file_list}
  - Next: {next_step}

### Working Decisions (Critical for Continuity)
- **Decision**: {decision}
  - **Rationale**: {reason}
  - **Impact**: {high|medium|low}

### Current Tasks
- **#{id}**: {task description} ({status}, {priority})

### Known Issues
- **ISSUE-1**: {description} ({status}, {priority})

### Open Questions / Parking Lot
- **Question**: {question text}? ({priority}, {type})
  - *Urgency*: High/Med/Low — what would need to be true to decide this?

### Knowledge Contributions
- **Insight**: {contribution}

### Next Immediate Action
1. {action_1}
2. {action_2}

### Parking Lot (Inversion)
*What would guarantee this session's work fails?* Surface it here.
- **Failure Mode**: {description} — *Mitigation*: {what would prevent it}
- **Assumption**: {core assumption} — *Invalidates*: D# or Action#
- **External Block**: {dependency} — *Blocks*: Action#

### Recommended Next Steps

Use `render_actions()` from `recap/__lib/render_rns.py` (local copy) to render actionable next steps in human-readable RNS format. The original RNS Python backend was removed when `/rns` became a pure-LLM skill; `__lib/render_rns.py` preserves the renderer locally.

```python
import sys
from pathlib import Path
_lib = str(Path(__file__).resolve().parent / "__lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from render_rns import render_actions, RenderOptions

actions = [
    {"id": "1a", "domain": "recap", "priority": "medium", "description": "...", "file_ref": "file.py:line", "effort": "~5min"},
]
print(render_actions(actions, RenderOptions(show_effort=True, show_file_ref=True)))
```

Rendered output format (via `render_actions`):

```
1 🔄 RECAP (2)
  1a 🟡 [E:~5min] Resume pending snapshot unit tests @ test_phase2_scan.py
  1b 🔵 Check handoff chain integrity for recent sessions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

0 — Do ALL Recommended Next Actions (2 items)
```

When no actionables found (brief mode, no session chain), skip the RNS section entirely — do not emit `RNS|Z|0|NONE` to the user.

### Raw Context
{condensed text for full transcript access}
```
> **⚠️ Note:** The `### Raw Context` section is condensed by `_condense_transcript()` with a 2000-character budget per session. When `### Modified Files` is present, AID distillation replaces Raw Context with AST-level code structure. Content beyond that limit is silently dropped — the structured fields above are the primary evidence source. Full transcript access requires reading the raw transcript file directly.


### Project Context Backdrop

Before synthesizing session narratives, establish project context.

Call `mcp__aid__distill_directory` on the project root with `recursive=false`, `include_implementation=false`. Present the result as a collapsible `## Project Context` section at the top of synthesis. Skip this step for `/recap brief` mode or if the AID MCP tool is unavailable.

### Response Synthesis (LLM task after script output)

When responding to `/recap`, apply reasoning to the script output plus the raw transcript context. For each session, synthesize:

**What happened**: Numbered list of issues. Each item starts with an origin tag and a confidence tag, then describes the issue.

Origin tags:
- `[user-reported]` — user explicitly raised this
- `[discovered-during-fix]` — surfaced while working on something else
- `[hook-failure]` — a hook caught or blocked something
- `[skill-escalated]` — a skill routed here from another skill
- `[regression]` — something that worked before broke

Confidence tags:
- `[FACT]` — grounded in tool output, file content, or command results visible in the transcript
- `[INFERENCE]` — plausible but not directly proven by transcript evidence; state what evidence would confirm or deny
- `[UNKNOWN]` — important question that cannot be answered from visible evidence

Example: `[user-reported] [FACT] Path refactoring broke imports — sync.py raised ModuleNotFoundError at line 42`

**What was done**: What actually changed (file edits, hooks, skills, configs). Be specific about the actual action.

**In hindsight**: Was the approach right, given what we know now? Only include this section when the fix was a workaround, a detour was taken, or something was missed. Skip it when the fix was straightforward and correct.

**Still pending**: Concrete next steps that were identified but not completed. Each item must be actionable — a command to run, a file to check, or a decision to make. If nothing is pending, omit this section entirely.

**Assumptions to verify**: For each assumption the synthesis relies on, suggest one concrete check — a command to run, a file to inspect, or a question to ask. Each item states the assumption and the check that would confirm or falsify it. If no assumptions are uncertain, omit this section entirely.

Example: "Assumption: sync.py import fix works for all package repos. Check: run `python P://.claude/skills/git/sync.py --health` and verify no ImportError."

Present synthesis as a per-session narrative in the response, not replacing the script output but complementing it.

### Code Structure Enrichment

For sessions with `### Modified Files`, call `mcp__aid__distill_file` on up to 5 files with `include_implementation=false`. The distilled output (function signatures, class hierarchy) serves dual purpose:

1. **Replaces regex-extracted “actions”** with actual function/class changes in synthesis
2. **Replaces `### Raw Context`** with AST-level structure instead of the 2000-char condensed transcript

Regex extraction remains as fallback for sessions without identifiable file changes. Sessions without Modified Files keep the `### Raw Context` fallback.

## Usage

```bash
/recap                    # Generate handoff document (default mode)
/recap brief              # Show brief catch-up summary only
/recap full               # Show full detailed session history
/recap check              # Run the recap-owned pre-handoff check
/recap check --tier core --size large --kind refactor  # Include explicit risk score
```

## Default Output: Handoff Document

When invoked without arguments, `/recap` produces a **handoff document** suitable for another LLM, PM, or developer picking up where the session left off. This is the default behavior — no flags needed.

### Handoff Template

```markdown
# Session Recap

## Resume Here
- **Status**: {complete | partial | blocked}
- **Outcome**: {one-sentence summary of what landed and what state the system is in now}
- **Immediate next action**: {one concrete command, file edit, or "none — session is closed"}
- **Do not**: {1–3 hard constraints the next agent must respect, e.g. "do not read the 495K-token export into main context"}
- **Handoff confidence**: {high | medium | low — anchored to GATE 1/2 signals below in "Evidence Appendix"}

## Completed
- **Change**:
- **Verification**:
- **Commits**:

## Remaining Work
### Urgent
- {only items requiring action before the next session can proceed}
### Blocked
- {external blockers; internal uncertainty belongs in Risks}
### Optional
- {deferred follow-ups clearly labeled non-urgent}

## Risks and Constraints
- {assumptions, failure modes, unsafe paths, hook false positives, stale tracker rows}
- {if nothing material, write "None material." rather than omit}

## Decisions
- {only decisions that constrain future work, each with its reversal trigger}

## Artifacts
- {files written/edited, exports, transcripts, evidence-store entries}
- {max 10; if exceeded, list the most-recent 10 and link to the rest in the appendix}

## Evidence Appendix
- **Friction**: {observed tool/hook/skill frictions that constrained this session}
- **Hypotheses**: {behave-style hypotheses surfaced but not confirmed}
- **Weakest assumption challenge**: {one assumption you'd be most confident about that you HAVEN'T verified}
- **Inversion prompt**: failure modes and their mitigations
- **Catch-up integrity prompts** (internal self-check): see SKILL.md "Catch-Up Integrity Prompts" — expand here as needed for the worst 2–3
- **Multi-terminal context** (only when chain spans terminals): {terminal-by-terminal summary}

## Next Session Checklist
- [ ] {concrete, deduplicated next action 1}
- [ ] {concrete next action 2}
```

The handoff format replaces the per-session narrative as the **default output**. Use `/recap full` for the detailed session-by-session view with origin tags and confidence labels. Use `/recap brief` for a quick one-paragraph catch-up — `brief` mode is **exempt from this template** and stays one section.

### Pre-Handoff Check (`/recap check`)

`/recap check` is the recap-owned successor to the retired `/dne` surface. It
keeps the useful DUF/NSE behavior at the handoff boundary:

1. **Evidence scope** — report the sessions and modified files actually loaded.
2. **Priority (Red)** — surface recorded blockers, unresolved tasks, and missing
   verified outcomes. Absence of a recorded blocker is not proof of safety.
3. **Maintenance (Yellow)** — prompt blast-radius, rollback, empty/null/zero,
   and inversion checks.
4. **Suggestions (Blue)** — list optional follow-up work, including `/debrief`
   when a recurring failure or durable lesson needs transcript forensics.

The check is advisory and does not infer commit/push state or implement fixes.
The objective tier × size × kind score is calculated only when all three inputs
are explicitly supplied; otherwise the output says that risk is uncalculated.
This keeps the score from becoming a false precision proxy for session safety.

### Handoff Synthesis Rules

1. **Resume Here** is the only section a future agent must read to keep moving. Status is one word; outcome is one sentence; immediate next action is one concrete step. Resist the urge to over-explain.
2. **Completed**: only items with VERIFIED evidence (tests passing, files written, commands succeeded). Infer nothing — if completion is uncertain, put it in Remaining Work → Urgent or Optional.
3. **Remaining Work → Urgent**: blocks the next session from proceeding. Use it sparingly; most sessions end with "none urgent."
4. **Remaining Work → Blocked**: external blockers only (missing API access, unanswered questions, upstream dependencies). Internal uncertainty goes in Risks.
5. **Remaining Work → Optional**: clearly labeled non-urgent. Do not pretend "nothing urgent" means "nothing pending."
6. **Risks and Constraints**: surface assumptions, failure modes, hook false positives, and inversion mitigations. If the handoff consumer does nothing else, they should read this section.
7. **Decisions**: architectural or design decisions that constrain future work. Each must include a reversal trigger. Drop trivial decisions.
8. **Artifacts**: files written/edited, exports, transcripts, evidence-store entries. Limit to 10; if exceeded, list the most-recent 10 and link to the rest.
9. **Evidence Appendix**: friction, hypotheses, assumption challenge, inversion prompt, and catch-up integrity prompts — supporting detail for the resume-oriented sections above, NOT a substitute for them. Keep the catch-up integrity prompts condensed to the worst 2–3 issues; expand them only when a specific integrity question matters.
10. **Next Session Checklist**: deduplicated, concrete. Each item must be a command, file edit, or decision, not a vague suggestion. If the session is closed and the next agent must simply pick a follow-up issue, the checklist can be one item: "Pick from #1296 / #1282 / #1283."

### Multi-Terminal Context

When session data spans multiple terminals (discovered via session registry or handoff chain), include a `## Multi-Terminal Context` section:

```markdown
## Multi-Terminal Context
- **Terminal A** ({id}): {summary of work}
- **Terminal B** ({id}): {summary of work}
- **Cross-terminal dependencies**: {what depends on what}
```

This section is omitted when all sessions belong to the same terminal.

## Routing Behavior

`/recap` uses intent detection to suggest follow-up commands. Map session patterns to the most relevant skill (max 3 suggestions per recap):

| Intent Detected | Follow-Up Command | When to Suggest |
|----------------|-------------------|-----------------|
| Navigation / lost context | `/debrief gaps` | Current gaps or stale assumptions are unclear |
| Architecture decisions | `/design` | Unresolved state or contract decisions in prior sessions |
| Complexity hotspots | `/tldr-deep` then `/refactor` | Sessions with many modified files or complex changes |
| Debugging / root cause | `/diagnose` or `/rca` | Sessions with unresolved bugs or error patterns |
| Impact verification | `/verify` | Work discussed or implemented but not actually proven |
| Data flow tracing | `/trace` | Sessions touching data pipelines or state management |

`/pre-mortem` remains the escalation path for sessions with unresolved risk or emergent behavior.

`/recap` should not implement fixes itself.

## Catch-Up Integrity Prompts

These prompts are the **source-of-truth rubric** the Evidence Appendix in the Handoff Template draws from. `/recap` runs them as an internal self-check before authoring the handoff; the worst 2–3 failures land in the Evidence Appendix `Catch-up integrity prompts (internal self-check)` subsection. Do NOT fan them out into the user-facing handoff at full length — that is exactly the audit-buried-in-prose failure the new template fixes.

Before synthesizing a catch-up summary, `/recap` should run a short internal catch-up integrity check:

- What part of this recap is being inferred from condensed transcript fragments rather than strong evidence?
- What session outcome might be stale, incomplete, or contradicted by later sessions in the same terminal chain?
- What assumption, contract gap, or resume risk is still implicit rather than explicitly surfaced?
- What event in the session chain changed the direction of work, and have I preserved that turning point accurately?
- What recommendation would be misleading if the transcript fallback lost important context?
- What issue was discussed but never actually verified or completed?
- What would a weaker model compress away that materially changes the summary?
- What gap belongs to `/design`, `/planning`, or `/verify` rather than being presented as a local recap observation?
- What summary statement is too confident given the available transcript evidence?
- What would make this recap locally coherent but globally wrong across the full session chain?
- **Weakest assumption challenge**: Which single assumption about this session chain am I MOST confident about that I HAVEN'T verified? What would happen if it is wrong? What's the smallest check that would falsify it?
- **Inversion prompting**: What would guarantee this session's work fails? Surface it here.
  - **Failure Mode**: {description} — *Mitigation*: {what would prevent it}
  - **Assumption**: {core assumption} — *Invalidates*: D# or Action#
  - **External Block**: {dependency} — *Blocks*: Action#

These are internal self-check prompts. They are not default user-facing questions and should only surface to the user when `/recap` is genuinely blocked and cannot proceed safely without clarification.

## Phase Gates

**GATE 1 (STOP after session_chain.walk_session_chain)**: Before moving to synthesis, verify:
- Session chain walked successfully (or fallback used)
- Session boundaries detected via sessionId changes
- All sessions in chain processed
- **The recap cites session IDs returned by `walk_session_chain()` — NOT inferred from in-memory conversation context.** This is the anti-compaction invariant: synthesis grounded in in-memory context alone silently omits items the summarizer dropped. If you cannot point to a session ID from the walk, you skipped the walk; go back and run it.

If gate fails: note chain walk issue and proceed with available data.

**GATE 2 (STOP before Response Synthesis)**: Before LLM synthesis, verify:
- Script output complete with all structured fields
- Raw Context present (or AID distillation applied)
- Project Context loaded (unless /recap brief mode)

If gate fails: note missing sections and proceed with available data.

**STOP between generation (Steps 1-4) and validation (Steps 5+)**:
- Steps 1-4: Walk chain, parse transcripts, extract goals/message counts, aggregate (generation)
- Step 5+: Response synthesis, integrity prompts, routing (validation)
- Do NOT proceed to synthesis until session chain is fully walked

---

## Implementation Notes

- **Session chain walking**: Uses `session_chain.walk_session_chain()` which first tries handoff-file chain (Strategy 1: `n_1_transcript_path` → prior handoff → ...), then mtime-gap + semantic fallback (Strategy 2)
- Fallback order: handoff files → sessions-index scan → semantic similarity → current transcript only
- Detects session boundaries via `sessionId` field changes within each transcript
- `sessionId` is the stem of the transcript filename (e.g., `8a7b83ff-7d98-47e9-b3b5-3ffabc978c40.jsonl`)
- Semantic extraction (problem/fix/action) via regex against structured output patterns (bugfixes.md format)
- Synthesis (optimal fix reasoning) is performed by the responding LLM — not in preprocessing

## Evidence-First Principles

### E1 — Evidence before claims
Before claiming code is absent, unchanged, or non-existent — search the codebase and verify with tools first. Claims of absence are only valid after confirmed Read/Grep/git failures.

### E4 — Investigate before asking
Do NOT answer without reading relevant source files first. Do not ask the user for information you can obtain yourself via Read, Grep, Bash, git, or available MCP tools.

### E5 — Anti-lazy escape hatch
Prohibited:
- "I assume", "I think", "probably" without tool verification
- Claiming something doesn't exist without confirmed tool failure
- Skipping evidence gathering because the answer seems obvious
