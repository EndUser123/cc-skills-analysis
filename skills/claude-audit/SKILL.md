---
name: claude-audit
description: Audit and optimize Claude Code configuration (CLAUDE.md, .claude/rules/, skills, hooks, agents, MCP, plugins) for over-engineering, token waste, and rule-shape — whether each rule lives in the right mechanism. Consolidates claudit + config-audit. Self-contained; no external subagent fleet.
version: 1.0.0
status: stable
category: analysis
enforcement: advisory
triggers:
  - /claude-audit
argument-hint: "[focus-area]"
allowed-tools: Task, Read, Glob, Grep, Bash, Write, Edit, AskUserQuestion
workflow_steps:
  - map
  - research
  - audit
  - score
  - apply
---

# /claude-audit — Claude Code Configuration Audit

One local-owned audit skill. Replaces `/claudit` (quickstop, third-party) and `/config-audit` (this plugin). Adds a dimension neither had: **Rule-Shape** — auditing whether each rule lives in the mechanism that matches its trigger.

## The Rule-Shape decision map (core differentiator)

A rule's **trigger** determines where it must live. The `.claude/rules/` loader supports **file paths/extensions only** — there is no activity trigger. Mis-matched trigger → either bloats every session (wrongly always-loaded) or silently never loads.

| Trigger | Mechanism | Loads |
|---|---|---|
| File path (`hooks/*.py`, `plugins/**`) | `.claude/rules/` + `paths:` glob | On matching-file read |
| Subtree (one package/module) | Subdirectory `CLAUDE.md` | On subtree read (additive, walks up) |
| Activity (debug, refactor, remove, test) | **Skill** | On invocation |
| Reusable procedure/expertise | **Skill** | On invocation |
| Truly universal (identity, language, safety) | Root / global `CLAUDE.md` | Always |

Full framework, defect catalog, and `@import`/`paths:` caveats: `references/claude-md-architecture.md`. Apply it as a scoring dimension in Phase 3.

## When invoked

Execute the phases in order. Argument is an optional focus area (see Phase 1.5). Do not summarize this file — execute it.

## Phase 0: Environment + Config Map

1. **PROJECT_ROOT** = `git rev-parse --show-toplevel 2>/dev/null` (empty if not a repo).
2. **HOME_DIR** = `echo $HOME`.
3. **Scope**: PROJECT_ROOT found → comprehensive (global + project); else global only.

Discover via parallel Glob (cap 50 files total, keep 50 most-recent):

| Project (if comprehensive) | Pattern |
|---|---|
| Instructions | `{PROJECT_ROOT}/**/CLAUDE.md` (exclude node_modules/.git/vendor/dist/build) |
| Local instructions | `{PROJECT_ROOT}/CLAUDE.local.md` |
| Rules | `{PROJECT_ROOT}/.claude/rules/**/*.md` |
| Settings | `{PROJECT_ROOT}/.claude/settings.json`, `.claude/settings.local.json` |
| Skills | `{PROJECT_ROOT}/.claude/skills/*/SKILL.md` |
| Agents | `{PROJECT_ROOT}/.claude/agents/*.md` |
| Memory | `{PROJECT_ROOT}/.claude/MEMORY.md` |
| MCP | `{PROJECT_ROOT}/.mcp.json` |
| Plugin hooks | `{PROJECT_ROOT}/.claude/plugins/*/hooks/hooks.json` |

| Global (always) | Path |
|---|---|
| Settings | `~/.claude/settings.json` |
| Instructions | `~/.claude/CLAUDE.md` (also `~/CLAUDE.md` legacy) |
| Rules | `~/.claude/rules/**/*.md` |
| Memory | `~/.claude/MEMORY.md` |
| MCP | `~/.claude/.mcp.json` |
| Plugins | `~/.claude/plugins/installed_plugins.json` |
| Managed policy | `/Library/Application Support/ClaudeCode/CLAUDE.md` (macOS) or `/etc/claude-code/CLAUDE.md` (Linux/WSL) |

Get line counts in one batched `wc -l`. Quote spaced paths. Present the map:

```
=== CONFIGURATION MAP ===
Scope: Comprehensive | Project: {PROJECT_ROOT}
  Instructions (N files, ~M tokens):
    CLAUDE.md                        45 lines
    src/api/CLAUDE.md                30 lines
    .claude/rules/testing.md         15 lines  [no paths: → always-loaded]
  ...
GLOBAL: ~/.claude/
  ...
=== END MAP ===
```

Token estimate: `(total_lines * 40) / 4`. **Flag every `.claude/rules/*.md` that lacks a `paths:` field** — those load unconditionally.

Store **GIT_USER** = `git config user.name 2>/dev/null`.

## Phase 1: Focus + Expert Context

### 1.5 Parse focus argument
If `$ARGUMENTS` empty → full audit. Else match (fuzzy) to a focus area + categories:

| Input | Focus | Categories |
|---|---|---|
| skills, agents, skill quality | Skills & Agents | CLAUDE.md Quality, Over-Engineering |
| CLAUDE.md, instructions, rules, rule-shape | Instruction Files | CLAUDE.md Quality, Over-Engineering, Context Efficiency |
| MCP, servers | MCP Configuration | MCP Configuration, Context Efficiency |
| hooks, hook sprawl | Hooks | Over-Engineering, Security Posture |
| plugins, plugin health, `<plugin-name>` | Plugins | Plugin Health |
| security, permissions, secrets | Security | Security Posture |
| over-engineering, verbosity | Over-Engineering | Over-Engineering |
| context, tokens | Context Efficiency | Context Efficiency |
| (other) | Free-form | all (best effort) |

Focus is additive depth, not routing — always run the full audit; just go deeper on focus-area findings and present them first.

### Expert context (model-routed)
Research is IO-bound → run it as a **cheap/fast** delegation; analysis is CPU-bound → run it on the **quality** model in-process. Fetch current Anthropic guidance for the target types present (CLAUDE.md memory hierarchy, `.claude/rules/` `paths:` semantics, skills progressive disclosure). Cache findings; refresh only if stale or Claude Code version changed. If research fetch fails, continue with the Rule-Shape reference (always bundled) and note the gap.

## Phase 2: Audit (in-process, quality model)

Apply `references/scoring-rubric.md` to the mapped files. For each file: read it, score against the rubric, quote evidence as `file:line`. The Rule-Shape checks (Phase 0 flagged the candidates) resolve here:

- For each rule file / CLAUDE.md section, classify its **trigger** (path / subtree / activity / universal / procedure).
- Flag mismatches per the defect catalog in `references/claude-md-architecture.md`:
  - activity-bound procedure in always-loaded tier → promote to skill
  - path-bound rule in root/global CLAUDE.md → move to `.claude/rules/` + `paths:`
  - rule file missing `paths:` → loads unconditionally (or never via legacy key)
  - subtree-specific rule at root → descend to subdirectory `CLAUDE.md`

## Phase 3: Score + Report

Score the 6 categories (rubric), compute weighted overall, look up grade. Decision-memory handling in Phase 4.

```
╔══════════════════════════════════════════════════════════╗
║                CLAUDE-AUDIT HEALTH REPORT                ║
║  Scope: Comprehensive | Files: N project + N global      ║
║  Decision Memory: N past decisions                       ║
║  Overall Score: XX/100  Grade: X  (Label)                ║
╚══════════════════════════════════════════════════════════╝
Over-Engineering      ████████████████████░░░░░  XX/100  X
CLAUDE.md Quality ◆   ████████████████████░░░░░  XX/100  X
Security Posture      ████████████████████░░░░░  XX/100  X
MCP Configuration     ████████████████████░░░░░  XX/100  X
Plugin Health         ████████████████████░░░░░  XX/100  X
Context Efficiency    ████████████████████░░░░░  XX/100  X
```
(`◆` marks focus-relevant categories.) Then: Focus Deep Dive (if focused) → Critical Issues (category < 50) → Ranked Recommendations (focus first) → Features to Adopt.

## Phase 4: Apply + Decision Memory

Use `AskUserQuestion` (multiSelect) grouped by priority. **Never auto-apply.** For each selected fix: read → Edit/Write → report. Common fixes: CLAUDE.md trimming, rule → `.claude/rules/`+`paths:`, procedure → skill, `@import` repair, permission simplification, MCP/hook cleanup.

**Scope safety:** project-scoped files (CLAUDE.md, .claude/settings.json, rules/) are PR-eligible. `CLAUDE.local.md`, `settings.local.json`, and `~/.claude/` are personal — edit directly, never PR.

### Decision memory
Path: comprehensive → `{PROJECT_ROOT}/.claude/claude-audit-decisions.json`; global → `~/.cache/claude-audit/decisions.json`. Schema `{"schema_version":1,"decisions":[...]}`. Each decision: `{fingerprint, action: accepted|rejected|deferred, reason, decided_by, timestamp, context}`. Fingerprint = `{category_slug}:{issue_type}:{file_stem}:{hash8}` (slugs in rubric).

- **Read** at Phase 0; route matching decisions into Phase 2 as context (annotate, **never suppress** — every recommendation appears regardless).
- **Write** after applying: record selected as `accepted`, and ask one follow-up to classify unselected items as `rejected`/`deferred` with optional reason.
- **Staleness**: flag for re-eval when content hash changed, impact delta ≥ 5, Claude Code version changed, age > 90 days, or deferred > 30 days.
- **Ordering**: new → stale → accepted-regression → rejected-with-reason.

### Re-score + show delta
After fixes, re-score affected categories and show before → after.

## Error handling
- Research fetch fails → continue with bundled Rule-Shape reference, note gap.
- File doesn't exist → valid data, report "not configured."
- No `.claude/` at project → audit global, recommend project setup.
- Glob > 50 → cap, note truncation.

## Principles
- Quote specific `file:line` for every finding.
- Be opinionated about over-engineering and rule-shape — this is the core value.
- Show token savings whenever removing/moving always-loaded content.
- Respect scope: project config is the team contract; personal config is personal.
- Verify before claiming absence (grep/read first).
