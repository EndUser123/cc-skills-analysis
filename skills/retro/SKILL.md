---
name: retro
disable-model-invocation: true
description: "DEPRECATED — use /debrief chain. Multi-session retrospective protocol (recap→gaps→friction→pre-mortem→rns + SCORES)."
enforcement: advisory
workflow_steps: []
---

# /retro — DEPRECATED

`/retro` is now `/debrief chain`:

```
/debrief chain <chain_*.md>     # full retrospective protocol with SCORES gate
```

The retrospective protocol is preserved as `/debrief`'s **chain mode**: recap → gaps → `/friction` → `/red-team` (pre-mortem) → `/rns`, with the SCORES gate (completeness/optimality/satisfaction 0–10, red-team mandatory if any axis < 8). The RNS aggregation rule (every finding from every chained skill gets an explicit MAPPED/REJECTED/DEFERRED disposition) and the retrospective-integrity self-check prompts are documented in [`skills/debrief/SKILL.md`](../debrief/SKILL.md).

`/debrief chain` and the old `/retro` share `debrief_core` (same state machine, victim-log detection, /truth gate, task template). Route all `chain_*.md` inputs through `/debrief chain` — do not invoke `/retro` directly. This stub will be removed after one release cycle.
