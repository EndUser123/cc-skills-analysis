---
name: gto
description: "DEPRECATED entry — use /debrief gaps. GTO v4.4 engine: session-aware gap-to-opportunity analysis with execution-contract runtime (deterministic detectors + mandatory haiku gap reviewer + RNS + artifact.json contract)."
version: 1.0.43
triggers:
  - "/gto"
category: analysis
contract_type: workflow-execution
enforcement: strict
workflow_steps:
  - name: run_orchestrator
    description: "Run deterministic detectors and write initial artifact"
  - name: gap_reviewer
    description: "Spawn mandatory gap reviewer subagent (haiku) to add findings"
  - name: merge
    description: "Merge-only pass to fold viewer results into artifact"
  - name: render
    description: "Display canonical RNS output via render_actions() + footer"
allowed_first_tools:
  - Bash
required_artifacts:
  - ".claude/.artifacts/{terminal_id}/gto/outputs/artifact.json"
---

# /gto — DEPRECATED entry (engine retained)

`/gto` is now `/debrief gaps`:

```
/debrief gaps <path>                 # deterministic detectors + gap reviewer + RNS + artifact contract
/debrief gaps <path> --gap-review    # two-pass haiku gap-reviewer agent
```

The GTO **engine is unchanged** — `/debrief gaps` selects it via `--gto-detectors`, which lazy-imports `skills.gto.__lib` and merges detector findings into `debrief_core.run()` at the `{symptom_text, symptom_source}` seam. Each WRITTEN task body gets a `[gto] gto_score: N | owner_skill: X` tag. Engine internals preserved verbatim:

- Orchestrator entry: `python -m skills.gto.orchestrator`
- Detectors, gap-reviewer prompts, scoring, carryover registry, resolve.py → `__lib/`, `agents/`, `schemas/`
- Runtime artifact contract: `.claude/.artifacts/{terminal_id}/gto/outputs/artifact.json`
- Boundary hooks (PreToolUse/PostToolUse/SessionStart/Stop) → `hooks/`

`/gto` remains the **source of truth** for its detector modules — `/debrief` imports, does not vendor. The `contract_type: workflow-execution` + `required_artifacts` gate on this skill stays live so direct `/gto` invocations still enforce artifact completion; `/debrief gaps` inherits the same orchestrator behavior. This stub entry will be removed after one release cycle; the engine directory (`__lib/`, `orchestrator.py`, `agents/`, `schemas/`, `hooks/`) stays.
