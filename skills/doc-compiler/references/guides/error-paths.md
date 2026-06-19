# Error Path Guide

## Principle
If the system can fail, retry, recover, escalate, or abort, that behavior must be visible in at least one diagram.

## Use for
- failure branches
- retry loops
- fallback behavior
- escalation paths
- terminal failure states

## Rules
- Never leave failure handling only in prose.
- Show what triggers failure branches.
- Show where recovery leads.
- Label retry conditions clearly.
- Distinguish recoverable vs terminal failures.
- Use a dedicated error-path diagram when inline branches overload the primary flowchart.

## Required checks
- each meaningful failure path represented
- recovery paths labeled
- terminal failures visually distinct
