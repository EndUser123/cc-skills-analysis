# TRACE Integrations, Usage Examples, and Version History

## Integration with /code Skill

The `/code` skill Phase 3.5 (TRACE) delegates to `/trace code:<file>`:

**Delegation pattern**:
```markdown
## Phase 3.5: TRACE - Manual Code Trace-Through

**Purpose**: Manual code trace-through to catch logic errors

**Invocation**:
- Automatic: Delegates to `/trace code:<file>` during Phase 3.5
- Manual: `/trace code:<file>` (standalone)

**TRACE Methodology**: See P:\\\\\\.claude/skills/trace/templates/TRACE_METHODOLOGY.md
**Code TRACE Templates**: See P:\\\\\\.claude/skills/trace/templates/code/TRACE_TEMPLATES.md
**TRACE Checklist**: See P:\\\\\\.claude/skills/trace/templates/code/TRACE_CHECKLIST.md
```

## Usage Examples

### Code TRACE (fully implemented)
```bash
/trace code:src/handoff.py                    # Manual code trace-through
/trace code:src/handoff.py --template 2      # Use specific template
/trace code:src/handoff.py --no-tot           # Disable ToT enhancement
```

### Skill TRACE (extension point - future)
```bash
/trace skill:skill-development                # Intent detection review
/trace skill:skill-development --full         # Full skill review
```

### Workflow TRACE (extension point - future)
```bash
/trace workflow:flows/feature.md              # Dependency verification
/trace workflow:flows/feature.md --rollback   # Focus on rollback paths
```

### Document TRACE (extension point - future)
```bash
/trace document:CLAUDE.md                     # Consistency check
/trace document:CLAUDE.md --cross-refs       # Verify cross-references
```

### Auto-detect domain (default behavior)
```bash
/trace src/handoff.py                         # Detects: code
/trace SKILL.md                                # Detects: skill
/trace flows/feature.md                       # Detects: workflow
```

## Execution Directive

For `/trace` requests, execute this workflow:

```bash
# Main entry point
cd P:\\\\\\.claude/skills/trace && python __main__.py "domain:target"

# Examples
python __main__.py "code:src/handoff.py"
python __main__.py "skill:skill-development"
python __main__.py "workflow:flows/feature.md"
python __main__.py "document:CLAUDE.md"

# Default (auto-detect domain)
python __main__.py "src/handoff.py"  # Detects: code
python __main__.py "SKILL.md"         # Detects: skill
```

## Version History

- **v1.1.0** (2026-03-10): Enhanced error handling and configuration
  - Fixed P0: Added try-finally block for proper resource cleanup
  - Fixed P1: Enhanced path resolution with user-friendly error messages
  - Fixed P2: Made project root configurable via TRACE_PROJECT_ROOT environment variable
  - Enhanced error messages with helpful suggestions and hints
  - Added --project-root CLI argument for runtime configuration
- **v1.0.0** (2026-02-28): Initial release with code TRACE support
