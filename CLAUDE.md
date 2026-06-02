# cc-skills-analysis

The Retrospective Hub for Claude Code — session analysis, gap detection, and evidence provenance.

## 🧠 The Analysis Tribe

Modules for detecting patterns, friction, and behavioral insights in current and historical work.

### 1. Gap Analysis (Trials)
Tools for understanding what was missed or deferred.

| Skill | Purpose | Home |
|-------|---------|------|
| /gto | Session-aware gap-to-opportunity analysis with execution-contract runtime | `gto/` |

### 2. Session Behavioral Insight
Analyzing HOW the work is progressing.

| Skill | Purpose | Home |
|-------|---------|------|
| /behave | Analyzes LLM behavior and session patterns | `behave/` |
| /similarity | Finds functionally similar skills to prevent bloat | `similarity/` |
| /why | Deep "5 Whys" root cause analysis | `why/` |
| /top-problems | Surfaces the highest-priority architectural blocks | `top-problems/` |
| /trace | Evidence provenance and workflow tracing | `trace/` |
| /rns | Extrapolates structured findings from transcripts | `rns/` |
| /recap | Intelligent session summarization | `recap/` |
| /retro | Full retrospective protocol and self-contrast | `retro/` |
| /epistemic-check | Validates response quality against contract | `epistemic-check/` |
| config-audit | Audits project configuration for drift | `config-audit/` |

## Artifacts Convention

All runtime artifacts write to:
`.claude/.artifacts/{terminal_id}/{skill_name}/`

Skills MUST NOT write state to their own directory or to the package root.

## Installation

Plugins live directly in `P:/packages/.claude-marketplace/plugins/<name>/`.
