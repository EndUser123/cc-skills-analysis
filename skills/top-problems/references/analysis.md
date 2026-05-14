# Analysis Reference: Dependency Graph, Escalation, Heat Map, Resolution

## Dependency Graph

After dedup, analyze relationships between problems:

1. **Blocking**: If problem A must be fixed before problem B can be fixed (shared file:line that both reference), record `A blocks B`.
2. **Same-file conflicts**: If two problems require changes to the same file, flag `CONFLICT: {file}`.
3. **Cascade risk**: If problem A's failure would trigger problem B, record `A cascades to B`.

Present dependencies as a simple adjacency list:
```
Dependencies:
  P-1 (stale sessions-index) -> blocks P-5 (walk_session_chain timeout)
  P-3 (st_ctime ordering) -> cascades to P-9 (datetime.min fallback)
  P-4 (sessions-index empty) CONFLICT with P-5: session_chain.py:296
```

## Severity Escalation

Auto-escalate problems meeting these criteria:

| Condition | Escalation | Suggested Action |
|-----------|------------|-----------------|
| Score >= 15 AND appears 3+ runs unchanged | `CRITICAL-STALE` | `Try: /pre-mortem specifically for this problem` |
| Score >= 20 AND new this run | `CRITICAL-NEW` | `Try: /planning to design immediate fix` |
| Cross-ref count >= 3 | `WELL-VALIDATED` | High confidence — safe to prioritize |
| Previously RESOLVED, now in evidence again | `REGRESSION` | Auto-escalate to P1 bucket — fixed problem reappeared |

## Resolution Tracking

Compare current results against ALL previous cached runs:
1. If a problem from a previous run is no longer found in any evidence source -> mark as `RESOLVED`
2. Show resolved count: `"{N} problems resolved since last run."`
3. List briefly: `"Resolved: P-7 (sys.path fragility) — no longer in evidence."`

## X-Y Problem Detection

After dedup, check whether problems are symptoms of deeper issues:

### Detection Rules

| Signal | Threshold | Action |
|--------|-----------|--------|
| Same file in 3+ problems | File appears in evidence for 3+ distinct problems | `XY-SUSPECT: {file} — possible root cause behind {N} symptoms` |
| Same fix pattern 3+ times | "add timeout", "add fallback", "add null check" repeated | `XY-SUSPECT: {pattern} — {N} band-aids suggest systemic issue` |
| Band-aid chain | Problem A's fix would create problem B (already in list) | `XY-SUSPECT: P-{A} fix creates P-{B} — treating symptom` |
| Recurring subsystem | 3+ problems in same directory across runs | `XY-SUSPECT: {dir}/ — recurring issues suggest design debt` |

### Output Integration

X-Y suspects appear as a separate section after the problem table:
```
## X-Y Suspects
- session_chain.py — 4 problems (P-3, P-4, P-5, P-9) share this file. Consider `/solution-space` for systemic redesign.
- "add fallback" pattern — 3 fixes propose fallbacks. Root cause may be missing timeout infrastructure.
```

### Escalation Ladder (Fix Level)

Each problem gets a `fix_level` classification:

| Level | Criteria | Example |
|-------|----------|---------|
| **Band-Aid** | Patches symptom, <10 lines, doesn't address cause | Add null check, catch exception, hardcode edge case |
| **Local Optimum** | Optimizes within current design, <50 lines | Extract method, add parameter, refactor for readability |
| **Reframe** | Questions the problem framing, changes approach | "Why do we cache this?" instead of "fix cache invalidation" |
| **Redesign** | Changes system so problem doesn't exist | Make data flow unidirectional instead of fixing sync conflicts |

Classification logic:
1. Single file, <20 lines, doesn't touch architecture → Band-Aid
2. Single file, <50 lines, improves existing design → Local Optimum
3. 2-3 files, changes approach rather than patching → Reframe
4. Multi-file, changes data flow or architecture → Redesign

**Band-aid chain detection**: If 3+ problems in same file are all Band-Aid level → escalate to `XY-SUSPECT` with suggestion to consider Reframe or Redesign.

Compare current results against ALL previous cached runs:
1. If a problem from a previous run is no longer found in any evidence source -> mark as `RESOLVED`
2. Show resolved count: `"{N} problems resolved since last run."`
3. List briefly: `"Resolved: P-7 (sys.path fragility) — no longer in evidence."`

## Heat Map by Directory

After the problem table, show a concentration summary:

```
## Directory Heat Map

hooks/                    ████████░░  8 problems
packages/search-research/ ████░░░░░░  4 problems
packages/handoff/         ██░░░░░░░░  2 problems
.claude/skills/           █░░░░░░░░░  1 problem
```

Each block char = 1 problem. Directories with 0 problems are omitted.
