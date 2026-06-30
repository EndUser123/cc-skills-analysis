# Debrief — snapshot handoff chain reconstruction

**Source:** `fixture-medium-mixed.txt`
**Mode:** dry-run (no tasks created, no file renamed)

---

## Open issues

### O1 — Ancestor edges lost in single-handoff read (parent link invisible)
**Problem:** Reading only the newest handoff discards ancestor edges. In session `754f0d6e` the newest handoff has `n_2=None`, so the parent link to `223e7922` is invisible. There is no native parent edge (verified: 0 of 110 transcripts resolve `parentUuid` to another file).
**Evidence:** Lines 4–6: `walk_handoff_chain.py a07ff025` → "newest handoff n_2=None → parent invisible"; defect = need a graph walk that recursively follows `n_2` and unions across all handoffs.
**Done looks like:** A graph walker that follows `n_2` recursively and unions across all handoffs reconstructs the full ancestor chain, including the `754f0d6e → 223e7922` edge currently dropped.

### O2 — Git Bash wrapper word-splits path tokens
**Problem:** The wrapper is word-splitting path tokens — `/c/Users` becomes `/c/Use`. Broke the inline-python probe three times. A temp-file workaround exists, but the wrapper itself is the root problem.
**Evidence:** Line 10 (explicitly tagged "the wrapper itself is the problem"); line 26 lists "fix the wrapper" as still open.
**Done looks like:** Path tokens survive the wrapper un-split (`/c/Users` round-trips intact), so inline-python probes run without the temp-file workaround.

### O3 — pi hangs on long inline design prompts (known)
**Problem:** pi hangs 8+ minutes on long inline design prompts while trivial smoke calls return in seconds. The hangs are specifically on long prompts, not general slowness.
**Evidence:** Line 12 (tagged "open issue, known").
**Done looks like:** Long inline design prompts complete (or fail fast) within an expected bound; no 8+ min silent hangs. Likely needs either a prompt-size cap, a timeout+fallback, or confirming it is upstream pi behavior and documenting the workaround.

### O4 — Branch `ai/chs-chain-export` not merged (CHANGE-001 + CHANGE-002)
**Problem:** CHANGE-001 (`_resolve_chain_from_handoff`) and CHANGE-002 (wire as Strategy 0) are implemented and tests are 7/7 green on the branch, but the branch is **not merged to main** and not verified there.
**Evidence:** Line 14 (tagged "needs merge + verify"); line 26 confirms merge still open.
**Done looks like:** Branch merged to main, tests re-run green on main, and the chain export confirmed working from main (not just the branch).

### O5 — Walker must follow `preservedSegment` uuids, not contiguous line ranges (correctness risk)
**Problem:** Across a compaction boundary, `compactMetadata.preservedSegment.headUuid` references an earlier uuid, so **line order ≠ message order**. A walker that assumes contiguous line ranges per cycle is wrong and will mis-order/reorder messages across boundaries.
**Evidence:** Line 16 (tagged "open correctness risk for the walker").
**Done looks like:** The walker follows `preservedSegment` uuids to order messages across compaction boundaries; a test exercises a non-contiguous boundary and asserts correct message ordering.

---

## Opportunities

### OP1 — Reuse existing `transcript_chain` field instead of adding a registry field
**Problem/Opportunity:** The original design re-invented infrastructure that already exists. The `transcript_chain` field is already present in `/chs export`; reusing it is a ~10-line consumer change rather than a new registry field.
**Evidence:** Line 18.
**Done looks like:** Consumer code reads the existing `transcript_chain` field; no new registry field is added.

### OP2 — Copy prior terminal's handoff chain forward at SessionStart resume
**Problem/Opportunity:** There is a transient gap between resume and the new session's first `PreCompact` where the chain is incomplete. Copying the prior terminal's handoff chain forward at `SessionStart` resume closes it.
**Evidence:** Line 20.
**Done looks like:** On `SessionStart` resume, the prior terminal's handoff chain is copied forward so the chain is complete immediately, before the first `PreCompact`.

---

## Items NOT converted to tasks

- **Resolved (excluded from open):** Registry bipartite matching + Option B (native resume signal) — ruled out by probe, 0 of 110 transcripts resolve `parentUuid`; documented as a closed dead end (line 8).
- **Resolved (excluded from open):** Orphan worktree at `.claude/worktrees/chs-chain-export` removed (line 24).
- **Accepted as-is (not recoverable):** Pre-deployment island sessions (no `parent_session_id`) are permanently unlinkable; treated as islands, not a task (line 22).

---

## Proposed tasks

| ID | Title | Severity |
|----|-------|----------|
| T1 | Merge `ai/chs-chain-export` and verify on main | Blocker |
| T2 | Rebuild walker to recursively follow `n_2` + union across handoffs | High |
| T3 | Make walker follow `preservedSegment` uuids (no contiguous-line-range assumption) | High |
| T4 | Reuse existing `transcript_chain` field instead of adding a registry field | Medium (do before T2 lands, else rework) |
| T5 | Fix Git Bash wrapper path-token word-splitting | High |
| T6 | Address pi long-prompt hangs (timeout / cap / documented workaround) | Medium |
| T7 | Copy prior terminal's handoff chain forward at SessionStart resume | Medium |

### T1 — Merge `ai/chs-chain-export` and verify on main
- **Problem:** CHANGE-001 (`_resolve_chain_from_handoff`) + CHANGE-002 (wire as Strategy 0) are 7/7 green on the branch but unmerged; main does not have the fix (O4).
- **Evidence:** Lines 14, 26.
- **Done:** Branch merged; tests green on main; chain export confirmed from main.

### T2 — Rebuild walker to follow `n_2` recursively + union across handoffs
- **Problem:** Single-handoff read discards ancestor edges; `n_2=None` makes `754f0d6e → 223e7922` invisible (O1).
- **Evidence:** Lines 4–6.
- **Done:** Walker reconstructs the full ancestor chain, including the currently-dropped `754f0d6e → 223e7922` edge.

### T3 — Make walker follow `preservedSegment` uuids across compaction boundaries
- **Problem:** Line order ≠ message order across a boundary; contiguous-line-range assumption reorders messages (O5).
- **Evidence:** Line 16.
- **Done:** Walker follows `preservedSegment` uuids; a non-contiguous-boundary test asserts correct ordering.

### T4 — Reuse existing `transcript_chain` field instead of a new registry field
- **Problem/Opportunity:** Re-invented infrastructure; an existing field covers it (OP1).
- **Evidence:** Line 18.
- **Done:** Consumer reads `transcript_chain`; no new registry field added.

### T5 — Fix Git Bash wrapper path-token word-splitting
- **Problem:** `/c/Users` → `/c/Use`; broke inline-python probe 3x; temp-file is a workaround, not a fix (O2).
- **Evidence:** Lines 10, 26.
- **Done:** Path tokens round-trip intact; inline-python probe runs without the temp-file workaround.

### T6 — Address pi long-prompt hangs
- **Problem:** 8+ min silent hangs on long inline design prompts (O3).
- **Evidence:** Line 12.
- **Done:** Long prompts complete or fail fast within an expected bound (timeout/cap), or behavior is documented with a known workaround.

### T7 — Copy prior terminal's handoff chain forward at SessionStart resume
- **Problem/Opportunity:** Transient chain gap between resume and first `PreCompact` (OP2).
- **Evidence:** Line 20.
- **Done:** Chain is complete immediately on resume, before the first `PreCompact`.

---

## Dependencies

- **T1 (merge) blocks T2, T3, T4, T7** — all modify the chain code that lives on the unmerged branch; land T1 first to avoid rebasing divergent work. T2/T3/T4 land on top of main after merge.
- **T4 before/in T2** — T2 should consume the existing `transcript_chain` field (OP1) rather than add a registry field; resolving T4 first prevents rework of T2. Treat T4 as a design input to T2, not a separate build.
- **T2 and T3 are co-dependent** — both touch the walker; do them together (T2 fixes the ancestor-edge union, T3 fixes boundary ordering). Merging them into one walker change avoids two passes over the same code.
- **T5 (Git Bash wrapper) blocks reliable inline-python probes** — independent of the chain work; unblocks diagnostics for T2/T3 but is not on the merge chain.
- **T6 (pi hangs) and T7 (SessionStart copy)** are independent of each other and of the merge chain.
- Suggested order: **T1 → (T4 folded into T2 + T3) → T7**, with **T5** and **T6** in parallel.

---

## Proposed rename of source file

Tag each open task number into the filename:

**`fixture-medium-mixed--T1-merge-T2-ancestor-walk-T3-uuid-walk-T4-reuse-field-T5-wrapper-T6-pi-hang-T7-resume-copy.txt`**

(Renamed file is NOT created — dry-run. Resolved items (dead-end Option B, orphan worktree) are intentionally untagged.)
