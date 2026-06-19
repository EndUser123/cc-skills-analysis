#!/usr/bin/env python3
"""Stage G: Artifact Plan Builder for doc-compiler.

Reads doc-model.json (Stage B) and diagrams.json (Stage E).
Produces the rendering instruction set for Stage H (HTML emitter).
Emits artifact-plan.json.

This is distinct from Stage B — B builds the documentation model, G
builds the rendering plan (which sections, which templates, which bindings).
"""
import json, sys
from pathlib import Path
from typing import Any

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
DOC_MODEL = BASE / "doc-model.json"
DIAGRAMS   = BASE / "diagrams.json"
SOURCE     = Path(__file__).parent / "source-model.json"
OUT        = BASE / "artifact-plan.json"


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def build_section_map(doc_model: dict) -> list[dict[str, Any]]:
    """Build the ordered list of section rendering instructions."""
    bindings = doc_model.get("section_bindings", [])
    section_map = []

    for binding in bindings:
        section_id = binding.get("section_id", "")
        template = binding.get("template", "")
        required = binding.get("required", False)

        section_map.append({
            "section_id": section_id,
            "template": template,
            "data_keys": binding.get("data_keys", []),
            "required": required,
            "render": True
        })

    return section_map


def build_mermaid_config(diagrams_data: dict, doc_model: dict) -> dict:
    """Build the Mermaid configuration from diagram plan."""
    diagrams = diagrams_data.get("diagrams", [])
    ui_config = doc_model.get("ui_config", {})

    # Collect all .mmd file references
    mmd_files = []
    for diag in diagrams:
        mmd_file = diag.get("mmd_file", "")
        if mmd_file:
            mmd_files.append(mmd_file)

    return {
        "curve": "basis",
        "nodeSpacing": 40,
        "rankSpacing": 50,
        "mmd_files": mmd_files,
        "primary_diagram": mmd_files[0] if mmd_files else "",
        "diagram_count": len(mmd_files)
    }


def build_content_bindings(source_model: dict, doc_model: dict) -> dict:
    """Build the content bindings from source + doc models."""
    content_hints = doc_model.get("content_hints", {})

    return {
        "name": content_hints.get("name", ""),
        "version": content_hints.get("version", "0.0.0"),
        "description": content_hints.get("description", ""),
        "kind": content_hints.get("kind", "skill"),
        "enforcement": content_hints.get("enforcement", "strict"),
        "status": content_hints.get("status", "active"),
        "triggers": content_hints.get("triggers", []),
        "steps": content_hints.get("steps", []),
        "decision_points": content_hints.get("decision_points", []),
        "route_outs": content_hints.get("route_outs", []),
        "terminal_states": content_hints.get("terminal_states", []),
        "artifacts": content_hints.get("artifacts", []),
        "gaps": content_hints.get("gaps", []),
        "ambiguities": content_hints.get("ambiguities", [])
    }


def build_css_contract(doc_model: dict) -> dict:
    """Build the CSS contract enforcement rules."""
    return doc_model.get("css_contract", {
        "toggle_position": "fixed",
        "toggle_left": "0",
        "toc_transition": "left",
        "no_transform_on_desktop": True,
        "toggle_outside_nav": True,
        "mobile_toggle_display": "flex"
    })


def main() -> None:
    if not DOC_MODEL.exists():
        print(f"ERROR: {DOC_MODEL} not found. Run Stage B first.", file=sys.stderr)
        sys.exit(1)
    if not DIAGRAMS.exists():
        print(f"ERROR: {DIAGRAMS} not found. Run Stage E first.", file=sys.stderr)
        sys.exit(1)

    doc_model = load_json(DOC_MODEL)
    diagrams_data = load_json(DIAGRAMS)
    source_model = load_json(SOURCE)

    section_map = build_section_map(doc_model)
    mermaid_config = build_mermaid_config(diagrams_data, doc_model)
    content_bindings = build_content_bindings(source_model, doc_model)
    css_contract = build_css_contract(doc_model)

    plan = {
        "template": "default-docs-v1",
        "template_version": "v1",
        "page_structure": {
            "sections": section_map
        },
        "ui_config": doc_model.get("ui_config", {}),
        "mermaid_source": "",
        "mermaid_config": mermaid_config,
        "toc_config": {
            "width": doc_model.get("ui_config", {}).get("toc_width", "18rem"),
            "breakpoint": doc_model.get("ui_config", {}).get("toc_breakpoint", 960)
        },
        "css_contract": css_contract,
        "content_bindings": content_bindings,
        "workflow_shape": doc_model.get("workflow_shape", "unknown"),
        "diagram_roles": doc_model.get("diagram_roles", []),
        "gaps": doc_model.get("content_hints", {}).get("gaps", []),
        "ambiguities": doc_model.get("content_hints", {}).get("ambiguities", []),
        "presentation": source_model.get("presentation", {"style": "default", "source": "default"}),
    }

    OUT.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    section_count = len(section_map)
    steps_count = len(content_bindings.get("steps", []))
    mmd_count = mermaid_config.get("diagram_count", 0)

    print(f"Stage G: PASS — artifact plan built")
    print(f"  sections={section_count}, steps={steps_count}, diagrams={mmd_count}")
    print(f"  workflow_shape={plan['workflow_shape']}")
    print(f"Written: {OUT}")
    sys.exit(0)


if __name__ == "__main__":
    main()