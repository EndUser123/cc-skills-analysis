# Diagram Selection Rules

Do not force every explanatory need into one flowchart. Choose diagrams based on what the user needs to understand.

## Flowchart
Use when:
- understanding the overall process
- routing, branches, gates, terminal outcomes
- happy path plus major alternates

## Sequence diagram
Use when:
- timing and order between actors matter
- tools/services/validators interact over time
- request/response and handoff behavior is central

## Class diagram
Use when:
- entities, objects, models, contracts, interfaces
- capability surfaces or domain structures

## State diagram
Use when:
- lifecycle and state transitions
- approval, retry, blocked, ready, completed
- document artifact lifecycle

## Error-path diagram / overlay
Use when:
- failures, retries, fallbacks, escalations, recovery
- hiding failures in prose would mislead

## Multi-diagram rule
If more than one explanatory dimension exists, generate multiple diagrams:
- flowchart + sequence
- flowchart + state
- flowchart + class + error-path

## Anti-patterns
- one giant flowchart that tries to explain process, timing, structure, and failure at once
- sequence diagrams used for static structure
- invented class diagrams
- error handling only in prose
