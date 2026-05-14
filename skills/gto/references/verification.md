# GTO Verification

## Artifact Verification

The `verify.py` module checks artifacts have:

1. Required fields: `artifact_version`, `mode`, `terminal_id`, `session_id`, `target`, `findings`, `machine_output`, `human_output`, `verification`, `coverage`
2. Machine output with RNS format: at least one `RNS|D|` line and one `RNS|Z|` line
3. Findings as a valid JSON array

## State Verification

State verification checks:

1. State file exists and is valid JSON
2. `phase` field equals `"completed"`
3. `verification_status` is `"pass"` or `"fail"`

## CLI Assertions

Run assertions standalone:

```bash
python -m skills.gto.__lib.assertions path/to/artifact.json --state path/to/run_state.json
```

Exit 0 = all pass, exit 1 = failures on stderr.
