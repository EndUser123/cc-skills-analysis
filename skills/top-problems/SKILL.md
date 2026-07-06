---
name: top-problems
disable-model-invocation: true
description: "DEPRECATED — use /debrief top. 6-source problem scan → ranked tasks (findings become tasks)."
enforcement: advisory
workflow_steps: []
---

# /top-problems — DEPRECATED

`/top-problems` is now `/debrief top`:

```
/debrief top <path>                  # 6-source scan → ranked tasks
/debrief top <path> --days 7 --top 15
/debrief top <path> --buckets        # P1/P2/P3 priority buckets
```

The analyzer **engine is unchanged** — `/debrief top` invokes this directory:
- Phase 1–4 procedure (6-source parallel scan, staleness gate, dedup, veto checks, X-Y detection, fix-level classification, ranking, policy modes) → `SKILL.md` body + `references/`
- Flags (`--days`, `--top`, `--focus`, `--since-commit`, `--diff`, `--buckets`, `--sensitivity`, `--policy`, `--json`) → `references/flags.md`
- Dependency graph, escalation thresholds, heat map → `references/analysis.md`

**One contract change:** `/top-problems` was identify-only ("do not automatically create tasks"). `/debrief top` **creates tasks from findings** — debrief raises issues and writes tasks, so findings surfaced by the 6-source scan become tracker tasks, routed through the same `debrief_core` state machine (CLASSIFIED → LOCATED → VERIFIED → WRITTEN) as default-mode findings. Veto checks (already-fixed, WONTFIX, duplicate-of-in-progress) still filter before task creation.

This stub will be removed after one release cycle.
