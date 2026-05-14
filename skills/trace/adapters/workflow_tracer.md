# Workflow TRACE Adapter

**Status**: Extension point (not yet implemented)

## Purpose

Review workflow step dependencies, error handling, and rollback paths.

## Focus Areas

1. **Step Dependencies**: Are dependencies satisfied before execution?
2. **Execution Order**: Do steps execute in correct order?
3. **Error Handling**: Is error handling present in each step?
4. **Rollback Paths**: Can workflow rollback on failure?
5. **Circular Dependencies**: Are there circular dependencies?

## TRACE Table Template

| Step | Operation | Dependencies | State Changes | Error Path | Notes |
|------|-----------|--------------|---------------|------------|-------|
| 1 | Parse plan.md | File exists | plan=<obj> | File found | |
| 2 | Validate tasks | plan.tasks | Validated | Validation fails | Rollback |
| 3 | Execute tasks | Validated | Tasks run | Success | |

## Common Bugs

1. **Circular dependencies**
   - Step A depends on Step B
   - Step B depends on Step A
   - Deadlock

2. **Missing rollback path**
   - Step fails, no rollback
   - System left in inconsistent state

3. **Error handling in step causes cascade failure**
   - Step 1 fails, triggers Step 2 error handler
   - Cascade failure across workflow

4. **Steps execute in wrong order**
   - Dependencies not satisfied
   - Step runs before prerequisite

## Implementation

When implementing workflow TRACE:

```python
class WorkflowTracer(Tracer):
    """Workflow TRACE adapter for workflow definitions."""

    def read_target(self) -> str:
        """Read workflow definition file."""
        return self.target_path.read_text(encoding='utf-8')

    def define_scenarios(self):
        """Define scenarios to trace."""
        return [
            TraceScenario(name='Happy Path', description='All steps execute successfully'),
            TraceScenario(name='Step Failure', description='One step fails, verify rollback'),
            TraceScenario(name='Dependency Error', description='Dependency not satisfied'),
        ]

    def trace_scenario(self, scenario):
        """Execute TRACE for a single scenario."""
        # Parse workflow definition
        # Extract step dependencies
        # Verify execution order
        # Check rollback paths
        pass

    def check_checklist(self):
        """Verify workflow TRACE checklist."""
        issues = []

        # Check for rollback paths
        if 'finally' not in self.content.lower() and 'rollback' not in self.content.lower():
            issues.append(TraceIssue(
                severity='P1',
                category='Logic Errors Found',
                location='Error handling section',
                problem='No rollback or cleanup defined',
                impact='Workflow failure leaves system in inconsistent state',
                recommendation='Add finally block or rollback step for cleanup'
            ))

        return issues
```

## Usage

```bash
# When implemented:
/trace workflow:flows/feature.md
/trace workflow:cwo/CWO.md
/trace workflow:flows/phase0_bootstrap.md
```
