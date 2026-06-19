# Flowchart Guide

## Use for
- overall workflow
- decisions and route-outs
- terminal states
- happy path and major alternates

## Rules
- Keep labels short and scannable.
- Label non-forward edges.
- Show terminals clearly.
- Keep the happy path visually obvious.
- Inline error branches when the graph stays readable; otherwise split.

## Mermaid shape mapping
- start/end: rounded nodes
- step: rectangle
- decision: diamond
- route-out: distinct class
- terminal: emphasized terminal node

## Required checks
- each workflow step appears
- each decision point appears
- each route-out appears
- each terminal appears
- required failure branches appear
