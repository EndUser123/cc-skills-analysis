# Implementation Plan: Enhance /recap with Structured Output and Enrichment

## Context

The `recap_v2.py` pipeline produces structured typed objects (ResumePacket, Workstream, Decision, Risk, Claim, VerificationItem) but the SKILL.md handoff template (lines 231-280) ignores this output and instructs the LLM to freeform-synthesize all sections. This wastes the deterministic pipeline and creates inconsistency.

The fix: wire the v2 structured output into the handoff template, add enrichment sections that pull signals from GTO/friction/behave/trace, and use RNS `render_actions()` for domain-grouped "Next Actions".

## Files to Modify

1. **P:\packages\cc-skills-analysis\skills\recap\SKILL.md** — Update handoff template (lines 231-280)
2. **P:\packages\cc-skills-analysis\skills\recap\recap_v2.py** — Add enrichment functions, converter, and CLI flags (~250 lines)

## Changes

### SKILL.md (lines 231-280)
- Replace freeform template with typed object references
- Add enrichment sections for GTO, friction, behave, trace

### recap_v2.py
- Add Stage 8 enrichment: enrich_with_gto(), enrich_with_friction(), enrich_with_behave(), enrich_with_trace()
- Add to_rns_actions() converter (VerificationItem/Workstream → CrossSessionAction)
- Add export_for_handoff() for template substitution
- Update render_markdown() to call render_actions()
- Add CLI flags: --no-enrichment, --export-handoff

## Verification

Run `/recap` and verify:
- RNS domain grouping in Next Actions (🔧🧪📄 etc.)
- Priority dots (🔴🟠🟡🔵)
- File references (@ file.py:line)
- "0 — Do ALL" footer
- Enrichment sections populate when artifacts exist
