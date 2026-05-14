# TRACE Visualization Templates

Pre-built Mermaid diagrams for common TRACE patterns. Use these templates to document and communicate TRACE findings.

## Template 1: File Descriptor Lifecycle

**When to use**: Tracing file I/O operations, resource acquisition/release

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["1. Initial State<br/>fd=None"]:::default
    B["2. Open File<br/>fd=3"]:::pass
    C["3. Read Data<br/>fd=3, data=<bytes>"]:::pass
    D["4. Process Data<br/>fd=3, result=<obj>"]:::pass
    E["5. Close File<br/>fd=None"]:::pass

    A --> B
    B --> C
    C --> D
    D --> E

    F["2a. Open Fails<br/>Exception raised"]:::fail
    G["3a. Exception Path<br/>Cleanup in finally"]:::pass

    A --> F
    F --> G
```

**Key observations**:
- Resource acquisition (fd=3) at step 2
- Resource used at steps 3-4
- **Critical**: Resource released at step 5 in all paths
- Exception path (2a → 3a) also releases resource

---

## Template 2: Lock Acquisition with Timeout

**When to use**: Tracing concurrent access, locking mechanisms

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["1. Try Acquire Lock<br/>lock_acquired=False"]:::default
    B["2. Lock Acquired<br/>lock_acquired=True"]:::pass
    C["3. Critical Section<br/>Modifying shared state"]:::pass
    D["4. Release Lock<br/>lock_acquired=False"]:::pass

    A --> B
    B --> C
    C --> D

    E["2a. Timeout/Failed<br/>lock_acquired=False"]:::fail
    F["3a. Skip Critical<br/>Return error"]:::warn

    A --> E
    E --> F

    G["4a. Finally Block<br/>Check lock_acquired"]:::pass
    H["5a. Conditional Cleanup<br/>Only release if acquired"]:::pass

    D --> G
    F --> G
    G --> H
```

**Key observations**:
- **Critical**: Finally block checks `lock_acquired` before releasing
- Prevents deleting another process's lock
- Both success and failure paths converge on cleanup

---

## Template 3: TOCTOU Race Condition

**When to use**: Tracing check-then-act patterns, time-of-check-time-of-use bugs

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["1. Check File Exists<br/>os.path.exists(file)"]:::default
    B["2. File Exists: True<br/>Proceed with operation"]:::pass
    C["3. Open File<br/>f = open(file)"]:::pass

    A --> B
    B --> C

    D["⚠️ RACE WINDOW<br/>Another process deletes file"]:::warn
    E["3a. File Not Found<br/>FileNotFoundError"]:::fail

    B --> D
    D --> E

    F["4a. Exception Handler<br/>File disappeared between check and use"]:::fail
    G["5a. TOCTOU Bug<br/>Non-atomic operation"]:::fail

    E --> F
    F --> G
```

**Key observations**:
- **BUG**: Race window between check (step 1) and use (step 3)
- **Fix**: Use atomic operation (e.g., `os.open(file, os.O_CREAT | os.O_EXCL)`)
- Another process can delete file during the race window

---

## Template 4: Exception Handling with Cleanup

**When to use**: Tracing exception paths, resource cleanup in error scenarios

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["1. Acquire Resources<br/>conn, fd, lock"]:::default
    B["2. Try Block<br/>Execute operation"]:::pass
    C["3. Success Path<br/>Process result"]:::pass

    A --> B
    B --> C

    D["2a. Exception Raised<br/>Error in operation"]:::fail
    E["3a. Catch Exception<br/>Log error"]:::pass
    F["4a. Re-raise or Return<br/>Propagate error"]:::warn

    B --> D
    D --> E
    E --> F

    G["5. Finally Block<br/>Always executes"]:::pass
    H["6. Cleanup Resources<br/>conn.close(), fd.close(), lock.release()"]:::pass

    C --> G
    F --> G
    G --> H
```

**Key observations**:
- Both success (B → C) and error (B → D → E → F) paths converge on finally (G)
- **Critical**: Cleanup happens regardless of exception
- All resources released in finally block (H)

---

## Template 5: Workflow Step Dependencies

**When to use**: Tracing workflow execution, step dependencies, rollback paths

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["Step 1: Parse Config<br/>config = parse(config_file)"]:::pass
    B["Step 2: Validate Tasks<br/>validate(config.tasks)"]:::pass
    C["Step 3: Execute Tasks<br/>run(config.tasks)"]:::pass
    D["Step 4: Cleanup<br/>cleanup(temp_files)"]:::pass

    A --> B
    B --> C
    C --> D

    E["2a. Validation Fails<br/>Invalid task config"]:::fail
    F["3a. Rollback<br/>Undo Step 1 changes"]:::warn

    B --> E
    E --> F

    G["3b. Execution Fails<br/>Task error"]:::fail
    H["4b. Rollback<br/>Undo Steps 1-2"]:::warn

    C --> G
    G --> H

    I["4c. Checkpoint<br/>Save progress"]:::pass
    J["5. Complete<br/>Report success"]:::pass

    D --> I
    F --> I
    H --> I
    I --> J
```

**Key observations**:
- Clear dependency chain: Step 1 → Step 2 → Step 3 → Step 4
- Each failure path has explicit rollback (F, H)
- Checkpoint (I) saves progress for recovery
- All paths converge on completion (J)

---

## Template 6: Intent Detection Flow (Skills)

**When to use**: Tracing skill intent detection, tool selection, fallback scenarios

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["1. User Input<br/>'create a new feature'"]:::default
    B["2. Intent Detection<br/>Match patterns"]:::pass
    C["3. Intent Matched<br/>intent='feature'"]:::pass
    D["4. Tool Selection<br/>/code, /design"]:::pass
    E["5. Execute<br/>Run tools"]:::pass

    A --> B
    B --> C
    C --> D
    D --> E

    F["3a. No Match<br/>intent='unknown'"]:::warn
    G["4a. Fallback<br/>Delegate to /search"]:::pass
    H["5a. Return Results<br/>Search findings"]:::pass

    B --> F
    F --> G
    G --> H

    I["4b. Tool Fails<br/>Tool error"]:::fail
    J["5b. Error Handler<br/>Log and fallback"]:::warn

    D --> I
    I --> J
```

**Key observations**:
- Intent detection (B) branches to matched (C) or unmatched (F)
- Matched path: Select tools (D) → Execute (E)
- Unmatched path: Fallback to /search (G → H)
- Tool failure (I) triggers error handler (J)

---

## Template 7: Document Consistency Check

**When to use**: Tracing document reviews, cross-reference validation

```mermaid
flowchart TD
    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    A["1. Section 1: Claim<br/>'System supports X'"]:::default
    B["2. Section 2: Evidence<br/>'Implementation: X'"]:::pass
    C["3. Section 3: Cross-ref<br/>'See Section 5 for details'"]:::pass
    D["4. Section 5: Details<br/>'X implementation details'"]:::pass

    A --> B
    B --> C
    C --> D

    E["3a. Broken Cross-ref<br/>Section 5 doesn't exist"]:::fail
    F["4a. Inconsistency<br/>Section 5 contradicts Section 1"]:::fail

    C --> E
    D --> F

    G["5. Validation<br/>Check all references"]:::pass
    H["6. Report<br/>List issues"]:::pass

    D --> G
    E --> G
    F --> G
    G --> H
```

**Key observations**:
- Cross-reference check (C → D) validates target section exists
- Consistency check (D → F) validates content matches claims
- All issues collected and reported (G → H)

---

## How to Use These Templates

### Step 1: Select Template
Choose the template that matches your TRACE scenario:
- File I/O → Template 1
- Locking → Template 2
- Race conditions → Template 3
- Exception handling → Template 4
- Workflows → Template 5
- Skills → Template 6
- Documents → Template 7

### Step 2: Customize Nodes
Replace placeholder text with actual operations from your code:
- `["1. Your Operation<br/>var=value"]`

### Step 3: Apply Styles
Use style classes to indicate status:
- `:::pass` for correct operations (green)
- `:::fail` for bugs/errors (red)
- `:::warn` for warnings (yellow)
- `:::default` for neutral (blue)

### Step 4: Add to TRACE Report
Include the Mermaid diagram in your TRACE report:
```markdown
### Visualization: Happy Path

```mermaid
[Your customized diagram]
```
```

---

## Creating Custom Templates

For patterns not covered here, create custom diagrams following this structure:

1. **Nodes**: Each step in the TRACE
   - Format: `["Step number: Description<br/>State"]`
   - Use `:::class` for styling

2. **Edges**: Arrows showing flow
   - Success path: `-->`
   - Exception path: `-->|condition|`

3. **Styles**: Color coding
   - `pass`: Green (correct)
   - `fail`: Red (bug)
   - `warn`: Yellow (warning)
   - `default`: Blue (neutral)

4. **Layout**: Flowchart
   - `flowchart TD` for top-down
   - `flowchart LR` for left-right

---

## Integration with TRACE Reports

The `/trace` skill automatically generates Mermaid diagrams from state tables. To use custom templates:

1. **Auto-generated** (default):
   - Use `state_table_to_mermaid()` in TraceReport
   - Automatically creates diagrams from TRACE scenarios

2. **Custom templates** (manual):
   - Copy template from this file
   - Customize for your specific scenario
   - Include in TRACE report markdown

---

## See Also

- **TRACE Methodology**: `TRACE_METHODOLOGY.md`
- **Code TRACE Templates**: `code/TRACE_TEMPLATES.md`
- **Code TRACE Case Studies**: `code/TRACE_CASE_STUDIES.md`
