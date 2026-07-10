# /recap Handoff Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use the incremental implementation workflow and verify each slice before proceeding.

**Goal:** Make the runtime `/recap` handoff resume-oriented without removing the existing detailed and brief recap behavior.

**Architecture:** Keep transcript acquisition and legacy detailed rendering intact. Add a canonical handoff renderer at the runtime entry point, with `Resume Here` first, evidence-backed completed work, separated remaining-work states, risks, decisions, artifacts, and a final checklist. Existing `brief` mode remains unchanged.

**Tech Stack:** Python, Markdown renderers, pytest.

## Global Constraints

- Do not remove legacy session-history data or `brief` mode.
- Do not claim completion without evidence from the acquired session data.
- Keep the output deterministic and bounded.
- Preserve the existing CLI entry point and argument names.

### Task 1: Add regression coverage for handoff ordering

**Files:**
- Modify: `skills/recap/tests/test_recap.py`
- Modify: `skills/recap/__init__.py`

- [ ] Add a focused test that constructs a session summary and asserts `Resume Here` precedes `Completed`, `Remaining Work`, and `Evidence Appendix`, with `Next Session Checklist` last.
- [ ] Run the focused test and confirm it fails against the current renderer.
- [ ] Implement the smallest renderer change that satisfies the ordering while retaining existing session fields.
- [ ] Run the focused recap tests.

### Task 2: Verify compatibility

- [ ] Run the complete recap test module.
- [ ] Inspect the rendered fixture/output for legacy fields, brief mode, and bounded raw context.

