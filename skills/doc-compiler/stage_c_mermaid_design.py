#!/usr/bin/env python3
"""Stage C: Mermaid Design for doc-compiler.

Generate Mermaid diagram from source-model.json via claude --print.
Output: diagram.mmd
"""
import json, subprocess, sys, re
from pathlib import Path

BASE   = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
SOURCE = BASE / "source-model.json"
OUT    = BASE / "diagram.mmd"

model = json.loads(SOURCE.read_text(encoding="utf-8"))

# Build Mermaid diagram
steps = model.get("steps", [])
decision_points = model.get("decision_points", [])
route_outs = model.get("route_outs", [])
terminal_states = model.get("terminal_states", [])

lines = []
lines.append("%%{ init: { 'theme': 'dark', 'flowchart': { 'curve': 'basis', 'nodeSpacing': 60, 'rankSpacing': 80 }, 'htmlLabels': true } }%%")
lines.append("flowchart TD")

# ClassDefs
lines.append("""classDef step     fill:#1e40af,stroke:#60a5fa,stroke-width:2.5px,color:#ffffff,font-size:13px,font-weight:600
classDef gate     fill:#92400e,stroke:#fbbf24,stroke-width:3px,color:#fef3c7,font-weight:700
classDef terminal fill:#059669,stroke:#10b981,stroke-width:3px,color:#ffffff,font-weight:700
classDef routeout fill:#7c3aed,stroke:#c084fc,stroke-width:2px,color:#ede9fe,font-style:italic
classDef start    fill:#1e1b4b,stroke:#818cf8,stroke-width:3px,color:#c7d2fe,font-weight:700""")

# Start node
lines.append("  START([Start])")

# Add steps
prev_id = "START"
for i, step in enumerate(steps, 1):
    sid = step.get("id", f"step{i}")
    name = step.get("display_name", step.get("name", f"Step {i}"))
    kind = step.get("kind", "step")

    # Truncate long labels
    if len(name) > 40:
        name = name[:37] + "..."

    if kind == "decision":
        node = f'  {sid}{{{name}}}'
    elif kind == "terminal":
        node = f'  {sid}(["{name}"])'
    elif kind == "route":
        node = f'  {sid}>"{name}"]'
    else:
        node = f'  {sid}["{name}"]'

    lines.append(node)

    # Style based on kind
    if kind == "decision":
        lines.append(f"  class {sid} gate")
    elif kind == "terminal":
        lines.append(f"  class {sid} terminal")
    elif kind == "route":
        lines.append(f"  class {sid} routeout")
    else:
        lines.append(f"  class {sid} step")

    # Edge from previous
    if prev_id:
        lines.append(f"  {prev_id} --> {sid}")

    prev_id = sid

# Terminal states not already in steps
for ts in terminal_states:
    tid = ts.get("id", "TERM")
    name = ts.get("name", "End")
    lines.append(f'  {tid}(["{name}"])')
    lines.append(f"  class {tid} terminal")
    if prev_id:
        lines.append(f"  {prev_id} -->|terminal| {tid}")

# Route outs
for ro in route_outs:
    rid = ro.get("id", "ROUTE")
    target = ro.get("target", "other")
    lines.append(f'  {rid}>"{target}"]')
    lines.append(f"  class {rid} routeout")
    if prev_id:
        lines.append(f"  {prev_id} -->|route out| {rid}")

mmd = "\n".join(lines) + "\n"
OUT.write_text(mmd, encoding="utf-8")

# Update artifact-plan.json with mermaid_source
plan_path = BASE / "artifact-plan.json"
if plan_path.exists():
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["mermaid_source"] = mmd
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

print(f"Stage C: PASS — {len(lines)} lines written")
print(f"Written: {OUT}")
sys.exit(0)
