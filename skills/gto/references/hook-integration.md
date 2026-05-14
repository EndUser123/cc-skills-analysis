# GTO Hook Integration

## Hook Protocol

All hooks follow Claude Code's subprocess hook protocol:
- Read JSON from stdin
- Write JSON to stdout
- Exit 0 to allow, exit 2 to block

## Scope Guard Pattern

Hooks check `is_gto_active()` which looks for a state file in the terminal-scoped
artifacts directory. This is NOT a marker file — it's the actual run state.

If no state file exists, hooks return `{"decision": "allow"}` immediately.

## Hook Registration

Hooks are registered in SKILL.md frontmatter (not settings.json):

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python \"$CLAUDE_PROJECT_DIR/.claude/skills/gto/hooks/pretooluse.py\""
          timeout: 10
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "python \"$CLAUDE_PROJECT_DIR/.claude/skills/gto/hooks/posttooluse.py\""
          timeout: 10
  Stop:
    - matcher: "*"
      hooks:
        - type: command
          command: "python \"$CLAUDE_PROJECT_DIR/.claude/skills/gto/hooks/stop.py\""
          timeout: 15
```

## Stop Hook Verification

The stop hook does NOT parse prose. It checks:

1. State file exists with `phase == "completed"`
2. Artifact file exists at `state.last_artifact` path
3. Artifact is valid JSON with required fields
4. Machine output has `RNS|D|` and `RNS|Z|` markers
5. All `expected_artifacts` paths exist
