# cc-skills-analysis

The Retrospective Hub for Claude Code — session analysis, gap detection, and evidence provenance.

## 🧠 The Analysis Tribe

Modules for detecting patterns, friction, and behavioral insights in current and historical work.

### 1. Gap Analysis (Trials)
Tools for understanding what was missed or deferred.

| Skill | Purpose | Home |
|-------|---------|------|
| /gto | *DEPRECATED stub → /debrief gaps* (engine retained: orchestrator + detectors + gap reviewer + artifact contract) | `gto/` |

### 2. Session Behavioral Insight
Analyzing HOW the work is progressing.

| Skill | Purpose | Home |
|-------|---------|------|
| /behave | Analyzes LLM behavior and session patterns | `behave/` |
| /similarity | Finds functionally similar skills to prevent bloat | `similarity/` |
| /why | Deep "5 Whys" root cause analysis | `why/` |
| /top-problems | *DEPRECATED stub → /debrief top* (6-source scan engine; findings become tasks) | `top-problems/` |
| /trace | Evidence provenance and workflow tracing | `trace/` |
| /rns | Extrapolates structured findings from transcripts | `rns/` |
| /recap | Intelligent session summarization | `recap/` |
| /debrief | Unified analysis hub — transcript → root-cause tasks (modes: default/chain/gaps/top; absorbs /retro + /gto + /top-problems) | `debrief/` |
| /retro | *DEPRECATED stub → /debrief chain* (multi-session retrospective protocol + SCORES) | `retro/` |
| /epistemic-check | Validates response quality against contract | `epistemic-check/` |
| /claude-audit | Audit Claude Code config (CLAUDE.md, rules, hooks, MCP, plugins) + rule-shape fit; consolidates claudit + config-audit | `claude-audit/` |
| /skill-audit | Unified skill audit + improvement (8-category rubric, 5-phase pipeline; modes: score/patterns/contract/partition/improve/migrate-ef/intel/generate-hooks; absorbs /av) | `skill-audit/` |

## Artifacts Convention

All runtime artifacts write to:
`.claude/.artifacts/{terminal_id}/{skill_name}/`

Skills MUST NOT write state to their own directory or to the package root.

## Installation

Plugins live directly in `P:/packages/.claude-marketplace/plugins/<name>/`.
