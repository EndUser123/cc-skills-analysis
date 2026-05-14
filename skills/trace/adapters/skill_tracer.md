# Skill TRACE Adapter

**Status**: Extension point (not yet implemented)

## Purpose

Review skill intent detection logic, tool selection, and fallback scenarios.

## Focus Areas

1. **Intent Detection**: Are all common intents matched?
2. **Tool Selection**: Is tool selection deterministic?
3. **Fallback Scenarios**: What happens on unmatched intent?
4. **Error Handling**: Are tool errors handled gracefully?
5. **Retry Logic**: Are there infinite loops in retry logic?

## TRACE Table Template

| Step | User Input | Matched Intent | Tools Selected | Fallback? | Notes |
|------|------------|----------------|----------------|-----------|-------|
| 1 | "create a new feature" | intent=feature | /code, /design | No | Intent matched |
| 2 | "fix this bug" | intent=bugfix | /aid, /refactor | No | Intent matched |
| 3 | "what's the weather" | intent=unknown | None | Yes | Fallback to /search |

## Common Bugs

1. **Unmatched intent has no fallback**
   - User gets generic error
   - No graceful degradation

2. **Tool selection not deterministic**
   - Same intent triggers different tools
   - Confusing user experience

3. **Error handling missing in tool calls**
   - Tool failure crashes skill
   - No error recovery

4. **Infinite loops in retry logic**
   - Tool fails, retries forever
   - No max retry limit

## Implementation

When implementing skill TRACE:

```python
class SkillTracer(Tracer):
    """Skill TRACE adapter for SKILL.md files."""

    def read_target(self) -> str:
        """Read skill SKILL.md file."""
        return self.target_path.read_text(encoding='utf-8')

    def define_scenarios(self):
        """Define scenarios to trace."""
        return [
            TraceScenario(name='Matched Intent', description='User input matches known intent'),
            TraceScenario(name='Unmatched Intent', description='User input has no matching intent'),
            TraceScenario(name='Tool Failure', description='Selected tool fails or errors'),
        ]

    def trace_scenario(self, scenario):
        """Execute TRACE for a single scenario."""
        # Parse SKILL.md
        # Extract intent detection patterns
        # Verify tool selection logic
        # Check fallback scenarios
        pass

    def check_checklist(self):
        """Verify skill TRACE checklist."""
        issues = []

        # Check for fallback intent
        if 'fallback' not in self.content.lower():
            issues.append(TraceIssue(
                severity='P1',
                category='Logic Errors Found',
                location='Intent detection section',
                problem='No fallback for unmatched intents',
                impact='Users get generic error on unknown input',
                recommendation='Add fallback intent with default tool or /search delegation'
            ))

        return issues
```

## Usage

```bash
# When implemented:
/trace skill:skill-development
/trace skill:code
/trace skill:refactor
```
