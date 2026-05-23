# TRACE Methodology - Domain-Agnostic Guide

Core TRACE methodology for manual trace-through verification. Applies to all domains: code, skills, workflows, and documents.

## What Is TRACE?

**TRACE** = Manual trace-through verification to catch logic errors that automated testing misses.

Based on industry best practices:
- **Dry running / desk checking**: 60-80% effectiveness for logic errors
- **Fagan Inspection**: Systematic code inspection methodology (IBM, 1976)
- **Manual code review**: Step-by-step verification of execution paths

### Why TRACE?

Automated testing verifies **behavior** (what the code does).
TRACE verifies **correctness** (how the code does it).

**The verification gap**: Tests can pass while code has bugs.

**Example**:
```python
# Tests pass ✅ (lock file doesn't exist when test runs)
def acquire_lock(lock_path):
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    return True
    finally:
        lock_path.unlink()  # ✗ BUG: Deletes lock even if we didn't acquire it
```

Tests pass because they run sequentially. TRACE reveals the bug by tracing the timeout scenario.

---

## Core TRACE Methodology

### Step 1: Define Scope

Identify the artifact to trace and scenarios to verify:

| Artifact | What to Trace |
|----------|---------------|
| **Code** | Functions with resource management (file I/O, locks, connections) |
| **Skills** | Intent detection logic, tool selection, fallback scenarios |
| **Workflows** | Step dependencies, error handling, rollback paths |
| **Documents** | Consistency, completeness, cross-references |

### Step 2: Define Scenarios

For each artifact, trace **3 scenarios minimum**:

1. **Happy Path**: Normal operation
2. **Error Path**: Exception/failure handling
3. **Edge Case**: Boundary condition, timeout, empty input

### Step 3: Create State Table

Track state at each step:

```
| Step | Operation | State/Variables | Resources | Notes |
|------|-----------|-----------------|-----------|-------|
| 1 | Initial state | var1=None, var2=[] | fd=None | ✓ Setup |
| 2 | Acquire resource | var1=<obj> | fd=3 | Resource acquired |
| 3 | Process data | var1=<data>, var2=[1,2,3] | fd=3 | Data processed |
| 4 | Release resource | var1=None | fd=None | ✓ Cleanup |
```

**Columns**:
- **Step**: Sequential operation number
- **Operation**: What happens (function call, state transition, etc.)
- **State/Variables**: Variable values after operation
- **Resources**: Resource state (file descriptors, locks, connections)
- **Notes**: Observations (✓ correct, ✗ bug, ⚠️ warning)

### Step 4: Trace Each Scenario

Step through the artifact line-by-line:
- Record state changes at each step
- Track resource acquisition/release
- Check cleanup in all paths (especially exception paths)
- Document any logic errors found

**Key questions**:
- What happens if this operation fails?
- Are resources cleaned up in all paths?
- Can this state cause problems later?
- Is there a race condition here?

### Step 4.5: Integration Verification (MANDATORY for Hook Code)

**CRITICAL**: Function-level TRACE misses bugs in orchestration logic. Before claiming DONE on hook code or multi-module systems:

1. **Cross-Module Contract Check**
   - List all exported schemas/types from dependency modules
   - Verify each schema is handled in consuming modules
   - Verify no silent fall-through to `return None`

2. **Main() Execution Path TRACE**
   - Trace the actual entry point (`main()`, `run()`, etc.)
   - Follow real flow through function calls
   - Verify cleanup runs in ALL exit paths
   - Simulate 10 consecutive runs → check for state accumulation

3. **Integration Test** (Run actual code, not just analysis)
   - Create synthetic input (temp files, mock stdin)
   - Run actual `main()` with synthetic input
   - Verify file system side effects (created/deleted)
   - Verify no state accumulation across runs

**Why this matters**: Unit tests pass ✅ but integration fails ❌.

**Example bug caught**: `PostToolUse_artifact_validator.py`
- Function-level TRACE: All functions look correct
- Integration test: Artifact never deleted, infinite injection loop
- Root cause: `sys.exit(0)` on line 138 skips cleanup on line 143

**When to skip**: Single-function modules with no external dependencies. Everything else requires integration verification.

### Step 5: Document Findings

Create TRACE report with:

```markdown
## TRACE Report: <domain>:<target>

**Date**: YYYY-MM-DD
**Scenarios traced**: 3 (happy, error, edge)

### Findings Summary
- **Logic Errors Found**: N
- **Resource Leaks Found**: N
- **Race Conditions Found**: N
- **Inconsistencies Found**: N

### Issues Found

#### Issue #1: P0 - [Category]
- **Location**: Line X-Y (or section reference)
- **Problem**: [What's wrong]
- **Impact**: [Why it matters]
- **Recommendation**: [How to fix]

### TRACE Results
✅ PASS / ❌ FAIL
- [Summary of verification]
```

---

## Domain-Specific Adaptations

### Code TRACE

**Focus**: Resource management, exception paths, race conditions

**State table columns**:
| Line | Operation | var1 | var2 | fd | lock_file | Notes |
|------|-----------|------|------|-----|-----------|-------|

**Common bugs**:
- File descriptor consumed by fdopen(), then reused
- Finally block deletes another process's lock
- TOCTOU race (check-then-act pattern)
- Resource leak in exception path

**Templates**: See `templates/code/TRACE_TEMPLATES.md` (5 templates)
**Checklist**: See `templates/code/TRACE_CHECKLIST.md` (100+ checks)

### Skill TRACE

**Focus**: Intent detection logic, tool selection, fallback scenarios

**State table columns**:
| Step | User Input | Matched Intent | Tools Selected | Fallback? | Notes |
|------|------------|----------------|----------------|-----------|-------|

**Common bugs**:
- Unmatched intent has no fallback
- Tool selection not deterministic
- Error handling missing in tool calls
- Infinite loops in retry logic

**Extension point**: `adapters/skill_tracer.py` (future)

### Workflow TRACE

**Focus**: Step dependencies, error handling, rollback paths

**State table columns**:
| Step | Operation | Dependencies | State Changes | Error Path | Notes |
|------|-----------|--------------|---------------|------------|-------|

**Common bugs**:
- Circular dependencies
- Missing rollback path
- Error handling in step causes cascade failure
- Steps execute in wrong order

**Extension point**: `adapters/workflow_tracer.py` (future)

### Document TRACE

**Focus**: Consistency, completeness, cross-references

**State table columns**:
| Section | Claim | Evidence | Cross-refs | Consistent? | Notes |
|---------|-------|----------|------------|-------------|-------|

**Common bugs**:
- Contradictory statements
- Broken cross-references
- Examples don't match descriptions
- Orphan sections (unreferenced)

**Extension point**: `adapters/document_tracer.py` (future)

---

## TRACE Checklist

### Before Starting

- [ ] Read target file completely
- [ ] Identify 3 scenarios (happy, error, edge)
- [ ] Understand expected behavior

### During TRACE

- [ ] Create state table for each scenario
- [ ] Track state changes at each step
- [ ] Check cleanup in all exception paths
- [ ] Document findings with line numbers

### After TRACE

- [ ] All three scenarios traced
- [ ] All findings cite line numbers
- [ ] Report generated with summary
- [ ] Recommendations provided for all issues

---

## TRACE Effectiveness

### Bug Detection Rates

| Method | Detection Rate | Time Cost |
|--------|----------------|------------|
| Testing | 30-50% | Low |
| Static Analysis | 20-40% | Very Low |
| Code Review | 40-60% | Medium |
| **TRACE** | **60-80%** | **Medium** |
| **Combined** | **85-95%** | **Medium** |

### ROI Analysis

**Handoff system case study**:
- **TRACE time**: 75 minutes (3 files)
- **Bugs found**: 2 P0 critical bugs
- **Incidents prevented**: 5-10 per month
- **Time saved**: 15-30 hours per month
- **ROI**: 12x return on time invested

---

## Quick Reference

### Top 10 TRACE Bugs

1. Lock cleanup race (finally deletes another process's lock)
2. File descriptor reuse (fd consumed, then reused)
3. TOCTOU race (check-then-act pattern)
4. Resource leak in exception path
5. Early return skips cleanup
6. Variable used after free/close
7. Missing exception handling (bare except)
8. Silent failure (exception caught, not logged)
9. Stale data used (fallback to outdated cache)
10. Infinite loop (missing termination)

### TRACE Command Reference

```bash
# Code TRACE
/trace code:src/handoff.py

# Skill TRACE (future)
/trace skill:skill-development

# Workflow TRACE (future)
/trace workflow:flows/feature.md

# Document TRACE (future)
/trace document:CLAUDE.md

# Auto-detect domain
/trace src/handoff.py  # Detects: code
```

### TRACE Modes

**Standard Mode** (default):
```bash
/trace code:src/handoff.py
# Pattern-matching TRACE for common bugs
# 3 scenarios: happy, error, edge
# Focus: Resource management, exception paths, race conditions
```

**Deep Mode** (`--mode deep`):
```bash
/trace code:src/handoff.py --mode deep
# Hypothesis-driven TRACE for complex issues
# 4-phase analysis with ACH scenario generation
# Focus: Intent vs reality gaps, integration failures, systemic issues
```

#### When to Use Deep Mode

Use `--mode deep` for:
- **Integration failures**: Hook not firing, cross-module errors
- **Systemic issues**: Problems that don't map to single code location
- **Root cause analysis**: After incidents to understand why they happened
- **Architecture review**: Verifying design intent matches implementation
- **Unknown unknowns**: When standard TRACE doesn't reveal the issue

#### Deep Mode: 4-Phase Analysis

**Phase 1: Intent vs Reality**
- What was supposed to happen? (Design intent, documentation, specs)
- What actually happened? (Observed behavior, logs, error messages)
- Gap analysis: Where does intent diverge from reality?

**Phase 2: Component Mapping**
- Which components are involved? (Modules, hooks, services, data flows)
- How do they interact? (Call graphs, event flows, dependencies)
- What are the integration points? (APIs, events, shared state)

**Phase 3: Hypothesis Generation (ACH Framework)**
Generate competing hypotheses across 6 categories:
- **Logic**: Control flow, algorithm errors, logic bugs
- **Data**: Data corruption, type mismatches, format issues
- **State**: State machine errors, lifecycle issues, stale state
- **Integration**: API mismatches, protocol errors, boundary failures
- **Resource**: Memory leaks, resource exhaustion, race conditions
- **Environment**: Configuration errors, dependency issues, platform-specific

**Phase 4: Verification Planning**
For each hypothesis:
- **Confirmation test**: What would prove this theory?
- **Refutation test**: What would disprove this theory?
- **Confidence assessment**: How likely is this hypothesis?
- **Action priority**: Which hypothesis to investigate first?

#### Deep Mode Output Structure

```markdown
## Deep TRACE Report: code:src/handoff.py

### Phase 1: Intent vs Reality Gap
**Intent**: Hook should validate all tool uses before execution
**Reality**: Hook never fires when tools are used
**Gap**: Hook registration failure or event timing mismatch

### Phase 2: Component Mapping
**Components Involved**:
- `.claude/hooks/PreToolUse_validator.py` (hook file)
- `PreToolUse` event system (event dispatcher)
- Tool execution pipeline (target system)

**Integration Points**:
- Hook registration: settings.json → hook loader
- Event dispatch: tool use → PreToolUse event
- Hook execution: event dispatcher → hook function

### Phase 3: ACH Hypotheses

#### H1: Logic - Registration Pattern Mismatch (Confidence: High)
- **Theory**: Hook filename doesn't match expected pattern
- **Evidence**: File is `validator.py` instead of `PreToolUse_validator.py`
- **Confirmation Test**: Rename file to match pattern, restart Claude Code
- **Refutation Test**: Verify hook fires after rename

#### H2: Data - Event Data Structure Mismatch (Confidence: Medium)
- **Theory**: Hook expects different event data structure
- **Evidence**: Hook uses `event.tool_name` but event uses `event_data['tool_name']`
- **Confirmation Test**: Log event_data structure, compare with hook expectations
- **Refutation Test**: Hook correctly accesses event data fields

#### H3: State - Hook Registration Not Persisted (Confidence: Low)
- **Theory**: Hook registered in memory but not saved to settings.json
- **Evidence**: Hook appears in running session but missing after restart
- **Confirmation Test**: Check settings.json for hook entry
- **Refutation Test**: Hook present in settings.json with correct config

### Phase 4: Verification Plan

**Priority 1**: Test H1 (Registration Pattern)
- Rename file to `PreToolUse_validator.py`
- Restart Claude Code
- Trigger tool use, verify hook fires
- **Expected**: Hook executes before tool
- **Time**: 5 minutes

**Priority 2**: Test H2 (Event Data Structure)
- Add debug logging to print event_data structure
- Trigger tool use, inspect logs
- Compare actual vs expected structure
- **Expected**: Identify field name mismatch
- **Time**: 10 minutes

**Priority 3**: Test H3 (State Persistence)
- Check settings.json for hook entry
- Restart Claude Code
- Verify hook loads on startup
- **Expected**: Hook registration persists
- **Time**: 5 minutes
```

#### Standard Mode vs Deep Mode

| Aspect | Standard Mode | Deep Mode |
|--------|--------------|-----------|
| **Focus** | File-scoped bugs | Codebase-scoped systemic issues |
| **Method** | Pattern matching | Hypothesis-driven investigation |
| **Scenarios** | 3 fixed (happy, error, edge) | ACH-based (6 categories × N hypotheses) |
| **Output** | Issues with line numbers | Hypotheses with verification plans |
| **Duration** | 5-15 minutes | 30-60 minutes |
| **Best for** | Known bug patterns, resource leaks | Unknown issues, integration failures |

---

## Visualization Support

TRACE includes automatic visualization generation to enhance understanding:

### Mermaid Flowcharts (Auto-Generated)
State tables automatically converted to Mermaid flowcharts with color coding:
- **Green**: Pass/correct operations
- **Red**: Fail/errors/bugs
- **Yellow**: Warnings
- **Blue**: Neutral/initial state

### Call Graph Recommendations (Code Domain)
For code TRACE, reports include recommendations to generate call graphs using:
- **pyan**: Python call graph analyzer
- **pygraphviz**: Graph visualization library
- **Graphviz**: DOT file rendering to PNG

### Program Slicing Recommendations
When circular dependencies detected, reports recommend:
- **pycg**: Call graph generation for dependency analysis
- Focused analysis of affected code paths

### Visualization Templates
Pre-built Mermaid templates for common patterns:
- File descriptor lifecycle
- Lock acquisition with timeout
- TOCTOU race conditions
- Exception handling with cleanup
- Workflow step dependencies
- Intent detection flows
- Document consistency checks

**Location**: `templates/TRACE_VISUALIZATION_TEMPLATES.md`

---

## See Also

- **Visualization Templates**: `templates/TRACE_VISUALIZATION_TEMPLATES.md`
- **Code TRACE Templates**: `templates/code/TRACE_TEMPLATES.md`
- **Code TRACE Checklist**: `templates/code/TRACE_CHECKLIST.md`
- **Code TRACE Case Studies**: `templates/code/TRACE_CASE_STUDIES.md`
- **Implementation Summary**: `P://.claude/skills/code/references/TRACE_IMPLEMENTATION.md`
