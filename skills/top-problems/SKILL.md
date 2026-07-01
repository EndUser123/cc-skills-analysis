---
name: top-problems
description: Analyze recent session history, premortem evidence, and task data to find the most impactful fixable problems, including systemic contract and stale-data failures
category: analysis
version: 1.0.43
status: stable
enforcement: advisory
triggers:
  - /top-problems

suggest:
  - /chs

do_not:
  - guess at problems without reading evidence files
  - list problems that are already fixed
  - skip the pending task list analysis
  - propose solutions (only identify problems)
  - automatically create tasks or plans — suggest slash commands instead
  - execute fixes directly — only suggest next steps

execution:
  directive: Scan evidence files, premortems, critique results, pending tasks, and recent git history to produce a ranked list of the top N most impactful fixable problems.
  default_args: "--days 3 --top 10"
  examples:
    - "/top-problems"
    - "/top-problems --days 7 --top 15"
    - "/top-problems --days 1 --top 5"
    - "/top-problems --ignore handoff,session_chain"
    - "/top-problems --diff"
    - "/top-problems --focus hooks"
    - "/top-problems --since-commit abc1234"
    - "/top-problems --buckets"
    - "/top-problems --sensitivity"
    - "/top-problems --diff --buckets"
    - "/top-problems --policy risk_averse"
    - "/top-problems --policy exploratory --top 5"
    - "/top-problems --json"
---

# Top Problems Analyzer (/top-problems)

## Purpose

Analyze recent session activity to surface the most impactful, fixable problems. Scans six evidence sources in parallel, deduplicates findings, ranks by impact x fixability, detects dependencies, and persists results for trend tracking.

The analyzer should explicitly cluster systemic workflow failures such as:

- contract drift
- stale-data bugs
- compact/resume failures
- producer-only success proofs
- missing consumer validators

## Arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `--days` | 3 | How many days of history to scan |
| `--top` | 10 | Number of problems to return |
| `--source` | all | Filter: `evidence`, `tasks`, `git`, `all` |
| `--status` | open | Filter: `open` (unfixed only), `all` |
| `--ignore` | (none) | Comma-separated subsystems to exclude |
| `--ignore-stale` | false | Skip STALE and LEGACY-UNKNOWN critique findings |
| `--focus` | (none) | Deep scan one subsystem: `hooks`, `handoff`, `session_chain`, `search`, `skills` |
| `--since-commit` | (none) | Scan since a git SHA instead of time-based window |
| `--diff` | false | Compare with previous run and show trends |
| `--buckets` | false | Group results into P1/P2/P3 priority buckets |
| `--sensitivity` | false | Show how stable each ranking is (fragile-rank detection) |
| `--policy` | balanced | Ranking philosophy: `balanced`, `risk_averse`, `exploratory` |
| `--json` | false | Machine-readable JSON output |

## Phase 1: Evidence Gathering

### Window Selection

1. `--since-commit <sha>`: use `git log <sha>..HEAD` for commits, `git diff <sha>..HEAD --stat` for changed files
2. `--focus <area>`: run focused deep scan (see `references/flags.md` for per-area methods)
3. Default: use `--days N` time-based window

### Broad Parallel Scan (default)

Run these 6 scans in parallel:

| # | Source | Path/Command | Extract |
|---|--------|-------------|---------|
| 1 | Pre-mortems | `P://.claude/.artifacts/{terminal_id}/top-problems/premortem_*.md` | OPEN/DEFERRED items, risk scores |
| 2 | Critiques | `P://.claude/.artifacts/{terminal_id}/critique/*/p1_findings.md` + staleness gate | CRITICAL/HIGH findings with staleness badge |
| 3 | Tasks | TaskList or `git status` | pending/in_progress, no owner |
| 4 | Git | `git log --since="<date>" --oneline` | fix/bug/BLOCKER/revert patterns |
| 5 | Session errors | `~/.claude/projects/P--/*.jsonl` (last 500 lines) | `"is_error":true` |
| 6 | Auto-retries | Same JSONL files | Consecutive identical tool_use (3+ repeats) |

### Window Fallback

If zero evidence found: double window to N*2, then N*4, cap at 30 days. Note expansion in output.

### Staleness Gate (Critiques only)

Before ingesting any `p1_findings.md` from a critique session directory:

1. **Read `source_metadata.json`** from the same session directory if present.
2. **Compare `git_sha` to current HEAD**: run `git rev-parse HEAD` in the project root.
   - If SHA differs from stored → mark ALL findings from that session as `STALE`.
   - If SHA matches → findings are `CURRENT`.
3. **If `source_metadata.json` absent** (legacy sessions created before this gate) → mark findings as `LEGACY-UNKNOWN`.
4. **Report staleness in output**: `STALE: {N} critique sessions | LEGACY-UNKNOWN: {N} | CURRENT: {N}`.
5. **Score penalty**: `STALE` findings receive 0.5x cross_ref_multiplier; `LEGACY-UNKNOWN` receive 0.3x.
6. **Exclusion option**: `--ignore-stale` flag skips STALE and LEGACY-UNKNOWN findings entirely.

> Rationale: Critique findings are snapshots of code state at session creation time. Code changes after the session invalidates severity claims. The `source_metadata.json` (written by `pre-mortem`'s `setup()`) captures git SHA at critique-start for this comparison.

## Phase 2: Deduplication & Clustering

### Cross-Source Dedup

Group by root cause: same file:line, same risk ID (P-4, F-007), same task across sources.

Record per problem: title, evidence sources (file:line), cross-ref count, impact, fix scope, status.

### Dependency Graph

Identify blocking, same-file conflicts, and cascade risks between problems.
See `references/analysis.md` for full dependency detection rules and output format.

### Exclude Filter

Apply `--ignore` after dedup. Skip problems in excluded subsystems.

### Veto Checks (always-on)

Auto-exclude problems meeting any veto condition, regardless of score:

| Veto Condition | Check Method |
|---------------|-------------|
| Already fixed in git | `git log --grep="<keyword>" --since="<window>"` finds merged fix |
| Marked WONTFIX/BYDESIGN | Grep evidence sources for `WONTFIX`, `BYDESIGN`, `INTENTIONAL` |
| Duplicate of in-progress task | TaskList shows same problem with owner in `in_progress` |

Record vetoed items in output: `Vetoed: {N} problems ({reasons})`.

### Contract-Failure Clustering (always-on)

When multiple findings point to boundary failures, cluster them into a systemic problem family instead of listing isolated symptoms.

Examples:

- same subsystem repeatedly missing validators
- repeated stale-artifact reuse
- resume/handoff failures across sessions
- multiple fixes that only prove producer success

### X-Y Problem Detection (always-on)

After dedup, check for symptom-vs-root-cause patterns:

1. **Same-file clustering**: If 3+ problems reference the same file, flag the file as a potential root cause.
2. **Fix pattern repetition**: If 3+ problems propose the same type of fix (e.g., "add timeout", "add fallback"), flag as symptom pattern.
3. **Band-aid chain**: If problem A's fix would create problem B (already in the list), flag A as treating a symptom.

For each X-Y detection, add to output: `"XY-SUSPECT: {file/pattern} — {N} problems may share root cause."`

## Phase 3: Ranking

Score: `impact(1-5) x fixability(1-5) x cross_ref_multiplier`

**Multipliers**: 1 source=1.0x, 2 sources=1.2x, 3+ sources=1.5x

### Confidence Scoring (always-on)

Each problem gets a confidence badge: `[HIGH]`, `[MED]`, `[LOW]`

| Factor | HIGH | MEDIUM | LOW |
|--------|------|--------|-----|
| Evidence sources | 3+ distinct sources | 2 sources | 1 source |
| Evidence recency | Last 24h | 2-3 days | >3 days |
| Evidence type | Direct (git errors, JSONL) | Mixed | Analysis only (premortem) |

Low-confidence problems get note: `"Limited evidence — consider --focus <subsystem> for deeper scan."`

### Priority Buckets (`--buckets`)

After ranking, assign deterministic buckets:

| Bucket | Criteria | Action |
|--------|---------|--------|
| **P1 Immediate** | Score >= 16 AND fixability >= 4 | Fix this session |
| **P2 This Week** | Score >= 10 OR impact = 5 | Plan and schedule |
| **P3 Backlog** | Everything else | Defer |

Output includes: `P1: {N} problems | P2: {N} | P3: {N}`

| Impact | Fixability |
|--------|-----------|
| 5: Every tool call/session | 5: Single file, <20 lines |
| 4: Core skill (/recap, /gto) | 4: Single file, <50 lines |
| 3: Specific workflow | 3: 2-3 files, clear path |
| 2: Single hook/edge case | 2: Multi-file, needs design |
| 1: Cosmetic only | 1: Research phase |

### Trend Detection (`--diff`), Regression Detection, Severity Escalation, Resolution Tracking

### Fix Level Classification (always-on)

Classify each problem's proposed fix on the Escalation Ladder:

| Level | Description | Signal |
|-------|-------------|--------|
| **Band-Aid** | Patches the symptom | "This will break again" |
| **Local Optimum** | Optimizes within current assumptions | "Cleaner but same shape" |
| **Reframe** | Questions the problem statement | "What if the problem is actually..." |
| **Redesign** | Changes the system so problem doesn't exist | "With this change, we wouldn't need to..." |

Output adds `fix_level` column. Problems with 3+ Band-Aid fixes to same file → X-Y SUSPECT.

### Policy Modes (`--policy`)

Adjust ranking weights by policy:

| Policy | Impact Weight | Fixability Weight | Use When |
|--------|--------------|-------------------|----------|
| `balanced` (default) | 1.0x | 1.0x | General purpose |
| `risk_averse` | 2.0x | 0.5x | Prioritize high-impact problems regardless of fix difficulty |
| `exploratory` | 0.5x | 2.0x | Prioritize quick wins and hidden problems |

In `risk_averse` mode, a problem with impact=5 and fixability=2 scores: `(5*2.0) * (2*0.5) * multiplier = 10.0 * multiplier`.

See `references/flags.md` for `--diff` procedure (including regression detection) and `references/analysis.md` for escalation thresholds and resolution tracking.

## Phase 4: Output

### Results Cache

Write to `P://.claude/.artifacts/{terminal_id}/top-problems/top-problems_<YYYYMMDD>.md`.

Read artifact files using the **Read tool** (not `cat` or `python -c`) — nested quoting breaks on Windows/bash.

### Output Format

**Markdown table** (default):

| # | Problem | Score | Impact | Fix | Sources | Confidence | Bucket | Fix Level | Trend | Conflicts |
|---|---------|-------|--------|-----|---------|-----------|--------|-------|-----------|

**Problem cards**: title, score with multiplier, evidence (file:line), impact, fix, confidence, bucket, status, blocks, conflicts.

**Heat map**: ASCII bar chart by directory. See `references/analysis.md`.

**JSON** (`--json`): Full schema in `references/flags.md`.

### Action Suggestions

| Problem Type | Suggested Command |
|-------------|-------------------|
| Fixability >= 4 | `Try: /task to create a tracked fix` |
| Fixability 2-3 | `Try: /planning to design the approach` |
| Fixability 1 | `Try: /pre-mortem to analyze before fixing` |
| Quality concern | `Try: /critique for adversarial review` |
| Stale (3+ runs) | `Try: /reflect to extract lessons` |
| CRITICAL-STALE | `Try: /pre-mortem specifically for this problem` |
| CRITICAL-NEW | `Try: /planning to design immediate fix` |
| 3+ Band-Aids to same file | `XY-SUSPECT — Try: /solution-space for systemic redesign` |
| Band-Aid fix level | `Consider: Is this treating a symptom? Check for X-Y suspects.` |
| Redesign fix level | `Try: /planning to design architectural change` |

**Do NOT** execute these commands. Only suggest them.

## Routing Behavior

`/top-problems` is a prioritizer. It should suggest lower skills based on the owning failure type:

- `/design` for systemic contract/state redesign
- `/planning` for multi-step fixes needing explicit task shape
- `/pre-mortem` for risky or repeated failures
- `/critique` for adversarial review before committing to a fix
- `/verify` for cases where the main issue is lack of proof rather than lack of implementation

`/top-problems` must not execute fixes directly.

### Footer

Quick wins, stale count, escalated, resolved, excluded, vetoed, conflicts, window type. Suggest `/task`, `/planning`, `/pre-mortem`, `/top-problems --diff`.

## Periodic Usage

```
/loop 1d /top-problems --days 3 --top 5 --diff
```

## Phase Gates

**GATE 1 (STOP after Phase 1: Evidence Gathering)**: Before moving to Phase 2 (Deduplication & Clustering), verify:
- At least 3 of 6 evidence sources returned data (or explicit "none found" noted)
- Window expansion logged if triggered
- Staleness check performed on critique findings

If gate fails: expand window or note evidence gaps before proceeding.

**GATE 2 (STOP after Phase 2: Deduplication & Clustering)**: Before moving to Phase 3 (Ranking), verify:
- Cross-source deduplication applied
- Veto checks completed
- X-Y problem detection run
- Dependency graph built

If gate fails: complete dedup and clustering before ranking.

**GATE 3 (STOP after Phase 3: Ranking)**: Before moving to Phase 4 (Output), verify:
- Confidence scoring assigned to each problem
- Priority buckets assigned (if --buckets)
- Fix level classification completed
- Policy weights applied (if non-default)

If gate fails: complete ranking before output.

**STOP between phases**:
- Phase 1 (Gather) → Phase 2 (Deduplicate): Must gather evidence before dedup
- Phase 2 (Deduplicate) → Phase 3 (Rank): Must dedupe before ranking
- Phase 3 (Rank) → Phase 4 (Output): Must rank before output

---

## Evidence Sources

| Source | Path | What to extract |
|--------|------|----------------|
| Pre-mortems | `P://.claude/.artifacts/{terminal_id}/top-problems/premortem_*.md` | OPEN/DEFERRED items |
| Critiques | `P://.claude/.artifacts/{terminal_id}/critique/*/p1_findings.md` | CRITICAL/HIGH |
| Tasks | TaskList tool | pending/in_progress |
| Git | `git log --since` or `<sha>..HEAD` | fix/bug/BLOCKER |
| Sessions | `~/.claude/projects/P--/*.jsonl` | `"is_error":true` (sample) |
| Retries | Same JSONL | Consecutive identical tool_use |
| Previous runs | `P://.claude/.artifacts/{terminal_id}/top-problems/top-problems_*.md` | Trend, resolution |

## Evidence-First Principles

### E1 — Evidence before claims
Before claiming code is absent, unchanged, or non-existent — search the codebase and verify with tools first. Claims of absence are only valid after confirmed Read/Grep/git failures.

### E4 — Investigate before asking
Do NOT answer without reading relevant source files first. Do not ask the user for information you can obtain yourself via Read, Grep, Bash, git, or available MCP tools.

### E5 — Anti-lazy escape hatch
Prohibited:
- "I assume", "I think", "probably" without tool verification
- Claiming something doesn't exist without confirmed tool failure
- Skipping evidence gathering because the answer seems obvious

## Reference Files

| File | Contents |
|------|----------|
| `references/flags.md` | `--focus` scan methods, `--since-commit` procedure, `--diff` matching rules, `--json` full schema |
| `references/analysis.md` | Dependency graph rules, escalation thresholds, resolution tracking, heat map format |

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `/chs` | Search session transcripts for specific errors |
| `/gto` | GTO health analysis identifies code quality gaps |
| `/pre-mortem` | Create premortems for planned changes |
| `/critique` | Run adversarial review on recent changes |
| `/reflect` | Extract lessons from session history |
| `/planning` | Design implementation approach |
| `/task` | Create tracked work items |
| `/loop` | Set up periodic problem scanning |

## Version

3.4.0 (2026-04-02) - Added systemic contract/stale-data clustering

## Artifact I/O — Bash Fallback

When writing the top-problems result file, use the **Write tool**. If the Write tool reports a CROSS-WORKTREE error, fall back to Bash with `python -c` using a temp variable for content (NOT inline JSON — nested quoting breaks on Windows/bash):

```bash
CONTENT='[the JSON content as a string]'
python -c "
from pathlib import Path
Path('P:/.claude/.artifacts/${TERMINAL_ID}/top-problems/result.json').write_text('''$CONTENT''', encoding='utf-8')
"
```

`${TERMINAL_ID}` is a stable per-terminal identifier resolved by `P:/packages/search-research/core/terminal_id.py:canonical_terminal_id()` from the `WT_SESSION` env var (with a hostname+pid fallback). The same value is the directory name under `P:/.claude/.artifacts/` where the top-problems cache file lives. Use the literal `${TERMINAL_ID}` — do not substitute; the cache lookup keys on this exact name.

Read artifact files using the **Read tool** (not `cat` or `python -c`). For pre-written helper scripts, use the scripts in `__lib/`.
