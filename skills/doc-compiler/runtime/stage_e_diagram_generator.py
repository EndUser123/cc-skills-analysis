#!/usr/bin/env python3
"""Stage E: Diagram Generator for doc-compiler.

Reads guides-loaded.json (Stage D) + diagram-plan.json (Stage C).
Generates Mermaid diagram content for each diagram in the plan.
Emits diagrams.json + individual .mmd files per diagram.

Diagram generation rules (per selection-rules.md):
- Flowchart: steps as nodes, transitions as edges, routing decisions as diamonds
- Sequence: actors on lanes, messages as arrows between actors
- State: states as rounded boxes, transitions as arrows with labels
- Class: classes as rectangles with name/component/method sections
- Error-path: steps with error outcomes as red nodes, fallback arrows
"""
import json, re, sys
from pathlib import Path
from typing import Any

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
GUIDES = BASE / "guides-loaded.json"
PLAN   = BASE / "diagram-plan.json"
OUT    = BASE / "diagrams.json"
MMD_DIR = BASE / "diagrams"


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def sanitize_id(text: str) -> str:
    """Make a safe Mermaid node ID."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', text.lower())[:40]


def sanitize_label(text: str) -> str:
    """Make a safe Mermaid label."""
    return text.replace('"', "'").replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')[:60]


# ---------------------------------------------------------------------------
# Diagram generators
# ---------------------------------------------------------------------------

def generate_flowchart(plan: dict, guide: dict) -> str:
    """Generate a primary flowchart Mermaid definition."""
    steps = plan.get("step_transitions", [])
    raw_steps = plan.get("diagrams", [{}])[0].get("elements", []) if plan.get("diagrams") else []

    # Use step_transitions for edges
    lines = ["flowchart TD"]
    lines.append("    %% Nodes")
    node_ids = {}
    for i, t in enumerate(steps):
        sid = sanitize_id(t["from"])
        node_ids[t["from"]] = sid

    # Add all elements as nodes
    all_elements = []
    for diag in plan.get("diagrams", []):
        all_elements.extend(diag.get("elements", []))

    # Draw step nodes
    for step in raw_steps:
        sid = sanitize_id(step) if isinstance(step, str) else sanitize_id(step.get("id", "step"))
        label = sanitize_label(step if isinstance(step, str) else step.get("name", "Step"))
        lines.append(f"    {sid}([{label}])")

    # Draw transitions
    for t in steps:
        fid = sanitize_id(t["from"])
        tid = sanitize_id(t["to"])
        label = sanitize_label(t.get("label", ""))
        if label:
            lines.append(f"    {fid} -->|{label}| {tid}")
        else:
            lines.append(f"    {fid} --> {tid}")

    # Add decision diamonds if decision_points exist
    for dp in plan.get("decision_points", []):
        did = sanitize_id(dp.get("id", "decision"))
        dname = sanitize_label(dp.get("name", "Decision"))
        lines.append(f"    {did}{{{{{dname}}}}}")

    return "\n".join(lines)


def generate_sequence(plan: dict, guide: dict) -> str:
    """Generate a sequence diagram."""
    decisions = plan.get("decision_points", [])
    route_outs = plan.get("route_outs", [])

    actors = []
    actor_ids = []
    for d in decisions:
        name = d.get("name", "Actor")[:20]
        aid = sanitize_id(name)
        actors.append(name)
        actor_ids.append(aid)
    for r in route_outs:
        target = r.get("target", "Target")[:20]
        tid = sanitize_id(target)
        if tid not in actor_ids:
            actors.append(target)
            actor_ids.append(tid)

    if not actor_ids:
        actor_ids = ["Actor1", "Actor2"]
        actors = ["Actor 1", "Actor 2"]

    lines = ["sequenceDiagram"]
    for aid, name in zip(actor_ids, actors):
        lines.append(f"    participant {aid} as {name}")

    # Add message sequence
    for i, (aid, name) in enumerate(zip(actor_ids[:-1], actors[:-1])):
        next_aid = actor_ids[i+1]
        lines.append(f"    {aid}->>+{next_aid}: step {i+1}")

    return "\n".join(lines)


def generate_state(plan: dict, guide: dict) -> str:
    """Generate a state diagram."""
    steps = plan.get("diagrams", [{}])[0].get("elements", []) if plan.get("diagrams") else []
    terminals = plan.get("terminal_states", [])

    lines = ["stateDiagram-v2"]
    lines.append("    [*] --> Start")

    step_names = []
    for step in steps:
        if isinstance(step, str):
            step_names.append(step)
        elif isinstance(step, dict):
            step_names.append(step.get("name", "Step"))

    for i, name in enumerate(step_names):
        sid = sanitize_id(name)
        lines.append(f"    state \"{sanitize_label(name)}\" as {sid}")

    # Connect states linearly
    for i in range(len(step_names) - 1):
        lines.append(f"    {sanitize_id(step_names[i])} --> {sanitize_id(step_names[i+1])}")

    # Terminal states
    for t in terminals:
        tid = sanitize_id(t.get("id", "terminal"))
        tname = sanitize_label(t.get("name", "End"))
        lines.append(f"    {sanitize_id(step_names[-1] if step_names else 'Start')} --> {tid}: {tname}")

    lines.append(f"    {sanitize_id(step_names[-1] if step_names else 'Start')} --> [*]")
    return "\n".join(lines)


def generate_class(plan: dict, guide: dict) -> str:
    """Generate a class diagram."""
    artifacts = plan.get("artifacts", [])
    steps = plan.get("diagrams", [{}])[0].get("elements", []) if plan.get("diagrams") else []

    lines = ["classDiagram"]

    # Create classes for artifacts
    for a in artifacts:
        name = a.get("name", "Class")
        cid = sanitize_id(name)
        lines.append(f"    class {cid} {{")
        lines.append(f"        +{name}")
        lines.append(f"    }}")

    # If no artifacts, derive from steps
    if not artifacts:
        for step in steps[:4]:  # limit to 4 classes
            if isinstance(step, str):
                name = step
            elif isinstance(step, dict):
                name = step.get("name", "Class")
            cid = sanitize_id(name)
            lines.append(f"    class {cid} {{")
            lines.append(f"        +name: str")
            lines.append(f"        +execute()")
            lines.append(f"    }}")

    # Add relationships
    for i in range(len(artifacts) - 1):
        lines.append(f"    {sanitize_id(artifacts[i].get('name', 'A'))} ..> {sanitize_id(artifacts[i+1].get('name', 'B'))}")

    return "\n".join(lines)


def generate_error_path(plan: dict, guide: dict) -> str:
    """Generate an error-path / failure flow diagram."""
    route_outs = plan.get("route_outs", [])
    terminals = plan.get("terminal_states", [])
    steps = plan.get("diagrams", [{}])[0].get("elements", []) if plan.get("diagrams") else []

    lines = ["flowchart TB"]
    lines.append("    %% Error/failure paths")

    # Start
    lines.append("    start[Start]")

    for step in steps[:5]:
        sid = sanitize_id(step if isinstance(step, str) else step.get("id", "step"))
        sname = sanitize_label(step if isinstance(step, str) else step.get("name", "Step"))
        lines.append(f"    {sid}[{sname}]")

    # Error nodes
    for r in route_outs:
        rid = sanitize_id(r.get("id", "route"))
        rtarget = sanitize_label(r.get("target", "fallback"))
        lines.append(f"    {rid}((\"⚠ {rtarget}\"))")

    # Terminal error states
    for t in terminals:
        tid = sanitize_id(t.get("id", "terminal"))
        tname = sanitize_label(t.get("name", "Failed"))
        lines.append(f"    {tid}[(✗ {tname})]")

    lines.append("    start --> " + (sanitize_id(steps[0]) if steps else "start"))

    return "\n".join(lines)


GENERATORS = {
    "flowchart": generate_flowchart,
    "sequence": generate_sequence,
    "state": generate_state,
    "class": generate_class,
    "error-path": generate_error_path,
}


def generate_diagram(diagram_type: str, plan: dict, guide: dict) -> str:
    """Generate Mermaid content for a given diagram type."""
    gen = GENERATORS.get(diagram_type, generate_flowchart)
    return gen(plan, guide)


def main() -> None:
    if not GUIDES.exists():
        print(f"ERROR: {GUIDES} not found. Run Stage D first.", file=sys.stderr)
        sys.exit(1)
    if not PLAN.exists():
        print(f"ERROR: {PLAN} not found. Run Stage C first.", file=sys.stderr)
        sys.exit(1)

    guides_data = load_json(GUIDES)
    plan_data = load_json(PLAN)

    plan_diagrams = plan_data.get("diagrams", [])
    guides_list = guides_data.get("guides", [])

    MMD_DIR.mkdir(exist_ok=True)

    diagrams = []
    for diag_plan in plan_diagrams:
        diagram_id = diag_plan.get("diagram_id", "")
        diagram_type = diag_plan.get("diagram_type", "flowchart")

        # Find matching guide
        guide = next(
            (g for g in guides_list if g.get("diagram_id") == diagram_id),
            {"mermaid_hints": {}, "palette_hint": "tailwind-modern"}
        )

        mmd_content = generate_diagram(diagram_type, plan_data, guide)
        mmd_file = MMD_DIR / f"{diagram_id}.mmd"
        mmd_file.write_text(mmd_content, encoding="utf-8")

        diagrams.append({
            "diagram_id": diagram_id,
            "diagram_type": diagram_type,
            "mmd_file": str(mmd_file.name),
            "mmd_content": mmd_content,
            "palette_hint": diag_plan.get("palette_hint", "tailwind-modern"),
            "caption": diag_plan.get("caption", ""),
            "role": diag_plan.get("role", ""),
            "guide_file": diag_plan.get("guide_file", ""),
            "elements": diag_plan.get("elements", [])
        })

    result = {
        "kind": "diagrams",
        "version": "1.0.0",
        "diagrams_count": len(diagrams),
        "diagrams": diagrams,
        "source_model_ref": plan_data.get("source_model_ref", "")
    }

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Stage E: PASS — {len(diagrams)} diagrams generated")
    for d in diagrams:
        print(f"  {d['diagram_id']} ({d['diagram_type']}) -> {d['mmd_file']}")
    print(f"Written: {OUT}")
    print(f"Written: {len(diagrams)} .mmd files to {MMD_DIR}")
    sys.exit(0)


if __name__ == "__main__":
    main()