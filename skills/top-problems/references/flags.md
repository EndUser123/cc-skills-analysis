# Flag Reference: --focus, --since-commit, --diff, --json

## --focus <area>

When specified, skip the broad 6-source scan and run a targeted deep dive on one subsystem.

| Focus Area | Scan Method | What to Find |
|-----------|-------------|--------------|
| `hooks` | Grep all files in `hooks/` for `TODO`, `FIXME`, `HACK`, `except.*pass`, bare `except` | Dead code, suppressed errors, deferred fixes |
| `handoff` | Trace full handoff pipeline: `transcript.py` -> `handoff_v2.py` -> hooks | Structural gaps, missing error handling |
| `session_chain` | Read `session_chain.py` + all callers (`/recap`, `/gto` skills) | Import failures, ordering bugs, timeout risks |
| `search` | Grep `packages/search-research/` for deprecated functions, broken imports | API drift, unused code paths |
| `skills` | Glob all `SKILL.md` files, check frontmatter validity, broken suggest links | Missing fields, one-way integrations |

Focused scans produce problems with `fixability` boosted by 1 (max 5) because the investigation is already partially done.

## --since-commit <sha>

Instead of time-based window, scan everything since a specific git SHA:
- Commits: `git log <sha>..HEAD --oneline`
- Changed files: `git diff <sha>..HEAD --stat`
- Evidence files: use modification time of files changed since that commit's date

## --diff

Compare with previous run. Read the most recent `P://.claude/.evidence/top-problems_YYYYMMDD.md`.

Match problems by title similarity (fuzzy match on key file:line references). For each match, show trend:
- `up N->M` (score increased — getting worse)
- `down N->M` (score decreased — improving)
- `unchanged N` (unchanged)

**Stale alert**: 3+ consecutive runs unchanged → flag `STALE`, suggest `/pre-mortem` for that specific problem.

**Regression detection**: Cross-reference `RESOLVED` problems from previous run against current evidence. If a previously-resolved problem appears again, flag as `REGRESSION` with auto-escalation: bump bucket to P1, add `REGRESSION` badge. Report: `"{N} regressions detected — previously fixed problems reappeared."`

## --buckets

Group ranked problems into deterministic priority buckets:

| Bucket | Criteria | Action |
|--------|---------|--------|
| **P1 Immediate** | Score >= 16 AND fixability >= 4 | Fix this session |
| **P2 This Week** | Score >= 10 OR impact = 5 | Plan and schedule |
| **P3 Backlog** | Everything else | Defer |

Output includes bucket summary: `P1: 2 | P2: 4 | P3: 4`

Each problem card shows its bucket. Table gets a `Bucket` column.

## --sensitivity

After ranking, check how stable each problem's position is:

1. For each adjacent pair (rank N and rank N+1), compute score delta
2. If delta < 2: flag lower-ranked problem as `FRAGILE-RANK` (could swap with N+1)
3. Compute: what would change if impact or fixability shifted by ±1
4. Report: `"P-3 FRAGILE: score 18 vs P-4 score 17 (delta=1). P-3 impact=4→5 would make it 22.5"`

Inspired by decision-matrix sensitivity analysis (weighted criteria close calls).

Red flags:
- Top 3 problems all within delta < 2 → ranking is noisy, treat as a cluster
- Problem at rank 1 is FRAGILE → note "leading by narrow margin"

## --policy

Adjust ranking weights by decision policy. Affects score calculation, not evidence gathering.

| Policy | Impact Wt | Fix Wt | Use When |
|--------|-----------|--------|----------|
| `balanced` (default) | 1.0 | 1.0 | General purpose |
| `risk_averse` | 2.0 | 0.5 | "What will hurt most if unfixed?" |
| `exploratory` | 0.5 | 2.0 | "What quick wins are we missing?" |

Score formula with policy: `(impact * impact_wt) * (fixability * fix_wt) * cross_ref_multiplier`

Example: impact=5, fix=2, balanced=10.0, risk_averse=10.0, exploratory=5.0.

**When to use each:**
- `risk_averse`: Before a release cut, after a critical incident, when reliability is paramount
- `exploratory`: During backlog grooming, when looking for momentum, when stuck on large problems
- `balanced`: Default for periodic scanning

In `--json` output: `"policy": "risk_averse", "policy_weights": {"impact": 2.0, "fixability": 0.5}`

## --json

Machine-readable output. Full schema:

```json
{
  "run_date": "YYYY-MM-DD",
  "window_days": 3,
  "window_type": "time | commit | focus",
  "since_commit": "sha or null",
  "focus_area": "area or null",
  "total_evidence_sources": 12,
  "problems": [
    {
      "rank": 1,
      "title": "...",
      "score": 22,
      "impact": 5,
      "fixability": 4,
      "cross_refs": 3,
      "status": "OPEN",
      "escalation": "null | CRITICAL-STALE | CRITICAL-NEW | WELL-VALIDATED | REGRESSION",
      "evidence": [{"file": "path", "line": 42, "source": "premortem"}],
      "confidence": "HIGH | MED | LOW",
      "bucket": "P1 | P2 | P3",
      "sensitivity": {"delta_to_next": 2, "fragile": false},
      "fix_level": "Band-Aid | Local Optimum | Reframe | Redesign",
      "policy": "balanced | risk_averse | exploratory",
      "policy_weights": {"impact": 1.0, "fixability": 1.0},
      "fix_scope": {"files": ["path"], "complexity": "S|M|L"},
      "blocks": ["P-4"],
      "conflicts": [],
      "directory": "hooks/",
      "trend": {"direction": "up|down|unchanged|new", "prev_score": 18, "runs_unchanged": 0}
    }
  ],
  "xy_suspects": [
    {"file": "session_chain.py", "problems": ["P-3","P-4","P-5","P-9"], "pattern": "same-file clustering", "suggestion": "Consider /solution-space for systemic redesign"}
  ],
  "resolved": ["P-7"],
  "heat_map": {"hooks/": 8, "packages/search-research/": 4},
  "summary": {
    "quick_wins": 3,
    "stale_count": 2,
    "escalated_count": 1,
    "excluded_count": 0,
    "resolved_count": 1,
    "conflict_count": 1
  }
}
```
