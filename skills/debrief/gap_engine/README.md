# Internal GAP Engine — Gap-to-Opportunity Analysis

Package-owned detector engine used by `/debrief gaps`. It is not a standalone
Claude skill or user-facing command.

## Quick Start

```
/debrief gaps <path>
```

## Engine Modes

| Mode | Description |
|------|-------------|
| `full` | Deterministic + agent analysis (default) |
| `quick` | Deterministic detectors only |
| `agent-only` | Agent analysis only |

## Architecture

```
Deterministic Detectors → Merge → Normalize → Dedupe → Route → Order → Render
                              ↑                              ↑
                        Agent Results                   Carryover
```

### Detectors

- **GIT-001**: Missing `.git` directory (severity: high)
- **DOC-001**: Missing `README.md` (severity: medium)
- **QUAL-001**: TODO/FIXME/HACK/XXX markers (severity: low)

### Agent Roles

- **Domain Analyzer**: Finds code gaps across quality, tests, docs, security, performance
- **Findings Reviewer**: Validates findings, removes duplicates, adjusts severities
- **Action Normalizer**: Ensures valid domains, severities, actions, and effort estimates

### Routing

| Gap Type | Routes To |
|----------|-----------|
| missingdocs | /docs |
| techdebt | /code |
| runtime_error, bug | /diagnose |
| security | /security |
| perf | /perf |
| invalidrepo | /git |
| staledeps | /deps |

## Artifact Structure

```
.claude/.artifacts/{terminal_id}/gap/
├── state/run_state.json      # Run state (phase, verification status)
├── inputs/                   # Agent handoff files
├── outputs/artifact.json     # Main artifact with findings
├── logs/failures.jsonl       # Failure capture log
└── carryover.json            # Unresolved findings for future runs
```

## RNS Compatibility

The engine output uses the shared RNS-compatible machine format:

```
RNS|D|1|🔧|QUALITY
RNS|A|1a|quality|E:~5min|recover/medium|description|file_ref|owner=/code|done=0|caused_by=|blocks=|unverified=0
RNS|Z|0|NONE
```

## Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| sessionstart.py | SessionStart | Restore state, show prior diagnosis |
| pretooluse.py | PreToolUse | Block destructive operations during runs |
| posttooluse.py | PostToolUse | Capture failures, validate artifacts |
| stop.py | Stop | State-driven completion verification |

## Testing

```bash
cd P://packages/.claude-marketplace/plugins/cc-skills-analysis
python -m pytest skills/debrief/gap_engine/tests/ -k "gap or test_models or test_detectors or test_normalize or test_dedupe or test_route or test_render or test_machine_render or test_verify" -v
```
