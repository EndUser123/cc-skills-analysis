# State Diagram Guide

## Use for
- lifecycle modeling
- status/phase transitions
- retry/blocked/ready/completed
- approval and gate transitions

## Rules
- States named clearly.
- Transitions labeled when condition matters.
- Avoid mixing process steps with states.
- Include failure and recovery transitions where present.

## Good candidates
- document artifact lifecycle
- validator pass/fail/rework loops
- plugin connection/auth/error/recovered lifecycle
- task progression through gates

## Required checks
- states grounded in source model
- transitions faithful
- recovery/retry states visible
