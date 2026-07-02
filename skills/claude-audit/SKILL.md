---
name: claude-audit
description: Audit and optimize Claude Code configuration (CLAUDE.md, .claude/rules/, skills, hooks, agents, MCP, plugins, MEMORY.md) for over-engineering, token waste, and rule-shape — whether each rule lives in the right mechanism. Consolidates claudit + config-audit. Self-contained; no external subagent fleet.
version: 1.1.0
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
  - memory
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
| Memory (index) | `{PROJECT_ROOT}/.claude/MEMORY.md` |
| Memory (topic files) | `{PROJECT_ROOT}/.claude/memory/**/*.md` |
| MCP | `{PROJECT_ROOT}/.mcp.json` |
| Plugin hooks | `{PROJECT_ROOT}/.claude/plugins/*/hooks/hooks.json` |

| Global (always) | Path |
|---|---|
| Settings | `~/.claude/settings.json` |
| Instructions | `~/.claude/CLAUDE.md` (also `~/CLAUDE.md` legacy) |
| Rules | `~/.claude/rules/**/*.md` |
| Memory (index) | `~/.claude/MEMORY.md` (or `~/.claude/projects/<proj>/memory/MEMORY.md` — project-scoped) |
| Memory (topic files) | same dir as the index, `memory/**/*.md` |
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
| memory, MEMORY.md, recall | Memory | Memory, Context Efficiency |
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

## Phase 2.5: Memory Audit (MEMORY.md + topic files)

**Premise:** `MEMORY.md` is an **always-loaded index** (200-line / ~24KB ceiling); the *value* lives in per-topic files it points to. The index line is a **retrieval key**, not prose. A stale, bloated, or redundant index wastes tokens every session and degrades recall. Memory is personal/long-term — destructive actions default to **archive** (`memory/archive/<name>.md`), never delete.

### Locate the memory tree
Resolve the index from Phase 0. Topic files = the directory the index's relative links point into (usually `memory/` alongside `MEMORY.md`). If no `MEMORY.md` mapped, skip this phase (note "Memory: not configured").

### Parse the index
For each line matching `- [Title](<rel-path>) — <hook>`, extract `{title, rel_path, hook, line_no, index_line_length}`. Lines not matching (section headers, free prose, the table-of-contents block) are tracked separately as **non-index prose** — they consume the 200-line budget without being retrieval keys.

### The four checks (per index entry)

1. **Liveness** — does the referenced topic file exist and is it resolvable? `glob` the resolved path. Missing file → broken retrieval key. If the path resolves but the named symbol/file/skill inside the body no longer exists in the repo (grep for the file path, symbol, or skill name the entry cites), the entry points at dead state.

2. **Derivability** — can the entry's claim be re-derived from a cheaper, authoritative source already loaded or trivially inspectable? Entry that restates a CLAUDE.md rule, a `git log`/`git blame` fact, an existing doc, or a code comment is **redundant** → drop. Cross-check: grep the entry's title keywords against CLAUDE.md and `references/` docs. Verbatim overlap = derivable.

3. **Redundancy** — cluster entries whose bodies name the **same failure / same correction / same artifact**. Two entries describing variants of one root cause (e.g., two "premature root cause" lessons from different sessions) → **merge** into one topic file, leave one index line. Cluster key = normalized root-cause/correction noun phrase, not the surface date.

4. **Index discipline** — is the line a retrieval key or prose? A line over ~150 chars, or containing multiple sentences, is prose masquerading as an index entry → **shorten** to `Title — one-line hook`. Also flag: entries whose topic-file body is under ~5 lines (the index line carries more than the file → fold into a sibling topic file and drop the entry).

### Verdict per entry
`keep | shorten | merge | archive`. **archive** = move the topic file to `memory/archive/` and remove its index line (reversible — `git mv` back restores). **merge** = append body into the survivor, archive the loser, rewrite the loser's index line to point at the survivor. No entry is deleted without per-item user approval.

### Open-ended self-reflection prompts (run on every `archive`/`merge` candidate before finalizing)
These optimize long-term outcomes — the audit is not just "is this file live," it's "does this memory still earn its slot in the model's future attention."

- **Future-mistake test:** What *specific* future mistake does this entry prevent, and is that mistake now blocked **structurally** (a hook, a test, a gate, a CLAUDE.md rule)? If the mistake is already structurally blocked, the memory is a shadow of enforcement that no longer needs to live in attention → archive.
- **Provenance decay:** Is the entry's evidence (file path, line number, version, gate name) still where it claims? An entry whose anchor has rotted teaches a wrong lesson → update or archive, don't leave it mis-teaching.
- **Generalization:** Does this entry encode a one-off incident (time-bound, won't recur) or a durable principle? One-offs → archive after the incident's shelf life; durable principles → keep and tighten.
- **Compounding cousin:** Is there a *different* entry this one should be merged with to form a stronger, more general lesson? (Redundancy check names obvious dupes; this prompt catches non-obvious semantic cousins.)
- **Retrieval honesty:** If a fresh session read only the index line, would it correctly predict the body? If not, the line is a broken key → rewrite.

Record answers in the audit notes; an entry survives the archive recommendation only if at least one prompt produces a concrete future-mistake that is *not* already structurally blocked.

### Output
A ranked `keep / shorten / merge / archive` table with evidence (`MEMORY.md:line`, resolved path, cluster members) and **token-delta per candidate** (always-loaded tokens freed = `(index_line_chars + topic_body_chars)/4`). Feed `archive`/`merge`/`shorten` candidates into Phase 4 (apply). Score feeds Phase 3 Memory category.

### Optional: intent-based quick-nav (large indices only)
If the index exceeds ~100 entries, emit an **intent→entry** quick-nav table grouped by activity (debug / hook-edit / plugin-work / git / etc.), `| I want to... | entry-title |`. Max 8–10 rows, grouped by category if more. This mirrors the `/lmc`+`/mlc` smart-TOC pattern: a model under attention pressure retrieves by *intent* faster than by keyword scan. Skip for small indices — it's overhead.

### Equivalence verification (mandatory after every `shorten`/`merge` in Phase 4)
After rewriting an index line or merging a topic, **re-read the new line in isolation** and confirm it still predicts the surviving body — a shortened key that no longer discriminates its own topic is information loss, not compaction (the `/mlc` "verify equivalence: ensure no information lost" rule). If the line fails this, rewrite until it predicts the body. Token savings without equivalence is a regression.

## Phase 3: Score + Report

Score the 7 categories (rubric), compute weighted overall, look up grade. Decision-memory handling in Phase 4.

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
Memory ◆              ████████████████████░░░░░  XX/100  X
```
(`◆` marks focus-relevant categories.) Then: Focus Deep Dive (if focused) → Critical Issues (category < 50) → Ranked Recommendations (focus first) → Features to Adopt.

## Phase 4: Apply + Decision Memory

Use `AskUserQuestion` (multiSelect) grouped by priority. **Never auto-apply.** For each selected fix: read → Edit/Write → report. Common fixes: CLAUDE.md trimming, rule → `.claude/rules/`+`paths:`, procedure → skill, `@import` repair, permission simplification, MCP/hook cleanup.

**Memory fixes (Phase 2.5 candidates):** default destructive action is **archive** (`git mv memory/<name>.md memory/archive/<name>.md` + drop the index line) — reversible via `git mv` back. **merge** = append body into survivor topic file, archive loser, rewrite loser's index line to alias the survivor. **shorten** = rewrite index line to `Title — one-line hook` (≤150 chars). **No memory entry is hard-deleted without per-item user approval.** Run each archive/merge through the Phase 2.5 self-reflection prompts before recording the decision.

**Scope safety:** project-scoped files (CLAUDE.md, .claude/settings.json, rules/) are PR-eligible. `CLAUDE.local.md`, `settings.local.json`, `~/.claude/`, and all memory files are personal — edit directly, never PR.

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
