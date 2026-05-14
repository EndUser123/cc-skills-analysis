# TRACE Workflow Steps and Report Format

## Workflow Steps

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

```python
target_path = resolve_target_path(target, domain)
content = read_file(target_path)
```

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

## TRACE Report Format

### Executive Summary
```markdown
## TRACE Report: code:src/handoff.py

**Date**: 2026-02-28
**Scenarios traced**: 3 (happy, error, edge)
**Lines analyzed**: 45-230

### Summary
- Logic Errors: 0
- Resource Leaks: 0
- Race Conditions: 0
- Code Quality: 2 (P2)
```

### Findings
```markdown
### Issues Found

#### Issue #1: P2 - Code Quality
- **Location**: Lines 120-135
- **Problem**: Function too long (16 lines), extracts validation logic
- **Impact**: Reduced readability, harder to test
- **Recommendation**: Extract validation to separate function
```

### Full Report Template
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
- **Location**: Line X-Y
- **Problem**: [What's wrong]
- **Impact**: [Why it matters]
- **Recommendation**: [How to fix]

### TRACE Results
PASS / FAIL
- [Summary of verification]
```
