# Claude-Audit Scoring Rubric

Ported from claudit (acostanzo/quickstop) with the Rule-Shape additions that distinguish `/claude-audit`. Each category starts at base **100**; apply deductions and bonuses; clamp 0–100. Overall = weighted average.

## Categories & Weights

| Category | Weight | What It Measures |
|----------|--------|------------------|
| Over-Engineering Detection | 20% | Unnecessary complexity, verbosity, redundancy |
| CLAUDE.md Quality (incl. Rule-Shape) | 20% | Structure, conciseness, **mechanism fit** (right rule in right place), token efficiency |
| Security Posture | 15% | Permission hygiene, secrets exposure, tool restrictions |
| MCP Configuration | 15% | Server health, tool sprawl, unused servers |
| Plugin Health | 15% | Version currency, structure, legacy patterns |
| Context Efficiency | 10% | Token budget awareness, config bloat |
| Memory | 5% | MEMORY.md index discipline, liveness, derivability, redundancy |

## Grade Thresholds

| Grade | Score | Label |
|---|---|---|
| A+ | 95-100 | Exceptional |
| A | 90-94 | Excellent |
| B | 75-89 | Good |
| C | 60-74 | Fair |
| D | 40-59 | Needs Work |
| F | 0-39 | Critical |

## Visual Score Bar

```
Category Name        ████████████████████░░░░░  82/100  B
```
`█` filled = `score/100 * 25` chars; `░` remainder; then score and grade.

## Over-Engineering Detection (20%)

**Philosophy:** Claude does the heavy lifting. Verbose instructions, excessive hooks, and complex permission rules consume context and fight Claude's natural capabilities.

### Deductions
| Issue | Points | Description |
|---|---|---|
| CLAUDE.md > 2500 tokens | -20 | Excessive verbosity (tiers exclusive — highest only) |
| CLAUDE.md > 1500 tokens | -10 | Likely contains redundancy (not applied if >2500 tier matches) |
| Restated built-in behaviors | -10 each (max -30) | Telling Claude what it already does |
| Prescriptive formatting rules | -5 each (max -15) | Over-specifying output format |
| Redundant/duplicate instructions | -10 each (max -20) | Same instruction stated multiple ways |
| Instruction conflicts (within-file) | -15 each | Contradictory instructions in same file (cross-file → CLAUDE.md Quality) |
| Permission over-specification | -15 | Dozens of granular rules where a mode suffices |
| Hook sprawl | -10 | Hooks duplicating built-in behavior |
| MCP server sprawl | -10 | Servers configured but rarely/never used |
| Legacy `commands/` dirs | -5 each | Should be migrated to `skills/` |
| Fighting Claude's style | -10 each (max -20) | Contradicts Claude's natural approach |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| Minimal, focused CLAUDE.md | +10 | Under 500 tokens with clear project context |
| Clean permission mode | +5 | Permission mode instead of granular rules |
| No redundant hooks | +5 | All hooks serve unique purposes |

## CLAUDE.md Quality (20%) — includes Rule-Shape

### Deductions (structural)
| Issue | Points | Description |
|---|---|---|
| Missing entirely | -50 | No CLAUDE.md at project level |
| No project context | -15 | Missing what the project is / tech stack |
| No build/test commands | -10 | Missing how to build or test |
| Stale file references | -10 each (max -20) | References to files that don't exist |
| No directory structure | -5 | Missing repo layout |
| Embeds full API docs | -15 | Should reference files, not embed |
| Includes secrets/keys | -30 | Secrets never in CLAUDE.md |
| Individual file > 200 lines | -10 each (max -20) | Per Anthropic docs, instruction files < 200 lines |
| Duplicated instructions across project files | -5 each (max -25) | Same instruction in root ↔ subdirectory or root ↔ rules (project scope only) |
| Conflicting instructions across project files | -15 each | Same-scope contradiction |
| Broken `@import` references | -10 each (max -20) | `@path/to/file` pointing to nonexistent files |
| `@import` depth > 3 levels | -5 | Hard limit is 5; ≤3 preferred for maintainability |
| Circular `@imports` | -15 | Import cycle detected |

### Deductions (Rule-Shape — mechanism fit) ★ `/claude-audit` differentiator
See `claude-md-architecture.md` for the full framework. A rule's **trigger** must match its **mechanism**; the `.claude/rules/` loader supports **paths/extensions only** (no activity triggers).

| Issue | Points | Description |
|---|---|---|
| Activity-bound rule stranded as always-loaded | -12 each (max -36) | A procedure (debug/refactor/removal/test protocol) in CLAUDE.md that should be a **skill** — paid every session, relevant to one activity |
| Path-bound rule stranded as always-loaded | -8 each (max -24) | Rule scoped to one dir (hooks/, plugins/) sitting in root/global CLAUDE.md → belongs in `.claude/rules/` + `paths:` |
| Rule file missing `paths:` frontmatter | -8 each | `.claude/rules/*.md` with no `paths:` loads unconditionally (or never, if it relies on a legacy key) |
| Legacy frontmatter key (`alwaysApply`/`patterns`) | -5 each | Schema field is `paths:`; legacy keys may be inert — verify loader honors them |
| Subtree-specific rule at repo root | -8 each | Package-local convention in root CLAUDE.md → belongs in subdirectory CLAUDE.md |
| `@import` mistaken for token reduction | -5 | Comment/intent suggests import saves context budget — it doesn't (expands at launch) |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| Well-structured sections | +10 | Clear headings, logical flow |
| Links to reference files | +5 | Points to docs instead of embedding |
| Project-specific conventions only | +5 | Doesn't repeat general knowledge |
| Effective `.claude/rules/` usage | +10 | Path-scoped rules with valid `paths:` globs |
| Good file decomposition | +5 | Subdirectory CLAUDE.md scoped to its domain |
| Clean `@import` tree | +5 | All imports valid, no cycles, depth ≤ 3 |
| Activity-bound procedures promoted to skills | +5 each (max +15) | Procedures live in `/skills`, not the always-loaded tier |

## Security Posture (15%)

### Deductions
| Issue | Points | Description |
|---|---|---|
| `full-auto` permission mode | -20 | No guardrails on tool execution |
| Secrets in config files | -30 | API keys, tokens in settings or CLAUDE.md |
| Overly broad `Bash(*)` allow | -15 | Any bash command without review |
| No permission config at all | -10 | Relying entirely on defaults |
| Sensitive paths in allowedTools | -10 | Edit/Write access to system dirs |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| Scoped bash permissions | +10 | Specific `Bash(...)` patterns for project commands |
| Path-scoped file access | +5 | Edit/Write restricted to project dirs |
| Thoughtful deny rules | +5 | Explicit `deniedTools` for dangerous operations |

## MCP Configuration (15%)

### Deductions
| Issue | Points | Description |
|---|---|---|
| Missing binary for server | -20 each | Command not found on PATH |
| Duplicate functionality | -10 | Multiple servers providing same tools |
| Unused servers | -10 each | Configured but tools never invoked |
| No .mcp.json when MCP used | -5 | MCP config in wrong location |
| Server without env isolation | -5 | Missing env vars the server needs |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| All servers healthy | +10 | Every configured server has working binary |
| Minimal tool surface | +5 | Only actively-used servers |

## Plugin Health (15%)

### Deductions
| Issue | Points | Description |
|---|---|---|
| Plugin install path missing | -20 each | Plugin directory doesn't exist |
| Legacy `commands/` structure | -10 | Should use `skills/` |
| Missing plugin.json fields | -5 each | Incomplete plugin metadata |
| Stale plugin versions | -10 | Plugins significantly behind marketplace |
| Disabled but loaded plugins | -10 | Consuming context for no benefit |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| All plugins current | +10 | Versions match or exceed marketplace |
| Clean plugin structure | +5 | Uses current `skills/` + `agents/` patterns |

## Context Efficiency (15%)

### Deductions
| Issue | Points | Description |
|---|---|---|
| Total config > 5000 tokens | -20 | Combined config too heavy (tiers exclusive) |
| Total config > 3000 tokens | -10 | Getting heavy (not applied if >5000 tier matches) |
| Aggregate instruction files > 8000 tokens | -15 | All CLAUDE.md + rules combined very large (tiers exclusive) |
| Aggregate instruction files > 5000 tokens | -10 | Getting heavy (not applied if >8000 tier matches) |
| Redundant memory entries | -10 | MEMORY.md duplicating CLAUDE.md |
| Large hook output | -10 | Hooks producing verbose context |
| Unused skill/agent definitions | -5 each | Loaded but never triggered |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| Lean total config | +10 | Under 1500 tokens total |
| Effective memory usage | +5 | MEMORY.md complements (not duplicates) CLAUDE.md |
| Minimal loaded context | +5 | Only what's needed is loaded |
| On-demand-only subdirectory files | +5 | Good architecture — subdirectory files load only when needed |

## Memory (5%)

**Philosophy:** `MEMORY.md` is an always-loaded index with a 200-line / ~24KB ceiling; value lives in topic files. Bloat, dead links, and prose-as-index waste tokens every session and rot recall. Memory is personal and long-term — destructive actions default to **archive**, never delete. Full procedure and self-reflection prompts: Phase 2.5 of `SKILL.md`.

### Deductions
| Issue | Points | Description |
|---|---|---|
| No MEMORY.md when memory dir exists | -10 | Topic files with no index → unreachable |
| Index > 200 lines / > 24KB | -15 | Over ceiling — always-loaded cost exceeds budget |
| Broken topic-file link (resolves to nothing) | -5 each (max -25) | Dead retrieval key — liveness check fail |
| Entry cites file/symbol/skill that no longer exists | -5 each (max -20) | Provenance decay — teaches a wrong lesson |
| Entry re-derivable from CLAUDE.md / git / docs | -5 each (max -20) | Restates cheaper authoritative source → drop |
| Duplicate/clustered entries (same root cause) | -5 per cluster | Redundancy — merge into one topic file |
| Index line > 150 chars or multi-sentence | -2 each (max -15) | Prose masquerading as retrieval key → shorten |
| Topic file body < 5 lines | -3 each (max -12) | Index carries more than file → fold + drop |
| Free-prose lines consuming the 200-line budget | -2 each (max -10) | Non-index lines in the always-loaded tier |

### Bonuses
| Optimization | Points | Description |
|---|---|---|
| Lean, all-retrieval-key index | +5 | Every line is `Title — one-line hook`, ≤150 chars |
| Every entry passes liveness + derivability | +3 | No dead links, no restated CLAUDE.md rules |
| Archived (not deleted) stale entries | +2 | Destructive actions stayed reversible |

## Scope-aware scoring

- **Global only** (no project): exclude CLAUDE.md Quality; renormalize remaining weights proportionally. Note "CLAUDE.md Quality: skipped (no project)."
- **No MEMORY.md / memory dir**: exclude Memory; note "Memory: not configured." Renormalize proportionally.
- **Comprehensive**: score all 7 categories.

## Recommendation Ranking

| Priority | Impact | Action |
|---|---|---|
| Critical | > 20 pts | Must fix — actively harming |
| High | 10-20 pts | Should fix — significant gain |
| Medium | 5-9 pts | Nice to have |
| Low | < 5 pts | Optional polish |

Include both **Issues to fix** and **Features to adopt** (capabilities the user isn't using yet).

## Decision Fingerprinting

Each deduction maps to a slug: `{category_slug}:{issue_type}:{file_stem}:{content_hash_8}`. Rule-Shape additions use these issue-type slugs:
- `rule-shape:activity-stranded` — activity-bound rule stranded as always-loaded
- `rule-shape:path-stranded` — path-bound rule stranded as always-loaded
- `rule-shape:missing-paths` — rule file missing `paths:` frontmatter
- `rule-shape:legacy-frontmatter` — legacy `alwaysApply`/`patterns` key
- `rule-shape:subtree-at-root` — subtree-specific rule at repo root
- `rule-shape:import-misconception` — `@import` treated as token reduction

All other category → slug mappings follow claudit's original issue-type table (over-engineering, claudemd-quality, security, mcp-config, plugin-health, context-efficiency). Memory slugs:
- `memory:dead-link` — topic-file link resolves to nothing
- `memory:provenance-decay` — cited file/symbol/skill no longer exists
- `memory:derivable` — re-derivable from CLAUDE.md / git / docs
- `memory:redundant-cluster` — clustered with another entry (same root cause)
- `memory:prose-index` — index line is prose, not a retrieval key
- `memory:thin-topic` — topic body shorter than its index line
- `memory:budget-prose` — non-index lines consuming the 200-line budget
