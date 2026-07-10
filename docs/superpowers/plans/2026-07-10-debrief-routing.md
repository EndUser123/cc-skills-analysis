# /debrief Safe Routing and Recursion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use the incremental implementation workflow and verify each slice before proceeding.

**Goal:** Preserve defect task generation while making opportunity handling explicit and recursion bounded.

**Architecture:** Keep `write_layer` as the defect writer. Route opportunities through the existing guarded `write_opportunity_layer` only when they are already VERIFIED; otherwise expose a skipped count. Add a visited-finding guard to recursive traversal and tests for mixed streams and cyclic input. Do not enable an unvalidated LLM-backed opportunity path.

**Tech Stack:** Python, dataclasses/enums, pytest.

## Global Constraints

- Defects must retain their current writer and task-body contract.
- Opportunities must never become phantom defect tasks.
- Unverified opportunities remain skipped and visible; no automatic writer arming.
- Recursion must terminate at the configured budget and on repeated finding identity.
- No cache/version bump is part of this source-only slice until tests pass.

### Task 1: Add failing routing and recursion tests

**Files:**
- Modify: `skills/debrief/tests/test_gto_adapter.py` or add a focused `test_debrief_core.py`.
- Modify: `skills/debrief/__lib/debrief_core.py`.

- [ ] Test that a mixed finding list writes defects through `write_layer` and sends VERIFIED opportunities only to the opportunity writer.
- [ ] Test that unverified opportunities are counted as skipped and do not appear in written tasks.
- [ ] Test that repeated child identity terminates without exceeding the layer budget.
- [ ] Run the focused tests and confirm they fail before the implementation.

### Task 2: Implement guarded routing

- [ ] Add a visited set keyed by finding identity to `recurse_layer`.
- [ ] Split defect and opportunity findings at the single write boundary.
- [ ] Return `opportunities_skipped` in the shared result summary.
- [ ] Keep the CLI output compatible while exposing the skip count.
- [ ] Run focused and complete debrief tests.

