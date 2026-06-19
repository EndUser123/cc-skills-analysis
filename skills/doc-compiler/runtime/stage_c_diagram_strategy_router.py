#!/usr/bin/env python3
"""Stage C: Diagram Strategy Router for doc-compiler.

Reads doc-model.json from Stage B and route_outs from source model.
Applies selection rules (references/guides/selection-rules.md) to decide
which diagram types to generate for each diagram role.
Emits diagram-plan.json and diagram-guides.json.

Multi-diagram routing logic:
- Primary flowchart: always generated
- Sequence diagram: generated if decision_points exist OR route_outs present
- State diagram: generated if workflow_shape == "decision-tree" OR
  step names contain lifecycle keywords
- Class diagram: generated if kind == "plugin" OR artifacts present
- Error-path diagram: generated if route_outs exist OR terminal_states present
"""
import json, re, sys
from pathlib import Path
from typing import Any

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
DOC_MODEL = BASE / "doc-model.json"
OUT_PLAN  = BASE / "diagram-plan.json"
OUT_GUIDES = BASE / "diagram-guides.json"
GUIDES_DIR = BASE / "references" / "guides"

LIFECYCLE_KEYWORDS = [
    "lifecycle", "state", "status", "phase", "stage",
    "ready", "pending", "waiting", "blocked", "approved",
    "rejected", "completed", "failed", "retry"
]


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def classify_step_type(name: str, description: str = "") -> str:
    """Classify a step's semantic role for diagram routing."""
    combined = f"{name} {description}".lower()
    if any(kw in combined for kw in ["validate", "check", "verify", "gate", "assert"]):
        return "validation"
    if any(kw in combined for kw in ["build", "create", "generate", "emit", "write"]):
        return "creation"
    if any(kw in combined for kw in ["route", "delegate", "invoke", "call", "handoff"]):
        return "delegation"
    if any(kw in combined for kw in ["error", "fail", "catch", "except"]):
        return "error-handling"
    if any(kw in combined for kw in ["input", "read", "parse", "extract"]):
        return "input"
    if any(kw in combined for kw in ["output", "send", "return", "deliver"]):
        return "output"
    return "process"


def determine_diagram_types(model: dict) -> list[dict[str, Any]]:
    """Determine which diagram types to generate based on doc-model."""
    steps = model.get("content_hints", {}).get("steps", [])
    decisions = model.get("content_hints", {}).get("decision_points", [])
    route_outs = model.get("content_hints", {}).get("route_outs", [])
    terminals = model.get("content_hints", {}).get("terminal_states", [])
    artifacts = model.get("content_hints", {}).get("artifacts", [])
    kind = model.get("content_hints", {}).get("kind", "skill")
    workflow_shape = model.get("workflow_shape", "linear-long")

    diagrams = []
    step_ids = [s.get("id") for s in steps]
    decision_ids = [d.get("id") for d in decisions]
    route_ids = [r.get("id") for r in route_outs]

    # Always generate primary flowchart
    diagrams.append({
        "diagram_id": "diagram-primary",
        "diagram_type": "flowchart",
        "guide_file": "flowchart-guide.md",
        "role": "primary-flowchart",
        "elements": step_ids,
        "caption": f"{model.get('content_hints', {}).get('name', 'Workflow')} — step flow",
        "palette_hint": "tailwind-modern"
    })

    # Sequence diagram: decision points OR route_outs present
    if decisions or route_outs:
        diagrams.append({
            "diagram_id": "diagram-sequence",
            "diagram_type": "sequence",
            "guide_file": "sequence-guide.md",
            "role": "sequence-interaction",
            "elements": decision_ids + route_ids,
            "caption": "Decision flow and routing interactions",
            "palette_hint": "nord"
        })

    # State diagram: decision-tree shape OR lifecycle keywords in step names
    step_names_text = " ".join([s.get("name", "") for s in steps]).lower()
    has_lifecycle = any(kw in step_names_text for kw in LIFECYCLE_KEYWORDS)
    if workflow_shape == "decision-tree" or has_lifecycle:
        diagrams.append({
            "diagram_id": "diagram-state",
            "diagram_type": "state",
            "guide_file": "state-guide.md",
            "role": "state-machine",
            "elements": step_ids,
            "caption": "Workflow state transitions",
            "palette_hint": "one-dark-pro"
        })

    # Class diagram: plugin kind OR artifacts present
    if kind == "plugin" or artifacts:
        diagrams.append({
            "diagram_id": "diagram-class",
            "diagram_type": "class",
            "guide_file": "class-guide.md",
            "role": "domain-structure",
            "elements": [a.get("name", "") for a in artifacts] if artifacts else step_ids[:3],
            "caption": "Domain model and artifact relationships",
            "palette_hint": "dracula"
        })

    # Error-path diagram: route_outs present OR terminal_states
    if route_outs or terminals:
        diagrams.append({
            "diagram_id": "diagram-error-path",
            "diagram_type": "error-path",
            "guide_file": "error-paths.md",
            "role": "error-path",
            "elements": route_ids + [t.get("id") for t in terminals],
            "caption": "Failure paths, retries, and escalations",
            "palette_hint": "material-ocean"
        })

    return diagrams


def build_step_transitions(steps: list) -> list[dict]:
    """Extract transitions between steps for flowchart rendering."""
    transitions = []
    for i, step in enumerate(steps):
        step_id = step.get("id", f"step-{i+1}")
        routes_to = step.get("routes_to", [])
        if routes_to:
            for target in routes_to:
                transitions.append({
                    "from": step_id,
                    "to": target,
                    "label": step.get("name", "")[:30]
                })
        elif i + 1 < len(steps):
            transitions.append({
                "from": step_id,
                "to": steps[i+1].get("id", f"step-{i+2}"),
                "label": ""
            })
    return transitions


def build_sequence_actors(decisions: list, route_outs: list) -> list[str]:
    """Build actor list for sequence diagram."""
    actors = []
    for d in decisions:
        name = d.get("name", "")[:20]
        if name and name not in actors:
            actors.append(name)
    for r in route_outs:
        target = r.get("target", "")[:20]
        if target and target not in actors:
            actors.append(target)
    if not actors:
        actors = ["Actor"]
    return actors


def main() -> None:
    if not DOC_MODEL.exists():
        print(f"ERROR: {DOC_MODEL} not found. Run Stage B first.", file=sys.stderr)
        sys.exit(1)

    model = load_json(DOC_MODEL)
    diagrams = determine_diagram_types(model)

    # Build diagram-plan.json
    steps = model.get("content_hints", {}).get("steps", [])
    decisions = model.get("content_hints", {}).get("decision_points", [])
    route_outs = model.get("content_hints", {}).get("route_outs", [])
    terminals = model.get("content_hints", {}).get("terminal_states", [])
    artifacts = model.get("content_hints", {}).get("artifacts", [])

    diagram_plan = {
        "kind": "diagram-plan",
        "version": "1.0.0",
        "workflow_shape": model.get("workflow_shape", "unknown"),
        "diagrams": diagrams,
        "step_transitions": build_step_transitions(steps),
        "decision_points": decisions,
        "route_outs": route_outs,
        "terminal_states": terminals,
        "artifacts": artifacts,
        "source_model_ref": model.get("source_model_ref", ""),
    }

    # Build diagram-guides.json — which guide to apply per diagram
    diagram_guides = []
    for diag in diagrams:
        guide_path = GUIDES_DIR / diag["guide_file"]
        guide_content = ""
        if guide_path.exists():
            guide_content = guide_path.read_text(encoding="utf-8")

        diagram_guides.append({
            "diagram_id": diag["diagram_id"],
            "diagram_type": diag["diagram_type"],
            "guide_file": diag["guide_file"],
            "guide_content": guide_content,
            "palette_hint": diag["palette_hint"]
        })

    OUT_PLAN.write_text(json.dumps(diagram_plan, indent=2), encoding="utf-8")
    OUT_GUIDES.write_text(json.dumps(diagram_guides, indent=2), encoding="utf-8")

    diagram_count = len(diagrams)
    type_counts = {}
    for d in diagrams:
        t = d["diagram_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"Stage C: PASS — {diagram_count} diagrams routed")
    for t, c in type_counts.items():
        print(f"  {t}: {c}")
    print(f"Written: {OUT_PLAN}")
    print(f"Written: {OUT_GUIDES}")
    sys.exit(0)


if __name__ == "__main__":
    main()