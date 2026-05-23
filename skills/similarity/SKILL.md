---
name: similarity
description: "Find skills similar to a target skill based on keywords, dependencies, and metadata"
version: "1.0.0"
status: stable
category: analysis
enforcement: advisory
triggers:
  - /similarity
  - "similar skills"
  - "find similar"
aliases:
  - /similarity
suggest:
  - /search
  - /skill-ship

suggest:
  - /search
  - /analyze
  - /adversarial-review
  - /skill-complete
  - /skill-ship

depends_on_skills: []
---

# /similarity - Find Similar Skills

## Purpose

Find skills in the codebase that are similar to a target skill based on semantic analysis of keywords, dependencies, category, and content.

**Use case:** "What skills do similar things to X?" or "What skills might be redundant with Y?"

## How It Works

This is a PROCEDURE-type skill — it runs a Python script that:
1. Scans all skills in the skills directory
2. Parses the target skill to extract keywords
3. Compares all skills against the target using multiple factors
4. Groups results by similarity tier (HIGH/MEDIUM/LOW/MINIMAL)
5. Exports a JSON report with full similarity data

## Usage

```
/similarity <target>           # Find skills similar to <target>
/similarity /evolve            # Find skills similar to /evolve
/similarity /tdd               # Find skills similar to /tdd
/similarity                    # Infer from context
```

## Output

The skill outputs:
1. **Console summary** - Grouped by similarity tier (HIGH/MEDIUM/LOW/MINIMAL)
2. **JSON report** - Full similarity data exported to `~/.claude/.artifacts/{terminal_id}/similarity/<target>_report.json`

Each result shows:
- Skill name and similarity score
- Description snippet
- Matched keywords
- Dependencies

## Scoring Algorithm

| Factor | Score |
|--------|-------|
| Direct delegate (known similar skill) | +1.0 |
| Same category | +0.5 |
| Keyword match in description | +0.1 per keyword |
| Keyword match in content | +0.05 per keyword |
| Shared dependency | +0.2 |
| Shared suggestion | +0.15 |
| Maximum possible | 1.0 (capped) |

## Your Workflow

When `/similarity` is invoked with a target:

### Step 1: Run Similarity Analysis

```bash
# Run the similarity script
python P://.claude/skills/similarity/similarity.py <target>
```

### Step 2: Format Results for User

After running the script, present results in this EXACT format using a code block:

```
## Similarity Analysis for `/<target>`

**Target:** [description of target skill]

HIGH (0.5+)
  /p0          1.00  Description...
  /p2          1.00  Description...
  /tdd         0.97  Description...

MEDIUM (0.2-0.49)
  /refactor    0.45  Description...
  /v           0.45  Description...

LOW (0.05-0.19)
  /security    0.19  Description...
  /discover    0.19  Description...
```

- Use code block (fenced with ```) for consistent rendering
- Group by tier with headers
- Format: `/skill` (indent) `score` `description...`
- Align scores at column 20
- Align descriptions at column 28
- Truncate descriptions to 60 chars
- Skip MINIMAL (<0.05) entirely

### Step 3: Check JSON Report (Optional)

```bash
# View full report
cat ~/.claude/.artifacts/{terminal_id}/similarity/<target>_report.json
```

## Phase Gates

**GATE 1 (STOP after Step 1: Run Similarity Analysis)**: Before moving to Step 2 (Format Results), verify:
- Python script executed successfully
- JSON report generated at expected path
- At least one similar skill found (or explicitly none)

If gate fails: re-run similarity script before formatting results.

**STOP between generation (Step 1) and validation (Step 2)**:
- Step 1 runs the similarity algorithm (generation)
- Step 2 formats results for user presentation (validation)
- Do NOT skip Step 1 or modify results before the gate check

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

---

## What This Does NOT Do

- Does NOT modify any skills
- Does NOT delete or deprecate skills
- Does NOT make automated decisions about redundancy
- Use `/adversarial-review` for deeper redundancy analysis
