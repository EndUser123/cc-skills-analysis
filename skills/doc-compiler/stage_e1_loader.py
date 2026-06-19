#!/usr/bin/env python3
"""Stage E1: Style-Aware Template Loader for doc-compiler.

Verifies template files exist — checking style-specific overrides first,
then falling back to shared templates/.  Required DOM IDs are validated
to ensure existing validators continue to pass.

Writes e1-output.json.
"""
import json, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
TPL  = BASE / "templates"
STYLES_DIR = TPL / "styles"
OUT = BASE / "e1-output.json"

# Shared templates (always required)
SHARED_TEMPLATES = [
    "base-shell.html",
    "toc.html",
    "shared-css.css",
    "toc-css.css",
    "section-css.css",
    "diagram-css.css",
    "shared-scripts.js",
    "diagram-scripts.js",
    "mermaid-palettes.json",
    "hero.html",
    "facts.html",
    "search-ui.html",
    "mermaid-panel.html",
    "steps-accordion.html",
    "route-outs.html",
    "terminals.html",
    "artifacts.html",
    "proof-summary.html",
]

# Required DOM IDs — these MUST exist in the final HTML regardless of style.
# Validators (stage F / static validator) check these exactly.
REQUIRED_DOM_IDS = [
    "tocToggle",
    "toc",
    "themeToggle",
    "searchInput",
    "clearSearch",
    "mermaidSource",
    "diagramViewport",
    "diagramStage",
    "zoomIn",
    "zoomOut",
    "zoomReset",
    "zoomFit",
    "zoomPct",
    "paletteSelect",
    "diagramResizeHandle",
    "diagramShell",
]

# Stage-specific template groups keyed by section type.
# Key: template name. Value: section type(s) that use it.
SECTION_TEMPLATES = {
    "hero.html":           "hero",
    "facts.html":          "quick-facts",
    "search-ui.html":      "search",
    "mermaid-panel.html":  "mermaid",
    "steps-accordion.html": "accordion",
    "route-outs.html":     "route-out-list",
    "terminals.html":       "terminal-list",
    "artifacts.html":      "artifact-cards",
    "proof-summary.html":  "proof-metadata",
}

STYLE_RESERVED_IDS = {
    "tocToggle", "toc", "themeToggle", "searchInput", "clearSearch",
    "mermaidSource", "diagramViewport", "diagramStage", "zoomIn", "zoomOut",
    "zoomReset", "zoomFit", "zoomPct", "paletteSelect", "diagramResizeHandle",
}


def read_template(name: str, style: str | None = None) -> tuple[str | None, str]:
    """Read a template, checking style-specific override first.

    Returns (content, source) where source is 'style/<style>/<name>' or 'shared/<name>'.
    """
    if style:
        style_path = STYLES_DIR / style / name
        if style_path.exists():
            return style_path.read_text(encoding="utf-8"), f"style/{style}/{name}"
    shared_path = TPL / name
    if shared_path.exists():
        return shared_path.read_text(encoding="utf-8"), f"shared/{name}"
    return None, ""


def validate_dom_ids(template_content: str) -> list[str]:
    """Return list of missing required DOM IDs found in assembled shell."""
    missing = []
    for rid in REQUIRED_DOM_IDS:
        if f'id="{rid}"' not in template_content and f"id='{rid}'" not in template_content:
            missing.append(rid)
    return missing


def main() -> None:
    # Resolve style from DOCC_STYLE env var (CLI override) or from artifact-plan.json.
    style = None
    plan_path = BASE / "artifact-plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            style = plan.get("presentation", {}).get("style") or plan.get("style")
        except Exception:
            pass
    style = sys.argv[2] if len(sys.argv) > 2 else (style or None)

    valid_styles = _load_valid_styles()
    if style and style not in valid_styles:
        print(f"WARNING: style '{style}' not in presets; proceeding with shared templates", file=sys.stderr)
        style = None
    elif not style:
        style = "deepwiki"  # default when none specified

    errors: list[str] = []
    templates_loaded: dict[str, str] = {}
    missing_ids: list[str] = []

    # Load shared templates
    for name in SHARED_TEMPLATES:
        content, source = read_template(name, style=None)
        if content is None:
            errors.append(f"missing shared template: {name}")
        else:
            templates_loaded[name] = source

    # Load style-specific section templates (override shared)
    for name in SECTION_TEMPLATES:
        content, source = read_template(name, style=style)
        if content is not None:
            templates_loaded[name] = f"{source} (override)"
        # If style file absent, the shared entry already loaded is fine.

    # Verify base-shell.html includes all required DOM IDs
    shell_content, _ = read_template("base-shell.html", style=style)
    if shell_content:
        missing_ids = validate_dom_ids(shell_content)
        if missing_ids:
            errors.append(f"base-shell missing required IDs: {missing_ids}")
    else:
        errors.append("base-shell.html not found (shared or style-specific)")

    output = {
        "stage": "E1",
        "status": "pass" if not errors else "fail",
        "style_resolved": style,
        "template_version": "v2",  # bumped for style-awareness
        "templates_loaded": templates_loaded,
        "errors": errors,
    }

    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    n = len([v for v in templates_loaded.values() if v])
    print(f"E1: {'PASS' if not errors else 'FAIL'} — {n}/{len(SHARED_TEMPLATES)} shared templates, style={style}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    print(f"E1 written to {OUT}")


def _load_valid_styles() -> set[str]:
    presets_path = STYLES_DIR / "presets.ini"
    if not presets_path.exists():
        return set()
    import configparser
    cp = configparser.ConfigParser()
    try:
        cp.read_string(presets_path.read_text(encoding="utf-8"))
        return set(cp.sections())
    except Exception:
        return set()


if __name__ == "__main__":
    main()
