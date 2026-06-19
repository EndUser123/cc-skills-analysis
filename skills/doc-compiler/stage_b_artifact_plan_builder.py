#!/usr/bin/env python3
"""Stage B: Artifact Plan Builder for doc-compiler.

Reads source-model.json from Stage A and designs the page structure,
including style-aware presentation config.
Emits artifact-plan.json.
"""
import configparser, json, os, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
TPL  = BASE / "templates"
STYLES_DIR = TPL / "styles"
SOURCE = BASE / "source-model.json"
OUT    = BASE / "artifact-plan.json"

PALETTE_DEFAULT = "tailwind-modern"
TOC_WIDTH = "18rem"
TOC_BREAKPOINT = 960
DIAGRAM_HEIGHT_INIT = 480
DIAGRAM_HEIGHT_MIN = 200
DIAGRAM_HEIGHT_MAX = 800

# CLI override takes precedence; fall back to frontmatter or env var
def _resolve_style(model: dict | None = None) -> str:
    """Resolve style: CLI arg > env var > frontmatter hint > default."""
    if len(sys.argv) > 2:
        return sys.argv[2]
    style = os.environ.get("DOCC_STYLE", "")
    if style:
        return style
    if model:
        style = model.get("style", "") or ""
        if style:
            return style
    return "deepwiki"


def _load_preset(style: str) -> dict:
    presets_path = STYLES_DIR / "presets.ini"
    if not presets_path.exists():
        return {}
    cp = configparser.ConfigParser()
    try:
        cp.read_string(presets_path.read_text(encoding="utf-8"))
        if style in cp.sections():
            return dict(cp[style])
    except Exception:
        pass
    return {}


STYLE_DEFAULT = "deepwiki"

# -------------------------------------------------------------------------- #
#  SECTION ORDER by style
# -------------------------------------------------------------------------- #
SECTION_ORDERS = {
    "deepwiki": [
        "overview", "what-it-does", "pipeline", "stages",
        "validation", "artifacts", "filemap", "functions", "workflow", "appendix"
    ],
    "product": [
        "overview", "what-it-does", "workflow", "pipeline", "stages",
        "artifacts", "validation", "filemap", "functions", "appendix"
    ],
    "minimal": [
        "overview", "artifacts", "stages", "validation", "functions"
    ],
}
# Sections that need a full card/section wrapper
FULL_SECTIONS = {
    "overview", "what-it-does", "pipeline", "stages", "validation",
    "artifacts", "filemap", "functions", "workflow", "appendix", "proof"
}


def build_artifact_plan(model: dict, style: str = STYLE_DEFAULT) -> dict:
    """Build artifact-plan.json from source model.

    style controls section order, density, and presentation through
    the presentation config — it does NOT change the content_bindings.
    """
    steps = model.get("steps", [])
    route_outs = model.get("route_outs", [])
    terminal_states = model.get("terminal_states", [])
    artifacts = model.get("artifacts", [])

    step_ids = [s.get("id", f"step-{i}") for i, s in enumerate(steps, 1)]
    section_order = SECTION_ORDERS.get(style, SECTION_ORDERS[STYLE_DEFAULT])
    preset = _load_preset(style)
    # configparser returns values with surrounding whitespace; strip quotes too
    def _pv(key: str, default: str) -> str:
        val = preset.get(key, default).strip().strip('"').strip("'")
        return val if val else default

    section_defs = []
    for sid in section_order:
        if sid in FULL_SECTIONS:
            section_defs.append({"id": sid, "type": sid})

    return {
        "template": "default-docs-v2",
        "template_version": "v2",
        "presentation": {
            "style": style,
            "density": _pv("density", "dense"),
            "diagram_weight": _pv("diagram_weight", "normal"),
            "section_order": section_order,
            "proof_position": _pv("proof_position", "bottom"),
            "font_scale": float(_pv("font_scale", "1.0")),
            "card_padding": _pv("card_padding", "1rem"),
            "decorative_whitespace": _pv("decorative_whitespace", "false") == "true",
        },
        "page_structure": {
            "sections": section_defs
        },
        "ui_config": {
            "palette": PALETTE_DEFAULT,
            "toc_width": TOC_WIDTH,
            "toc_breakpoint": TOC_BREAKPOINT,
            "diagram_height_initial": DIAGRAM_HEIGHT_INIT,
            "diagram_height_min": DIAGRAM_HEIGHT_MIN,
            "diagram_height_max": DIAGRAM_HEIGHT_MAX
        },
        "mermaid_source": "",
        "mermaid_config": {"curve": "basis", "nodeSpacing": 40, "rankSpacing": 50},
        "toc_config": {"width": TOC_WIDTH, "breakpoint": TOC_BREAKPOINT},
        "css_contract": {
            "toggle_position": "fixed",
            "toggle_left": "0",
            "toc_transition": "left",
            "no_transform_on_desktop": True,
            "toggle_outside_nav": True,
            "mobile_toggle_display": "flex"
        },
        "content_bindings": {
            "name": model.get("name", ""),
            "version": model.get("version", ""),
            "description": model.get("description", ""),
            "steps": steps,
            "route_outs": route_outs,
            "terminal_states": terminal_states,
            "artifacts": artifacts
        }
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

    style = _resolve_style(model)
    if style not in SECTION_ORDERS:
        print(f"WARNING: unknown style '{style}', defaulting to deepwiki", file=sys.stderr)
        style = STYLE_DEFAULT

    gaps = model.get("gaps", [])
    ambiguities = model.get("ambiguities", [])

    plan = build_artifact_plan(model, style=style)

    if gaps or ambiguities:
        plan["gaps"] = gaps
        plan["ambiguities"] = ambiguities
        if ambiguities:
            print(f"WARNING: {len(ambiguities)} ambiguities recorded")

    OUT.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    steps_count = len(plan["content_bindings"]["steps"])
    print(f"Stage B: PASS — style={style}, {steps_count} steps")
    print(f"Written: {OUT}")
    sys.exit(0)


if __name__ == "__main__":
    main()
