---
name: trace
description: Manual trace-through verification for code, skills, workflows, and documents - catch logic errors that automated testing misses
version: 1.0.43
status: stable
category: verification
triggers:
  - /trace
  - /trace code:<file-path>
  - /trace skill:<skill-name>
  - /trace workflow:<workflow-path>
  - /trace document:<document-path>
aliases:
  - /trace
  - /trace code:src/handoff.py
  - /trace skill:skill-development
  - /trace workflow:flows/feature.md
  - /trace document:CLAUDE.md
suggest:
  - /code (Phase 3.5 delegates to /trace)
  - /refactor (uses /trace for verification)
  - /q (strategic quality check)
  - /av (skill analysis)

do_not:
  - skip reading the target file before tracing
  - create trace tables without reading the code
  - claim findings without line numbers and evidence
  - trace without checking all three scenarios (happy, error, edge)
---

# /trace - Manual Trace-Through Verification

## Purpose

Manual trace-through verification to catch logic errors that automated testing misses. Based on industry best practices:
- **Dry running / desk checking**: 60-80% effectiveness for logic errors
- **Fagan Inspection**: Systematic code inspection methodology
- **Manual code review**: Step-by-step verification of execution paths

**When to use:**
- Code review after tests pass (verification gap)
- Resource management verification (file descriptors, locks, connections)
- Skill intent detection logic review
- Workflow step dependency verification
- Document consistency checks

## Project Context

### Constitution / Constraints
- **Solo-dev constraints apply** (CLAUDE.md)
- **Evidence-based**: All findings must cite line numbers
- **Three scenarios minimum**: Happy path, error path, edge case
- **No fabrication**: Read actual code before creating trace tables

### Technical Context
- **Core methodology**: State table tracking at each step
- **Domain adapters**: Code, skills, workflows, documents
- **Trace tables**: Structured format for variable/state tracking
- **Effectiveness**: 60-80% detection rate for logic errors (vs 0% for testing)
- **Integration**: /code skill Phase 3.5 delegates to `/trace code:<file>`

### Architecture Alignment
- Independent skill with domain adapters
- /code skill delegates TRACE phase to `/trace code:<file>`
- Can be invoked standalone or by other skills (/refactor, /av, /q)
- Extensible: New domain adapters added without core changes

## Modes

`/trace` operates in 4 domain modes:

| Mode | Description | When to Use |
|------|-------------|-------------|
| **code** | Resource management, exception paths, race conditions | File I/O, locking, concurrency |
| **skill** | Intent detection, tool selection, fallback logic | Skill development, /av analysis |
| **workflow** | Step dependencies, error handling, rollback | Flow verification, orchestration review |
| **document** | Consistency, completeness, cross-references | Doc review, CLAUDE.md verification |

## Visualization Features

TRACE reports include automatic visualization generation: Mermaid flowcharts, call graph recommendations (pyan), program slicing recommendations, and pre-built templates.

See `references/visualization-features.md` for full details on all 4 visualization types and usage instructions.

## debugRCA Integration

TRACE integrates with debugRCA for enhanced root cause analysis: evidence saturation detection, red flag detection, ACH scenario generation, timeline visualization, call graph hypothesis generation, CKS findings persistence, and differential TRACE.

See `references/debugrca-integration.md` for all 7 integration features with code examples and benefits table.

## Your Workflow

### Step 1: Parse Target

Extract domain and target from invocation:
```bash
/trace code:src/handoff.py        -> domain=code, target=src/handoff.py
/trace skill:skill-development     -> domain=skill, target=skill-development
/trace workflow:flows/feature.md   -> domain=workflow, target=flows/feature.md
/trace document:CLAUDE.md          -> domain=document, target=CLAUDE.md
```

**Default invocation** (no domain specified):
- If target is `.py` file -> `code` domain
- If target is `SKILL.md` -> `skill` domain
- If target is in `flows/` -> `workflow` domain
- Otherwise -> `document` domain

### Step 2: Select Domain Adapter

```python
ADAPTERS = {
    'code': CodeTracer,
    'skill': SkillTracer,      # Future: Extension point
    'workflow': WorkflowTracer, # Future: Extension point
    'document': DocumentTracer, # Future: Extension point
}
```

### Step 3: Load Target File

**CRITICAL**: Read the target file before creating trace tables.

### Step 4: Define Scenarios

For each target, define 3 scenarios:
1. **Happy path**: Normal operation
2. **Error path**: Exception/failure handling
3. **Edge case**: Boundary condition, timeout, empty input

### Step 5: Create State Table

```markdown
| Step | Operation | State/Variables | Resources | Notes |
|------|-----------|-----------------|-----------|-------|
| 1 | Initial state | var1=None, var2=[] | fd=None | Setup |
| 2 | Open file | var1=<fileobj> | fd=3 | File opened |
| 3 | Process data | var1=<data>, var2=[1,2,3] | fd=3 | Data processed |
| 4 | Close file | var1=None | fd=None | Cleanup |
```

### Step 6: Trace Each Scenario

Step through the code/content line-by-line:
- Record state changes at each step
- Track resource acquisition/release
- Check cleanup in all paths (especially exception paths)
- Document any logic errors found

### Step 7: Document Findings

See `references/workflow-and-report-format.md` for the full TRACE report template with executive summary, findings format, and results structure.

## Validation Rules

- **Before tracing**: Read the target file completely
- **During tracing**: Cite line numbers for all findings
- **After tracing**: Verify all three scenarios traced
- **No fabrication**: Only report what you actually see in the code

## Execution Directive

For `/trace` requests, execute this workflow:

```bash
cd P://.claude/skills/trace && python __main__.py "domain:target"

# Examples
python __main__.py "code:src/handoff.py"
python __main__.py "skill:skill-development"
python __main__.py "workflow:flows/feature.md"
python __main__.py "document:CLAUDE.md"
```

## Domain-Specific Behavior

Each domain has specific focus areas, trace table columns, checklists, and example invocations.

See `references/domain-adapters.md` for detailed checklists and trace table formats for all 4 domains (code, skill, workflow, document).

## Integration with /code Skill

The `/code` skill Phase 3.5 (TRACE) delegates to `/trace code:<file>`. The delegation pattern and references to TRACE methodology, templates, and checklists are documented in `references/integrations-and-usage.md`.

## Usage

```bash
# Code TRACE (fully implemented)
/trace code:src/handoff.py                    # Manual code trace-through
/trace code:src/handoff.py --template 2      # Use specific template
/trace code:src/handoff.py --no-tot           # Disable ToT enhancement

# Skill / Workflow / Document TRACE (extension points - future)
/trace skill:skill-development                # Intent detection review
/trace workflow:flows/feature.md              # Dependency verification
/trace document:CLAUDE.md                     # Consistency check

# Auto-detect domain (default behavior)
/trace src/handoff.py                         # Detects: code
/trace SKILL.md                                # Detects: skill
/trace flows/feature.md                       # Detects: workflow
```

## Files

- `SKILL.md` - Skill definition (this file)
- `__main__.py` - Entry point with CLI argument parsing
- `scripts/scripts/core/tracer.py` - Core TRACE methodology
- `scripts/core/state_table.py` - State table creation
- `adapters/code_tracer.py` - Code TRACE adapter (implemented)
- `adapters/skill_tracer.py` - Skill TRACE adapter (extension point)
- `adapters/workflow_tracer.py` - Workflow TRACE adapter (extension point)
- `adapters/document_tracer.py` - Document TRACE adapter (extension point)
- `templates/TRACE_METHODOLOGY.md` - Domain-agnostic TRACE guide
- `templates/code/TRACE_TEMPLATES.md` - Code TRACE templates (5 templates)
- `templates/code/TRACE_CHECKLIST.md` - Code TRACE checklist (100+ checks)
- `templates/code/TRACE_CASE_STUDIES.md` - Real-world bug examples

### Reference Files

| File | Contents |
|------|----------|
| `references/visualization-features.md` | Mermaid flowcharts, call graphs, program slicing, templates |
| `references/debugrca-integration.md` | 7 debugRCA integration features with code examples |
| `references/domain-adapters.md` | Domain-specific checklists and trace table formats |
| `references/workflow-and-report-format.md` | Workflow steps, state tables, TRACE report template |
| `references/integrations-and-usage.md` | /code integration, CLI examples, version history |

## Phase Gates

**GATE 1 (STOP after Step 3: Load Target File)**: Before moving to Step 4 (Define Scenarios), verify:
- Target file read completely
- No fabrication — only report what was actually read
- Line numbers available for all findings

If gate fails: re-read the file completely before creating trace tables.

**GATE 2 (STOP after Step 4: Define Scenarios)**: Before moving to Step 5 (Create State Table), verify:
- Three scenarios defined: happy path, error path, edge case
- Each scenario is distinct and complete
- Boundary conditions identified

If gate fails: define all three scenarios before proceeding.

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

**GATE 3 (STOP after Step 6: Trace Each Scenario)**: Before moving to Step 7 (Document Findings), verify:
- All three scenarios traced
- Cleanup verified in all paths
- Line numbers cited for all findings
- No logic errors skipped

If gate fails: complete trace through all scenarios before documenting.

**STOP between generation (Steps 1-3) and validation (Steps 4-6)**:
- Steps 1-3: Parse target, select adapter, load file (generation)
- Steps 4-6: Define scenarios, create state table, trace execution (validation)
- Do NOT proceed to Step 4 until file is fully read in Step 3

---

## Success Criteria

- Code TRACE works (all 5 templates functional)
- TRACE reports generated with findings
- Line numbers cited for all issues
- Three scenarios traced (happy, error, edge)
- Integration with /code skill Phase 3.5
- Skill / Workflow / Document TRACE adapters (future extension)
