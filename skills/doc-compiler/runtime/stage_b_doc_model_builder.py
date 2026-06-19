#!/usr/bin/env python3
"""Stage B: Documentation Model Builder for doc-compiler.

Reads source-model.json from Stage A and enriches it into a structured
documentation model with section bindings, content hints, and metadata.
Emits doc-model.json.

This model is consumed by Stage C (diagram strategy router) and
Stage H (template HTML emitter) — it is the central pipeline artifact.
"""
import json, sys
from pathlib import Path
from typing import Any

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
SOURCE = BASE / "source-model.json"
OUT    = BASE / "doc-model.json"


def classify_workflow_shape(steps: list, decision_points: list) -> str:
    """Classify the overall workflow shape for diagram routing."""
    if decision_points:
        return "decision-tree"
    step_count = len(steps)
    if step_count <= 2:
        return "linear-simple"
    if step_count <= 5:
        return "linear-multi"
    # Check for branching indicators in step names
    names = [s.get("name", "") for s in steps]
    branch_keywords = ["branch", "fork", "split", "parallel", "either", "or"]
    if any(kw.lower() in " ".join(names).lower() for kw in branch_keywords):
        return "branching"
    return "linear-long"


def assign_diagram_roles(steps: list, decisions: list, route_outs: list) -> list[dict]:
    """Assign diagram type roles to each workflow element."""
    roles = []
    step_names = [s.get("name", "") for s in steps]

    # Primary flowchart is almost always appropriate
    roles.append({
        "diagram_id": "diagram-primary",
        "role": "primary-flowchart",
        "elements": [s.get("id") for s in steps],
        "caption": "Workflow steps and transitions"
    })

    # Add sequence diagram if there are decision points or complex routing
    if decisions or any("->" in r.get("target", "") for r in route_outs):
        roles.append({
            "diagram_id": "diagram-sequence",
            "role": "sequence-interaction",
            "elements": [d.get("id") for d in decisions],
            "caption": "Decision flow sequence"
        })

    # Add error-path diagram if artifacts or terminal states exist
    if route_outs or len(steps) > 3:
        roles.append({
            "diagram_id": "diagram-error-path",
            "role": "error-path",
            "elements": [r.get("id") for r in route_outs],
            "caption": "Route-out and failure paths"
        })

    return roles


def extract_section_bindings(model: dict) -> list[dict[str, Any]]:
    """Build section bindings for the template HTML emitter."""
    steps = model.get("steps", [])
    decisions = model.get("decision_points", [])
    route_outs = model.get("route_outs", [])
    terminals = model.get("terminal_states", [])
    artifacts = model.get("artifacts", [])

    bindings = []

    # Hero / overview section
    bindings.append({
        "section_id": "overview",
        "template": "section-hero",
        "data_keys": ["name", "version", "description"],
        "required": True
    })

    # Facts section (key-value metadata)
    if model.get("triggers"):
        bindings.append({
            "section_id": "facts",
            "template": "section-facts",
            "data_keys": ["triggers", "enforcement", "status"],
            "required": False
        })

    # Diagram placeholder section (diagram-plan.json fills this)
    bindings.append({
        "section_id": "diagram",
        "template": "section-mermaid",
        "data_keys": ["diagram_plan_id"],
        "required": True
    })

    # Steps accordion
    if steps:
        bindings.append({
            "section_id": "steps",
            "template": "section-accordion",
            "data_keys": ["steps"],
            "step_ids": [s.get("id") for s in steps],
            "required": True
        })

    # Decision points (if any)
    if decisions:
        bindings.append({
            "section_id": "decisions",
            "template": "section-decision-list",
            "data_keys": ["decision_points"],
            "required": False
        })

    # Route outs
    if route_outs:
        bindings.append({
            "section_id": "route-outs",
            "template": "section-route-outs",
            "data_keys": ["route_outs"],
            "required": False
        })

    # Terminal states
    if terminals:
        bindings.append({
            "section_id": "terminals",
            "template": "section-terminal-list",
            "data_keys": ["terminal_states"],
            "required": False
        })

    # Artifacts
    if artifacts:
        bindings.append({
            "section_id": "artifacts",
            "template": "section-artifact-cards",
            "data_keys": ["artifacts"],
            "required": False
        })

    # Proof metadata section
    bindings.append({
        "section_id": "proof",
        "template": "section-proof",
        "data_keys": [],
        "required": True
    })

    return bindings


def build_doc_model(model: dict) -> dict:
    """Build the full documentation model from source model."""
    steps = model.get("steps", [])
    decisions = model.get("decision_points", [])
    route_outs = model.get("route_outs", [])
    terminals = model.get("terminal_states", [])
    artifacts = model.get("artifacts", [])

    workflow_shape = classify_workflow_shape(steps, decisions)
    diagram_roles = assign_diagram_roles(steps, decisions, route_outs)
    section_bindings = extract_section_bindings(model)

    # Assemble content hints from source model
    content_hints = {
        "kind": model.get("kind", "unknown"),
        "name": model.get("name", ""),
        "version": model.get("version", "0.0.0"),
        "description": model.get("description", ""),
        "enforcement": model.get("enforcement", "strict"),
        "status": model.get("status", "active"),
        "triggers": model.get("triggers", []),
        "steps": steps,
        "decision_points": decisions,
        "route_outs": route_outs,
        "terminal_states": terminals,
        "artifacts": artifacts,
        "gaps": model.get("gaps", []),
        "ambiguities": model.get("ambiguities", []),
    }

    return {
        "kind": "doc-model",
        "version": "1.0.0",
        "source_path": model.get("source_path", ""),
        "workflow_shape": workflow_shape,
        "diagram_roles": diagram_roles,
        "section_bindings": section_bindings,
        "content_hints": content_hints,
        "ui_config": {
            "palette": "tailwind-modern",
            "toc_width": "18rem",
            "toc_breakpoint": 960,
            "diagram_height_initial": 480,
            "diagram_height_min": 200,
            "diagram_height_max": 800,
        },
        "css_contract": {
            "toggle_position": "fixed",
            "toggle_left": "0",
            "toc_transition": "left",
            "no_transform_on_desktop": True,
            "toggle_outside_nav": True,
            "mobile_toggle_display": "flex",
        },
        "mermaid_config": {
            "curve": "basis",
            "nodeSpacing": 40,
            "rankSpacing": 50,
        },
        # Consumed by later stages
        "source_model_ref": str(SOURCE.resolve()),
        "artifacts_emitted": [],
    }


def main() -> None:
    if not SOURCE.exists():
        print(f"ERROR: {SOURCE} not found. Run Stage A first.", file=sys.stderr)
        sys.exit(1)

    try:
        model = json.loads(SOURCE.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"ERROR: failed to read {SOURCE}: {ex}", file=sys.stderr)
        sys.exit(1)

    doc_model = build_doc_model(model)

    OUT.write_text(json.dumps(doc_model, indent=2), encoding="utf-8")

    steps_count = len(doc_model["content_hints"]["steps"])
    decisions_count = len(doc_model["content_hints"]["decision_points"])
    diagrams_count = len(doc_model["diagram_roles"])
    sections_count = len(doc_model["section_bindings"])

    print(f"Stage B: PASS — doc-model built")
    print(f"  workflow_shape={doc_model['workflow_shape']}")
    print(f"  steps={steps_count}, decisions={decisions_count}")
    print(f"  diagrams={diagrams_count}, sections={sections_count}")
    print(f"Written: {OUT}")
    sys.exit(0)


if __name__ == "__main__":
    main()