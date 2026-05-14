# TRACE Phase Checklist

Comprehensive checklist for manual code trace-through, organized by category and severity. Based on industry best practices from Fagan Inspections, dry running techniques, and code review standards.

## How to Use This Checklist

1. **Before TRACE**: Run static analysis tools to catch obvious issues
2. **For each modified file**: Read through completely
3. **For each function**: Identify 3 scenarios (happy path, error path, edge case)
4. **Trace each scenario**: Use TRACE tables from TRACE_TEMPLATES.md
5. **Check applicable items** from this checklist
6. **Document findings**: Log any issues found

---

## 0. Integration Verification (P0 - Critical)

**MANDATORY for hook code and multi-module systems** - This catches bugs that unit tests and function-level TRACE miss.

### Cross-Module Contract Verification
- [ ] **List all exported schemas/types** from dependency modules
- [ ] **Verify each schema is handled** in consuming modules
- [ ] **Verify no silent fall-through** to `return None` for unhandled types
- [ ] **Verify all fields used** - no exported fields ignored

**Common Bugs**:
- Module A exports `SchemaB` but Module B only handles `SchemaA`
- Function returns `None` for unhandled cases (silent failure)
- Field from dependency is never used in consumer

**Detection**: Read both modules, list exports, verify each is consumed

**For the GAV bug**: `artifact_grounder.py` exported `git_safety_block`, `PostToolUse_artifact_validator.py` only handled `blocked_command`, fell through to `None`.

### Main() Execution Path TRACE
- [ ] **Trace actual entry point** - not just helper functions
- [ ] **Follow real flow**: `main()` → calls helpers → actual execution
- [ ] **Verify cleanup runs** in ALL exit paths (early returns, sys.exit)
- [ ] **Verify no skipped cleanup** due to early returns
- [ ] **Simulate 10 consecutive runs** - check for state accumulation

**Common Bugs**:
- Early `sys.exit(0)` skips cleanup on line 50
- Cleanup only runs in "no artifact" path, not "artifact exists" path
- State accumulates across multiple runs

**Detection**: Create state table for `main()` execution, mark cleanup points

**For the GAV bug**: `main()` line 137 prints injection, line 138 `sys.exit(0)` skips cleanup at line 143.

### Integration Test (MANDATORY before claiming DONE on hooks)
- [ ] **Run actual main()** with synthetic input
- [ ] **Verify file system side effects** - files created/deleted as expected
- [ ] **Verify no state accumulation** - run 10x, check for orphans
- [ ] **Verify cleanup in all paths** - success, failure, early return
- [ ] **Verify injection actually happens** - check stdout/context

**How to run**:
```python
# Create temporary artifact file
# Simulate hook stdin: echo '{"tool_name": "Bash", ...}' | python hook.py
# Check: artifact deleted? Injection printed?
```

**For the GAV bug**: Integration test would show artifact still exists after injection.

---

## Priority Categories

- **P0 - Critical**: Must fix before SHIP (security, data loss, crashes)
- **P1 - High**: Should fix before SHIP (resource leaks, race conditions)
- **P2 - Medium**: Consider fixing (code quality, maintainability)
- **P3 - Low**: Nice to have (style, optimization opportunities)

---

## 1. Resource Management (P0-P1)

### File Descriptors (P0 - Critical)
- [ ] **File opened** → Must be closed in all paths (try, except, finally)
- [ ] **File descriptor not reused** after fdopen() or with block
- [ ] **Context managers preferred** (`with open()` not `open()` without close)
- [ ] **Temp files cleaned up** - mkstemp() paired with close/unlink
- [ ] **File handles in finally** - closed even if exception raised

**Common Bugs**:
- File descriptor consumed by fdopen(), then reused in except block
- Missing finally block - leak on exception
- Early return skips cleanup

**Detection**: TRACE all exception paths, verify fd state at each line

### Locks and Synchronization (P0 - Critical)
- [ ] **Lock acquisition flag** - boolean tracks if lock was acquired
- [ ] **Lock released in finally** - even if try block fails
- [ ] **Only release if acquired** - finally checks flag before unlink
- [ ] **Lock timeout handled** - timeout doesn't cause resource leak
- [ ] **No deadlock potential** - locks acquired in consistent order
- [ ] **Shared state protected** - all access to shared vars is locked

**Common Bugs**:
- finally block deletes lock even if acquisition failed
- Lock acquired but never released (missing finally)
- Deadlock from inconsistent lock ordering

**Detection**: TRACE happy path + timeout + exception paths

### Database Connections (P0 - Critical)
- [ ] **Connection opened** → Must be closed in finally
- [ ] **Transaction begin → commit/rollback** - no orphan transactions
- [ ] **Cursor closed** before connection closed
- [ ] **Connection pool handled** - connections returned to pool
- [ ] **Retry logic safe** - doesn't leak connections on retry

**Common Bugs**:
- Exception leaves transaction open
- Cursor not closed before connection closed
- Connection not returned to pool in exception path

**Detection**: TRACE exception paths, verify cleanup order

### Network Connections (P1 - High)
- [ ] **Socket opened** → Must be closed in finally
- [ ] **Timeout set** - no infinite waits
- [ ] **Connection errors handled** - doesn't leave socket open
- [ ] **HTTP response closed** - after reading body

**Common Bugs**:
- Socket leak on timeout
- Response body not consumed/closed
- No timeout → hangs

**Detection**: TRACE timeout scenarios, verify socket state

### Memory Management (P1 - High)
- [ ] **Allocations matched with frees** - malloc/free, new/delete
- [ ] **No memory leaks in loops** - accumulations without cleanup
- [ ] **Large objects released** - after use, not held forever
- [ ] **Reference cycles avoided** - weak references where needed

**Common Bugs**:
- Memory leak in exception path
- Cache growing without bound
- Circular references

**Detection**: TRACE loop iterations, exception paths, object lifetimes

---

## 2. Exception Handling (P0-P2)

### Exception Catching (P0 - Critical)
- [ ] **No bare except** - must catch specific exceptions
- [ ] **Specific exceptions** - OSError, ValueError, not Exception
- [ ] **Exception info preserved** - `except OSError as e:` not bare
- [ ] **Original exception re-raised** - `raise` not `raise Exception()`
- [ ] **No silent failures** - exceptions logged, not swallowed

**Common Bugs**:
- `except:` catches KeyboardInterrupt and SystemExit
- Swallowing exceptions with `pass`
- Re-raising generic exception loses stack trace

**Detection**: Check all except clauses, verify specificity

### Error Messages (P2 - Medium)
- [ ] **Error messages informative** - include variable values, context
- [ ] **No empty strings** - not `raise Exception("")`
- [ ] **User-facing errors** - explain what went wrong + how to fix
- [ ] **Debug info included** - file path, line number, variable state

**Common Bugs**:
- Generic "error occurred" messages
- No context in exception
- Missing critical information (which file? which line?)

**Detection**: Review all exception handling, check message strings

### Logging (P2 - Medium)
- [ ] **Exceptions logged** at appropriate level (ERROR, WARNING, DEBUG)
- [ ] **Sensitive data not logged** - no passwords, tokens, PII
- [ ] **Tracebacks logged** for debugging (ERROR level)
- [ ] **User-visible errors** - print() for users, logging for debugging

**Common Bugs**:
- Logging at DEBUG level (invisible) when should be ERROR
- Logging secrets/credentials
- No logging → silent failures

**Detection**: Check all exception blocks for logging

---

## 3. Concurrency Safety (P0-P1)

### Race Conditions (P0 - Critical)
- [ ] **No TOCTOU races** - use atomic operations, not check-then-act
- [ ] **File operations atomic** - os.replace not exists() + write
- [ ] **Lock ordering consistent** - acquire locks in same order everywhere
- [ ] **No shared state without locks** - all shared vars protected
- [ ] **Check-then-act eliminated** - use try/except instead of if-exists

**Common Bugs**:
- `if exists(): open()` race between check and open
- Multiple locks acquired in different order (deadlock)
- Global variable accessed without lock

**Detection**: TRACE concurrent access scenarios, look for check-then-act patterns

### Lock Cleanup (P0 - Critical)
- [ ] **Lock release in finally** - executes even if try fails
- [ ] **Release only if acquired** - finally checks acquisition flag
- [ ] **No stale lock deletion** - won't delete another process's lock
- [ ] **Lock file permissions** - proper umask for lock files
- [ ] **Lock timeout reasonable** - not too short, not too long

**Common Bugs**:
- finally unlinks lock even if acquisition failed
- Lock timeout too short → spurious failures
- Lock never released if early return

**Detection**: TRACE lock acquisition failure + exception paths

### Thread Safety (P1 - High)
- [ ] **Immutable data preferred** - avoid shared mutable state
- [ ] **Thread-local storage** - use threading.local() for per-thread data
- [ ] **Atomic operations** - use queue.Lock, atomic operations
- [ ] **No deadlocks** - lock timeout or consistent ordering
- [ ] **GIL considerations** - Python GIL doesn't guarantee safety

**Common Bugs**:
- Shared mutable state without locks
- Assuming GIL provides thread safety
- Deadlock from circular locks

**Detection**: TRACE multi-threaded scenarios, verify synchronization

---

## 4. Logic Correctness (P0-P2)

### Control Flow (P0 - Critical)
- [ ] **Early returns don't skip cleanup** - use finally or explicit cleanup
- [ ] **Finally blocks execute** - in all paths, no bypass
- [ ] **Loop invariants preserved** - termination conditions correct
- [ ] **No infinite loops** - always has termination condition
- [ ] **All branches covered** - no missing else clauses

**Common Bugs**:
- Early return skips cleanup code
- finally not executed (early return, goto)
- Loop doesn't terminate on edge case

**Detection**: TRACE all branches, verify cleanup runs

### Variable State (P0 - Critical)
- [ ] **Variables not reused after consumption** - fd, iterators, generators
- [ ] **Variable initialization** - set before use in all paths
- [ ] **No use-after-free** - object not used after cleanup
- [ ] **No stale references** - references updated after state change
- [ ] **No shadowing** - same name in outer/inner scope

**Common Bugs**:
- File descriptor consumed by with block, reused in except
- Iterator exhausted, used again
- Variable used before initialization

**Detection**: TRACE variable state at each line, watch for consumption

### Edge Cases (P1 - High)
- [ ] **Empty input handled** - doesn't crash on empty list/string
- [ ] **Null/None checks** - validates before use
- [ ] **Boundary conditions** - array bounds, loop limits
- [ ] **Zero/negative values** - handled correctly
- [ ] **Single element cases** - works with one item

**Common Bugs**:
- Crash on empty input
- No null check before use
- Off-by-one errors in loops

**Detection**: TRACE edge case scenarios

### Algorithm Correctness (P1 - High)
- [ ] **Loop invariants** - true at start, end, and each iteration
- [ ] **Termination** - loop eventually exits
- [ ] **Postconditions** - result meets specification
- [ ] **No integer overflow** - checks for overflow in calculations
- [ ] **No floating point issues** - epsilon comparisons, not exact

**Common Bugs**:
- Infinite loop (missing termination)
- Wrong loop bounds (off-by-one)
- Floating point equality check

**Detection**: TRACE algorithm execution, verify invariants

---

## 5. Security (P0-P1)

### Input Validation (P0 - Critical)
- [ ] **All inputs validated** - length, type, range
- [ ] **No SQL injection** - use parameterized queries
- [ ] **No command injection** - no shell=True with user input
- [ ] **No path traversal** - validate file paths, resolve symlinks
- [ ] **No XSS** - HTML output escaped

**Common Bugs**:
- SQL: f"SELECT * FROM users WHERE name='{user_input}'"
- Shell: os.system(f"command {user_input}")
- Path: open(user_input) without validation

**Detection**: TRACE all external inputs, verify validation

### Cryptography (P0 - Critical)
- [ ] **No hard-coded secrets** - no API keys, passwords in code
- [ ] **Strong encryption** - AES not DES, SHA256 not MD5
- [ ] **Proper key management** - keys not logged, not in git
- [ ] **Random values** - use secrets.random, not random module
- [ ] **No timing attacks** - constant-time comparisons

**Common Bugs**:
- Hard-coded API keys
- Using MD5 for passwords
- Using random instead of secrets.random

**Detection**: Grep for secrets, review crypto usage

### Authentication/Authorization (P0 - Critical)
- [ ] **Authentication required** - protected routes check auth
- [ ] **Authorization checks** - user can only access their data
- [ ] **No privilege escalation** - can't elevate permissions
- [ ] **Session management** - timeouts, secure tokens
- [ ] **Rate limiting** - prevents brute force

**Common Bugs**:
- Missing auth check
- IDOR (direct object reference) - can access others' data
- No rate limiting on auth

**Detection**: TRACE auth flows, verify all checks present

### Data Validation (P1 - High)
- [ ] **Output encoding** - escape HTML, JSON, SQL
- [ ] **Length limits** - prevent DoS from huge inputs
- [ ] **Type checking** - validate data types
- [ ] **Range checking** - numbers in valid range
- [ ] **No sensitive data in logs** - passwords, tokens, PII

**Common Bugs**:
- No output encoding (XSS)
- No length limits (DoS)
- Logging sensitive data

**Detection**: TRACE data flows from input to output

---

## 6. Performance (P2-P3)

### Algorithmic Complexity (P2 - Medium)
- [ ] **No O(n²) where O(n log n) possible** - sorting algorithms
- [ ] **No nested loops without need** - can often be flattened
- [ ] **Early exits** - return/break early when possible
- [ ] **Caching used** - avoid repeated expensive operations
- [ ] **Lazy evaluation** - defer work until needed

**Common Bugs**:
- Nested loops O(n²) when single pass O(n) possible
- Repeated expensive calculations in loop
- No caching of repeated lookups

**Detection**: Review loops, calculate complexity

### Resource Usage (P2 - Medium)
- [ ] **No memory leaks** - allocations balanced with frees
- [ ] **No excessive allocations** - reuse buffers
- [ ] **Connection pooling** - reuse connections
- [ ] **Batch operations** - group multiple operations
- [ ] **Pagination** - process large data in chunks

**Common Bugs**:
- Memory leak in loop
- Creating new connection for each query
- Loading entire dataset into memory

**Detection**: TRACE resource acquisition/release patterns

### I/O Efficiency (P2 - Medium)
- [ ] **Buffered I/O** - use buffered readers/writers
- [ ] **Batch writes** - group multiple writes
- [ ] **Async I/O** - for concurrent operations
- [ ] **No redundant I/O** - cache reads, avoid duplicate work
- [ ] **Compression** - for large data transfers

**Common Bugs**:
- Unbuffered I/O in tight loop
- Reading same file multiple times
- No async for concurrent operations

**Detection**: Review I/O patterns, look for redundancy

---

## 7. Code Quality (P2-P3)

### Readability (P3 - Low)
- [ ] **Self-documenting code** - variable names explain purpose
- [ ] **Complex logic commented** - explain non-obvious logic
- [ ] **Function length** - fits on one screen (~50 lines)
- [ ] **Nesting depth** - max 4 levels
- [ ] **Magic numbers** - replaced with named constants

**Common Bugs**:
- Cryptic variable names (x, y, tmp)
- No comments on complex algorithms
- Deep nesting (8+ levels)

**Detection**: Code review, readability check

### Maintainability (P2 - Medium)
- [ ] **DRY principle** - no duplicate code
- [ ] **Single responsibility** - functions do one thing
- [ ] **Cohesion** - related functionality grouped
- [ ] **Coupling minimized** - few dependencies
- [ ] **Testable** - can unit test in isolation

**Common Bugs**:
- Same code copied in multiple places
- God functions (100+ lines, multiple responsibilities)
- Tight coupling to global state

**Detection**: Code review, look for duplication

### Error Messages (P2 - Medium)
- [ ] **Actionable error messages** - tell user what to do
- [ ] **Context included** - file path, line number, operation
- [ ] **No technical jargon** - end-user friendly
- [ ] **Suggestions provided** - how to fix the problem

**Common Bugs**:
- "Error occurred" (what error?)
- "Invalid input" (what's invalid?)
- Technical jargon for end-users

**Detection**: Review all error messages

---

## 8. Testing Coverage (P2)

### Edge Cases Tested (P2 - Medium)
- [ ] **Happy path tested** - normal operation
- [ ] **Error paths tested** - exceptions handled correctly
- [ ] **Boundary conditions tested** - empty, single, max
- [ ] **Concurrent access tested** - if applicable
- [ ] **Error injection tested** - simulate failures

**Common Bugs**:
- Only happy path tested
- No edge case coverage
- No failure scenario testing

**Detection**: Review test coverage, check for gaps

### Test Quality (P2 - Medium)
- [ ] **Assertions specific** - check exact behavior
- [ ] **No brittle tests** - don't test implementation details
- [ ] **Test isolation** - tests don't depend on each other
- [ ] **Fast tests** - unit tests run quickly
- [ ] **Clear test names** - describe what is being tested

**Common Bugs**:
- Generic assertions (assert True)
- Brittle tests (break on refactoring)
- Slow tests (integration tests where unit tests suffice)

**Detection**: Review test code, check assertions

---

## 9. Documentation (P3)

### Code Comments (P3 - Low)
- [ ] **Complex algorithms explained** - why, not what
- [ ] **Non-obvious logic commented** - explain reasoning
- [ ] **Public API documented** - parameters, return values
- [ ] **TODO/FIXME markers** - track work to be done
- [ ] **No commented-out code** - remove or explain why kept

**Common Bugs**:
- Comments say what code does (redundant)
- No comments on complex logic
- Large blocks of commented-out code

**Detection**: Code review, check comments

### API Documentation (P2 - Medium)
- [ ] **Function signatures** - parameters, types, defaults
- [ ] **Return values** - type, meaning, error cases
- [ ] **Exceptions raised** - which exceptions, when
- [ ] **Usage examples** - show how to use
- [ ] **Limitations noted** - what it doesn't do

**Common Bugs**:
- No parameter documentation
- No mention of exceptions
- No usage examples

**Detection**: Review public API docs

---

## TRACE Report Template

After tracing each file, create a report:

```markdown
## TRACE Report: module/file.py

**Date**: YYYY-MM-DD
**Traced by**: [Your name]
**Modified lines**: 45-230 (185 lines changed)

### Scenarios Traced
1. ✓ Happy path: Function called with valid input, returns success
2. ✓ Error path: OSError raised, cleanup executed correctly
3. ✓ Edge case: Empty input handled gracefully

### Findings Summary
- **Logic Errors Found**: 0
- **Resource Leaks Found**: 0
- **Race Conditions Found**: 0
- **Security Issues Found**: 0
- **Code Quality Issues**: 2 (P2)

### Issues Found

#### Issue #1: P2 - Code Quality
- **Location**: Lines 120-135
- **Problem**: Function too long (16 lines), extracts validation logic
- **Impact**: Reduced readability, harder to test
- **Recommendation**: Extract validation to separate function

#### Issue #2: P2 - Error Messages
- **Location**: Line 185
- **Problem**: Generic error message: "Invalid input"
- **Impact**: User doesn't know what's wrong
- **Recommendation**: Specify which parameter failed validation

### Static Analysis Results
- **pylint**: 0 blocking, 3 warnings (complexity, line length)
- **mypy**: 0 blocking, 0 warnings
- **bandit**: 0 blocking, 0 warnings

### TRACE Results
✅ **PASS** - All scenarios traced correctly
- Resource cleanup verified in all paths
- No logic errors found
- No race conditions detected
- Security checks passed

### Recommendation
Ready for SHIP phase. P2 issues are optional improvements, not blocking.
```

---

## Severity Guidelines

### When to Block SHIP

**P0 - Critical** (Must fix before SHIP):
- Security vulnerabilities
- Data loss bugs
- Crash/hang bugs
- Resource leaks (file descriptors, memory, locks)
- Race conditions
- Logic errors that affect correctness

**P1 - High** (Should fix before SHIP):
- Resource management issues in edge cases
- Error handling gaps
- Missing exception handling
- Performance issues that impact users

### Can Defer to Later

**P2 - Medium** (Consider fixing):
- Code quality issues
- Maintainability improvements
- Minor performance optimizations

**P3 - Low** (Nice to have):
- Style improvements
- Documentation gaps
- Minor readability improvements

---

## Quick Reference: Most Common TRACE Bugs

Based on research from handoff system fixes and industry data:

### Top 10 TRACE Bugs

1. **Lock cleanup race** - finally block deletes another process's lock
2. **File descriptor reuse** - fd consumed, then reused in except block
3. **TOCTOU race** - check-then-act pattern has race condition
4. **Resource leak in exception path** - cleanup skipped on error
5. **Early return skips cleanup** - no finally block
6. **Variable used after free/close** - use-after-free bug
7. **Missing exception handling** - bare except or no except
8. **Silent failure** - exception caught but not logged
9. **Stale data used** - fallback to outdated cached value
10. **Infinite loop** - missing termination condition

### Detection Pattern

**For each bug type**:
1. **Identify pattern** from code
2. **TRACE all scenarios** (happy, error, edge)
3. **Verify resource state** at each line
4. **Check cleanup in exception paths**
5. **Document finding** with line numbers

---

## TRACE Phase Completion Criteria

 TRACE phase is **COMPLETE** when:

- [ ] All modified files have been read completely
- [ ] Each modified function has 3 scenarios traced (happy, error, edge)
- [ ] TRACE tables created for complex functions (file I/O, locking, concurrency)
- [ ] TRACE checklist reviewed for all applicable items
- [ ] All P0 and P1 issues fixed
- [ ] P2 and P3 issues documented in decision log
- [ ] TRACE report created for each file
- [ ] Static analysis results integrated into report
- [ ] Ready to proceed to SHIP phase

**Estimated time per file**: 5-15 minutes (depending on complexity)
**Typical TRACE session**: 30-60 minutes for 3-5 modified files
