# Debrief — Snapshot Handoff Chain Reconstruction (fixture-medium-mixed)

Source transcript: `fixture-medium-mixed.txt` (26 lines)
Existing task list at debrief time: **none** → all findings are CREATE (Phase 3).
DRY-RUN: no TaskCreate/TaskUpdate invoked; no source file renamed. Task IDs below are provisional (`T1`–`T6`) for graph wiring only.

---

## Open Issues

### CHS handoff-chain / walker

- **Single-handoff read discards ancestor edges.** "The single-handoff read discards ancestor edges. Session 754f0d6e's newest handoff has n_2=None, so the parent link (223e7922) is invisible. This is the defect — need a graph walk that recursively follows n_2 and unions across all handoffs." (L6)
- **Compaction-boundary uuid ordering breaks naive walkers.** "compactMetadata.preservedSegment.headUuid references an earlier uuid, so line order ≠ message order across a boundary. A walker that assumes contiguous line ranges per cycle is wrong — must follow the preservedSegment uuids." (L16)
- **Implemented fix not merged.** "Implemented CHANGE-001 (`_resolve_chain_from_handoff`) + CHANGE-002 (wire as Strategy 0). Tests 7/7 green on branch `ai/chs-chain-export`. Not merged to main yet." (L14) — needs merge + verify on main.
- **Final session note confirms the open set.** "Still open: merge the branch, fix the wrapper, the walker uuid-following." (L26)

### Tooling friction

- **Git Bash wrapper word-splits path tokens.** "the Git Bash wrapper is word-splitting path tokens — /c/Users becomes /c/Use. Broke the inline-python probe three times. Worked around with a temp file but the wrapper itself is the problem." (L10)
- **pi hangs on long inline prompts.** "pi hung for 8+ minutes on the long inline design prompt again; trivial smoke returns in seconds." (L12) — known, recurring.

### Excluded as resolved / out of scope (verified against source — NOT listed above as open)

- Registry bipartite matching failure — same root cause as the handoff defect; **Option B (native resume signal) ruled out by probe (0 of 110 transcripts resolve parentUuid to another file)** — closed dead end, recorded in task DEAD ENDS. (L8)
- Orphan worktree at `.claude/worktrees/chs-chain-export` — **cleaned up / resolved.** (L24)
- Pre-deployment island sessions (no parent_session_id) permanently unlinkable — **accepted as islands, not recoverable** — constraint, not an open issue. (L22)

---

## Opportunities

- **Reuse the existing `transcript_chain` field in `/chs` export** instead of adding a new registry field — "~10-line consumer change. The original design was re-inventing infrastructure that already exists." (L18)
- **Copy the prior terminal's handoff chain forward at SessionStart resume** to close the transient gap before the new session's first PreCompact. (L20)

---

## Proposed Tasks

Each task below uses the 8-field cold-start template (TITLE, PROBLEM, VERIFIED FACTS, MUST RE-VERIFY, DEAD ENDS, DISCRIMINATING TEST, DEFINITION OF DONE, BLOCKERS, BLAST RADIUS).

### T1 — Merge `ai/chs-chain-export` (CHANGE-001 + CHANGE-002) to main and verify

```
TITLE:          Merge the chs handoff-chain export branch to main and re-verify
PROBLEM:        The handoff ancestor-edge defect is implemented and green on a branch but lives nowhere the next session can use it.
VERIFIED FACTS: - "Implemented CHANGE-001 (_resolve_chain_from_handoff) + CHANGE-002 (wire as Strategy 0). Tests 7/7 green on branch ai/chs-chain-export. Not merged to main yet." (transcript L14)
                - Root defect the changes target: single-handoff read drops ancestor edges; session 754f0d6e newest handoff n_2=None hides parent 223e7922 (transcript L6)
                - "Still open: merge the branch, fix the wrapper, the walker uuid-following." (transcript L26)
MUST RE-VERIFY: - 7/7 green claim is from the session, NOT re-run this debrief — re-run the suite on main after merge.
                - That CHANGE-001 truly follows n_2 recursively and unions across all handoffs (the L6 requirement) — confirm against merged code, not the session narrative.
DEAD ENDS:      - Do NOT pursue a native resume signal (Option B): probe showed 0 of 110 transcripts resolve parentUuid to another file — that path is closed (transcript L8).
                - Registry bipartite matching does NOT bridge sessions — same missing-native-parent-edge root cause; do not re-attempt matching as the fix (transcript L8).
DISCRIMINATING TEST: On main after merge, run `python walk_handoff_chain.py a07ff025` (and 754f0d6e) — the ancestor edge (e.g. 223e7922) must resolve, not return None.
DEFINITION OF DONE: Branch merged to main; full test suite green on main (≥7/7, no regressions); `walk_handoff_chain.py a07ff025` resolves the previously-invisible parent uuid.
BLOCKERS:       none external (branch + tests reportedly ready).
BLAST RADIUS:   Touches the CHS export + handoff-chain resolution path. Merge is reversible (revert commit). Verify on main before any downstream consumer depends on the new edge semantics.
NEXT STEP:      diff `ai/chs-chain-export` vs main; re-run the 7 tests; merge.
```

### T2 — Make the chain walker follow `preservedSegment` uuids across compaction boundaries

```
TITLE:          Make the handoff-chain walker follow preservedSegment uuids instead of contiguous line ranges
PROBLEM:        A chain walker that assumes contiguous line ranges per cycle produces wrong order across compaction boundaries, silently corrupting reconstructed history.
VERIFIED FACTS: - "compactMetadata.preservedSegment.headUuid references an earlier uuid, so line order ≠ message order across a boundary. A walker that assumes contiguous line ranges per cycle is wrong — must follow the preservedSegment uuids." (transcript L16)
                - This is a correctness risk ON the new walker introduced by CHANGE-001/002 (T1), flagged but not yet fixed. (transcript L14, L16, L26)
MUST RE-VERIFY: - Whether CHANGE-001's current implementation already follows preservedSegment uuids or still assumes contiguous ranges — NOT confirmed this debrief; inspect the merged code from T1.
                - Existence/shape of compactMetadata.preservedSegment in a real compacted transcript — pull one and confirm the field path.
DEAD ENDS:      - Contiguous-line-range reconstruction across a boundary is the wrong premise — do not patch line offsets, follow the uuids (transcript L16).
DISCRIMINATING TEST: Walk a session that spans a compaction boundary; assert the reconstructed message order matches compactMetadata.preservedSegment.headUuid chain, not raw line order.
DEFINITION OF DONE: A regression test using a real compacted transcript passes: walker output order == preservedSegment-uuid order across the boundary. Fails on the contiguous-range assumption.
BLOCKERS:       T1 (need the merged walker code to inspect/fix). Confirmed-only-after T1 so the fix lands on main, not the branch.
BLAST RADIUS:   Same walker module as T1. Pure ordering logic — reversible by reverting the walker change. Low blast radius but high silent-correctness risk if skipped.
NEXT STEP:      After T1 merges, read _resolve_chain_from_handoff and check whether it already follows preservedSegment uuids.
```

### T3 — Fix Git Bash wrapper word-splitting path tokens (`/c/Users` → `/c/Use`)

```
TITLE:          Fix Git Bash wrapper word-splitting on Windows path tokens
PROBLEM:        Path tokens fed to the Git Bash wrapper are truncated (e.g. /c/Users → /c/Use), repeatedly breaking inline-python probes.
VERIFIED FACTS: - "the Git Bash wrapper is word-splitting path tokens — /c/Users becomes /c/Use. Broke the inline-python probe three times. Worked around with a temp file but the wrapper itself is the problem." (transcript L10)
MUST RE-VERIFY: - The exact wrapper / invocation path (which "Git Bash wrapper" — the harness shell, a profile alias, or a plugin helper) — NOT identified this debrief; locate it before patching.
                - Whether the split is tokenization or quoting — reproduce with a minimal echo of the offending path.
DEAD ENDS:      - Temp-file workaround addresses symptoms, not the wrapper — do not ship the workaround as the fix (transcript L10).
DISCRIMINATING TEST: Pass a path containing `/c/Users/...` through the wrapper; assert the receiver sees the full path verbatim (no truncation at `/c/Use`).
DEFINITION OF DONE: Minimal repro command round-trips `/c/Users/...` untruncated through the wrapper; the original inline-python probe no longer breaks on path tokens.
BLOCKERS:       none.
BLAST RADIUS:   Shell/wrapper layer — affects every command routed through it. Fix is reversible. Test with a benign path before trusting it on real probes.
NEXT STEP:      Identify the wrapper definition (profile / harness / plugin) and add a one-token path round-trip assertion.
```

### T4 — Investigate / mitigate pi hangs on long inline prompts

```
TITLE:          Stop pi from hanging 8+ minutes on long inline design prompts
PROBLEM:        Long inline prompts to pi hang for 8+ minutes while trivial smoke calls return in seconds, blocking interactive work.
VERIFIED FACTS: - "pi hung for 8+ minutes on the long inline design prompt again; trivial smoke returns in seconds." (transcript L12) — flagged "known, recurring".
MUST RE-VERIFY: - Reproduce deterministically: same long prompt → measure wall-clock; confirm the hang is prompt-length-dependent and not a transient network/provider stall.
                - Whether a shorter / chunked prompt avoids the hang — not tested this debrief.
DEAD ENDS:      - none recorded.
DISCRIMINATING TEST: Time pi on the known long prompt before vs after mitigation; assert response in ≤ N seconds (pick N from the smoke-call baseline, e.g. < 60s), not 8+ minutes.
DEFINITION OF DONE: Long-prompt call returns within the chosen timeout on 3 consecutive runs; a fallback (chunk, or timeout + route elsewhere) is in place so the session never blocks 8 minutes again.
BLOCKERS:       none.
BLAST RADIUS:   pi invocation path / prompt-construction layer. Reversible. Do not mask a real provider outage as a "fixed hang" — distinguish length-triggered from outage-triggered before claiming done.
NEXT STEP:      Capture the exact long prompt, time it cold, then test a chunked variant.
```

### T5 — Reuse `transcript_chain` field in `/chs` export instead of adding a new registry field  (OPPORTUNITY)

```
TITLE:          Reuse the existing transcript_chain field in /chs export (drop the new registry field)
PROBLEM:        The handoff-chain work risks adding a new registry field when an existing export field already carries the chain — pure re-invention.
VERIFIED FACTS: - "reuse the existing transcript_chain field in /chs export instead of adding a new registry field — ~10-line consumer change. The original design was re-inventing infrastructure that already exists." (transcript L18)
MUST RE-VERIFY: - That `transcript_chain` in the /chs export actually contains the chain the new consumers need (shape + completeness) — NOT inspected this debrief.
                - Current count of consumers of the proposed new field — if zero, the new field is pure deletion.
DEAD ENDS:      - Adding a parallel registry field duplicates existing infra — the session explicitly calls the original design re-invention (transcript L18).
DISCRIMINATING TEST: Diff the consumer change (~10 lines) pointed at transcript_chain; assert the export's chain output is byte-identical to what the new-field path would have produced.
DEFINITION OF DONE: No new registry field added; /chs export consumers read transcript_chain; existing export tests still green and a new test asserts the chain is populated end-to-end.
BLOCKERS:       T1 (the change lands on the merged chain work; coordinate so the consumer points at the merged field semantics).
BLAST RADIUS:   /chs export consumers only — ~10-line change, reversible. Confirm no consumer already depends on the would-be new field name before deleting it.
NEXT STEP:      Grep /chs export for transcript_chain to confirm it holds the needed chain.
```

### T6 — Copy prior terminal's handoff chain forward at SessionStart resume  (OPPORTUNITY)

```
TITLE:          Forward-copy the prior terminal's handoff chain at SessionStart resume
PROBLEM:        Between SessionStart resume and the new session's first PreCompact there is a transient gap where the chain is unavailable.
VERIFIED FACTS: - "copy the prior terminal's handoff chain forward at SessionStart resume to close the transient gap before the new session's first PreCompact." (transcript L20)
MUST RE-VERIFY: - That the gap is real (not already closed by CHANGE-002 / Strategy 0 wiring from L14) — confirm against merged code from T1.
                - Where the prior terminal's chain is persisted at resume time and whether SessionStart has read access — not inspected.
DEAD ENDS:      - Pre-deployment island sessions (no parent_session_id) are permanently unlinkable — do NOT try to chain those; accept as islands (transcript L22).
DISCRIMINATING TEST: Start a resume session; before its first PreCompact fires, assert the chain is already populated from the prior terminal (non-empty / resolves parent), with no wait-for-PreCompact window.
DEFINITION OF DONE: A SessionStart resume test shows the handoff chain present immediately, independent of PreCompact timing; island sessions still degrade gracefully (no parent, no crash).
BLOCKERS:       T1 (chain source must exist and be merged first). Likely T2 (correct uuid ordering should hold across the forward-copy too).
BLAST RADIUS:   SessionStart hook / resume path — runs on every resume, so verify it degrades cleanly when there is no prior terminal. Reversible; guard against reading a stale/corrupt prior chain.
NEXT STEP:      After T1 merges, locate where SessionStart resume can read the prior terminal's chain.
```

---

## Dependency Graph

```
T1 (merge CHANGE-001/002 + verify)  ──┬──► T2 (walker must follow preservedSegment uuids)
                                       ├──► T5 (reuse transcript_chain field)
                                       └──► T6 (forward-copy chain at SessionStart)
T3 (Git Bash wrapper path-split)       standalone
T4 (pi hang on long prompts)           standalone
```

Attack order: **T1 first** (it unblocks the three CHS-chain follow-ons and is reportedly merge-ready). **T2** is the highest silent-correctness risk and should be confirmed immediately after T1 merges. **T3** and **T4** are independent tooling fixes — pick up anytime. **T5** and **T6** are opportunities gated on T1 (and T6 on T2's ordering correctness).

---

## Source File Rename

DRY-RUN constraint in effect: **no file was renamed.** Proposed rename (would be applied in a real run), keeping original name + extension and appending a task-number tag bracket:

- OLD: `fixture-medium-mixed.txt`
- NEW: `fixture-medium-mixed [chs #T1 #T2 #T5 #T6 · tooling #T3 #T4].txt`

Tasks grouped by theme: **chs** (chain/walker/export) = T1, T2, T5, T6; **tooling** (wrapper, pi) = T3, T4. Resolved items (L8 Option B dead end, L22 islands, L24 worktree cleanup) contributed to DEAD ENDS / scope notes but generated no open task and so carry no tag.

---

## Report Summary

- **Open issues found:** 5 (3 CHS chain/walker, 2 tooling).
- **Opportunities found:** 2.
- **Resolved / out-of-scope items excluded from open list:** 3 (Option B dead end L8; island sessions L22; orphan worktree L24) — confirmed against source, NOT listed as open.
- **Tasks proposed (all CREATE — no existing task list):** 6 — T1 (merge+verify), T2 (walker uuid-following), T3 (Git Bash wrapper), T4 (pi hang), T5 (reuse transcript_chain — opp), T6 (forward-copy at SessionStart — opp).
- **Tasks updated:** 0.
- **Dry-run:** no TaskCreate/TaskUpdate called; no source file renamed.
