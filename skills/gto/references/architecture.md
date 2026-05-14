# GTO Architecture

## Pipeline

```
Deterministic Detectors
        ↓
    Carryover Load
        ↓
    Agent Analysis (optional)
        ↓
    Merge (deterministic wins over agent on same domain+gap_type)
        ↓
    Normalize (domain aliases, severity/action/priority validation)
        ↓
    Docs Followup Detection
        ↓
    Dedupe (by domain+title+file)
        ↓
    Route (gap_type → owning skill)
        ↓
    Order (severity → domain → id)
        ↓
    Render (machine RNS + human readable)
        ↓
    Write Artifact + Update State
        ↓
    Verify + Save Carryover
```

## Terminal Isolation

All artifacts are scoped by terminal ID under `.claude/.artifacts/{terminal_id}/gto/`.
This prevents cross-terminal conflicts when multiple terminals run GTO simultaneously.

## State Machine

```
initialized → running → completed
                  ↑         ↓
                  └── (on error: phase stays "running")
```

The stop hook checks `verification_required` and `phase == "completed"` to determine success.

## Agent Handoff Contract

Handoff is file-based:

1. Orchestrator writes `inputs/agent_handoff.json` with target, root, and config
2. Agent reads handoff, writes `inputs/domain_analyzer_result.json` with findings array
3. Orchestrator re-runs, picks up agent results via `domain_analyzer.read_result()`

No API calls between orchestrator and agents. Files are the contract boundary.
