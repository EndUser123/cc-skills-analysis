# Sequence Diagram Guide

## Use for
- request flows
- agent/tool/validator interactions
- user/system/service timing
- handoffs

## Rules
- Participants must come from the source model.
- Message labels describe intent, not implementation noise.
- Use `alt`, `else`, `opt`, notes as needed.
- Visualize validation and failure responses explicitly.
- Split long exchanges into focused sequences.

## Good candidates
- generator -> validator -> external critic
- user -> skill -> browser harness -> proof bundle
- plugin -> MCP tool -> external service -> retry path

## Required checks
- participants are real
- order of messages is faithful
- failure/retry paths shown when relevant
