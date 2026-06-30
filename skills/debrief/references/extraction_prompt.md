# Phase 1 — Parallel Extraction Prompt

This is the exact prompt to give each `Explore` subagent when chunking a large
transcript. Copy it verbatim, substituting only the line range and the file path.
Identical wording across all chunks is what makes the outputs mergeable — do not
improvise per chunk.

## How to chunk

1. `wc -l "<file>"` to get the total line count.
2. Split into N equal ranges (4 is usually right; scale with size — aim for
   ~2000–2500 lines per chunk).
3. Dispatch all N subagents **in one message** (parallel), each with the prompt
   below and its line range. Do not wait for chunk 1 before launching chunk 2.

## The prompt

> Read lines `<START>`–`<END>` of the file `<ABSOLUTE PATH>`
> (a chat-history / session transcript). Use the Read tool with offset/limit.
>
> Your job: extract every OPEN ISSUE and OPPORTUNITY in this chunk. Definitions:
> - **OPEN ISSUE** = an unresolved problem, bug, gap, blocker, rejected-but-unfixed
>   defect, question left hanging, a "we still need to", a known limitation, a TODO,
>   or anything flagged broken/incomplete/risky.
> - **OPPORTUNITY** = an improvement, enhancement, feature idea, refactor, simplification,
>   consolidation, automation candidate, or leverage point explicitly surfaced — even
>   if not actioned.
>
> For each item capture:
> - A short title
> - Category (OPEN ISSUE vs OPPORTUNITY)
> - A 1–3 sentence description (what it is, why it matters)
> - The transcript line number(s) where it appears (approximate is fine)
> - Any named files / plugins / symbols involved
>
> Be exhaustive but precise — quote the key phrase. Skip resolved/closed items. Skip
> routine tool-call noise. Mine for issues + opportunities only; do not summarize the
> whole session. Return a clean bulleted list grouped by category. Pay special attention
> to any "remaining work" / "next steps" / "still need to" phrasing.

## After the subagents return

- Collect all chunk outputs.
- De-duplicate (the same issue often appears in two adjacent chunks).
- Group by theme, not by chunk.
- Keep every line number — those citations are the evidence that lets the next LLM
  jump straight to the source.

## When NOT to chunk

If the source fits in a single Read (< ~250 KB), read it directly and run the
extraction inline — no subagents needed. Chunking is a scale tactic, not a default.
