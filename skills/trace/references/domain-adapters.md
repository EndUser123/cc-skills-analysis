# Domain-Specific TRACE Behavior

## Code TRACE (Domain: `code`)

**Focus**: Resource management, exception paths, race conditions

**Templates**:
- File I/O with locking
- File descriptor management
- Concurrent access (TOCTOU races)
- Exception handling with cleanup
- Lock acquisition with timeout

**Checklist**:
- [ ] File descriptors opened -> closed (all paths)
- [ ] Locks acquired -> released (even if acquisition fails)
- [ ] Exception paths don't leak resources
- [ ] No TOCTOU races (atomic operations preferred)
- [ ] Cleanup in finally blocks

**Examples**:
- `/trace code:src/handoff/hooks/__lib/handoff_store.py`
- `/trace code:src/handoff/hooks/SessionStart_handoff_restore.py`

## Skill TRACE (Domain: `skill`) - Future Extension

**Focus**: Intent detection logic, tool selection, fallback scenarios

**Trace table columns**:
| Step | User Input | Matched Intent | Tools Selected | Fallback? | Notes |
|------|------------|----------------|----------------|-----------|-------|

**Checklist**:
- [ ] All common intents have patterns
- [ ] Unmatched input has fallback
- [ ] Tool selection is deterministic
- [ ] Error handling in tool calls
- [ ] No infinite loops in retry logic

**Examples**:
- `/trace skill:skill-development`
- `/trace skill:code`

## Workflow TRACE (Domain: `workflow`) - Future Extension

**Focus**: Step dependencies, error handling, rollback paths

**Trace table columns**:
| Step | Operation | Dependencies | State Changes | Error Path | Notes |
|------|-----------|--------------|---------------|------------|-------|

**Checklist**:
- [ ] Steps execute in correct order
- [ ] Dependencies satisfied before execution
- [ ] Error handling in each step
- [ ] Rollback paths for failures
- [ ] No circular dependencies

**Examples**:
- `/trace workflow:flows/feature.md`
- `/trace workflow:cwo/CWO.md`

## Document TRACE (Domain: `document`) - Future Extension

**Focus**: Consistency, completeness, cross-references

**Trace table columns**:
| Section | Claim | Evidence | Cross-refs | Consistent? | Notes |
|---------|-------|----------|------------|-------------|-------|

**Checklist**:
- [ ] No contradictory statements
- [ ] All cross-references resolve
- [ ] Examples match descriptions
- [ ] No orphan sections (unreferenced)
- [ ] Metadata consistent with content

**Examples**:
- `/trace document:CLAUDE.md`
- `/trace document:README.md`
