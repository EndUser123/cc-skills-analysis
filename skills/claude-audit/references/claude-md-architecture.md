# CLAUDE.md Architecture Reference

The decision framework for *where a rule should live*. This is the differentiating knowledge `/claude-audit` adds over generic config auditors: it doesn't just ask "is CLAUDE.md too long?" but "is each rule in the **right mechanism**?"

## Core reframe

The question is never "how do I fit all rules in CLAUDE.md." It is "which rules are even CLAUDE.md-shaped." A rule's **trigger** determines which mechanism can carry it. Mismatching trigger to mechanism is the most common — and most expensive — config defect, because it produces rules that either bloat every session (wrongly always-loaded) or silently fail to load when needed (wrongly conditional).

## The loader's only conditional mechanism

Claude Code's `.claude/rules/` loader triggers on **file paths and file extensions only**. There is no "activity," "intent," or "task-type" trigger. This is the hard constraint every rule-placement decision must respect:

- A rule that fires when a *file location* is touched → expressible as a path glob → candidate for `.claude/rules/` + `paths:` frontmatter.
- A rule that fires when an *activity* is performed (debugging, refactoring, removing code, testing) → **not expressible** as a path glob. It cannot be conditionally loaded. It must either stay always-on (in CLAUDE.md) or become a **skill** invoked when the activity starts.

Frontmatter key: the schema-documented field is `paths:` (a list of glob patterns). Legacy `alwaysApply:` / `patterns:` keys may exist in older files — treat them as suspicious: verify the loader still honors them before relying on them. When in doubt, migrate to `paths:`.

## The trigger → mechanism decision map

For each rule, identify its trigger, then place it in the matching mechanism:

| Trigger | Mechanism | Loads when | Token cost |
|---|---|---|---|
| **File path** (rule is about `hooks/*.py`, `plugins/**`, `*.tsx`) | `.claude/rules/` + `paths:` glob | Claude reads a matching file | On-demand only |
| **Subtree** (rule is about one package/module) | Subdirectory `CLAUDE.md` | Claude reads files under that subtree | On-demand (additive, walks up to root) |
| **Activity** (debugging, removing, refactoring, testing) | **Skill** | User invokes the skill | On-demand only |
| **Truly universal** (epistemic discipline, language, safety, identity) | Root / global `CLAUDE.md` | Every session | Always-loaded |
| **Reusable procedure/expertise** (a workflow, a playbook) | **Skill** | User invokes the skill | On-demand only |

## The three loads-at-launch tiers

1. **Always-loaded** — root `CLAUDE.md`, global `~/.claude/CLAUDE.md`, and every `.claude/rules/*.md` *without* a `paths:` field. These fire every session regardless of task. Target < 200 lines / ~2500 tokens per file; adherence drops past that.
2. **On-demand by file path** — `.claude/rules/*.md` *with* a `paths:` field, and subdirectory `CLAUDE.md` files. Load only when matching files are touched. This is the **only** mechanism that removes content from the always-loaded baseline.
3. **On-demand by invocation** — skills. Load only when invoked. The correct home for activity-bound rules and reusable procedures.

## What `@import` does and does not do

`@path/to/file` imports expand at launch — imported content **enters context at session start**. `@import` is an *organizational* tool (split a large file into editable sections, co-locate rules with the code they describe), **not** a token-reduction tool. An imported 200-line file costs the same always-loaded budget as an inline 200-line file. Use it for maintainability; never mistake it for a diet. Limits: max 4 import hops, not evaluated inside code spans, hard cap ~5 deep, prefer depth ≤ 3.

## Rule-shape defects (what to flag in an audit)

- **Activity-bound rule stranded in CLAUDE.md as always-loaded** when it should be a skill. *Symptom:* a multi-step procedure (debugging protocol, removal checklist, refactor gate) sitting in the always-loaded tier, paid for every session but relevant to one activity. *Fix:* promote to a skill.
- **Path-bound rule stranded in CLAUDE.md as always-loaded** when it could be `.claude/rules/` + `paths:`. *Symptom:* a rule that only matters for one directory (hooks/, plugins/) but loads globally. *Fix:* move to `.claude/rules/` with a scoped `paths:` glob.
- **Path-bound rule with no/wrong frontmatter** → loads unconditionally or never. *Symptom:* file has `alwaysApply: false` but no `paths:` field, or uses a legacy key. *Fix:* add/migrate to `paths:`.
- **Reusable expertise buried in CLAUDE.md** — Anthropic's documented #1 confusion ("using CLAUDE.md for reusable expertise that belongs in a skill").
- **Root file holding subtree-specific rules** — local conventions for one package sitting at the repo root. *Fix:* descend into a subdirectory `CLAUDE.md`.

## Grow-don't-shrink, but itemize

A large CLAUDE.md is acceptable when growth goes into **scoped subtree files and skills**, not one ballooning root file. For rules that genuinely must stay always-loaded, prefer **itemized high-signal entries** (one directive per line, optionally tagged with an ID and feedback counter) over prose paragraphs — and never let an LLM auto-summarize/compress them (context collapse loses the discriminating detail). The discipline is: keep the *always-loaded* tier lean and universal; let everything else grow in the on-demand tiers.

## Layering cheat-sheet

```
~/.claude/CLAUDE.md          # global, always-loaded — identity, language, cross-project safety
<repo>/CLAUDE.md              # root, always-loaded — pointers + critical gotchas only
<repo>/CLAUDE.md → @AGENTS.md # cross-harness bridge for non-Claude tools (Codex/Cursor/agy)
<repo>/.claude/rules/*.md     # path-scoped, on-demand — path: glob controls loading
<repo>/<pkg>/CLAUDE.md        # subtree, on-demand — package-local conventions
<repo>/.claude/skills/*/SKILL.md  # invocation, on-demand — activity-bound procedures
```

## Sources

- Anthropic, "How Claude Code works in large codebases" (May 2026) — layered CLAUDE.md, "root = pointers + gotchas only," skills as progressive disclosure, "common confusion: using CLAUDE.md for reusable expertise that belongs in a skill."
- Claude Code docs, "How Claude remembers your project" — `paths:` frontmatter, `@import` semantics (expands at launch, max 4 hops), <200 line guidance.
- Folkman, "Your CLAUDE.md should grow, not shrink" — itemized entries, never auto-compress (Stanford ACE framework).
