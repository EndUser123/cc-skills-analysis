#!/usr/bin/env python3
"""Stage E3: Style-Aware CSS/JS Assembler for doc-compiler.

Loads style-specific CSS/JS overrides first, then falls back to shared.
Inlines the resolved Mermaid palette.
Output: e3-output.json (with css_block and js_block strings)
"""
import json, sys
from pathlib import Path

BASE  = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
TPL   = BASE / "templates"
STYLES_DIR = TPL / "styles"
E2_OUT = BASE / "e2-output.json"
PALETTES_FILE = TPL / "mermaid-palettes.json"

# Canonical CSS load order (shared base layer first)
SHARED_CSS = ["shared-css.css", "toc-css.css", "section-css.css", "diagram-css.css"]
SHARED_JS  = ["shared-scripts.js", "diagram-scripts.js"]

# Style CSS overrides — style folder wins, shared is fallback
STYLE_CSS_MAP = {
    "deepwiki": ["styles/deepwiki.css"],
    "product":  ["styles/product.css"],
    "minimal":  ["styles/minimal.css"],
}
STYLE_JS_MAP = {
    "deepwiki": [],
    "product":  [],
    "minimal":  [],
}


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def read(name: str, style: str | None = None) -> str:
    """Read a file from style folder first, then shared templates/."""
    if style:
        style_path = STYLES_DIR / f"{style}.css"
        if style_path.exists():
            return style_path.read_text(encoding="utf-8")
    return (TPL / name).read_text(encoding="utf-8")


def read_optional(name: str, style: str | None = None) -> tuple[str | None, str]:
    """Read a file returning (content, source). Returns (None, '') if absent."""
    if style:
        # Style CSS overlay lives at STYLES_DIR/{style}.css
        sp = STYLES_DIR / f"{style}.css"
        if sp.exists():
            return sp.read_text(encoding="utf-8"), f"style/{style}.css"
    sp = TPL / name
    if sp.exists():
        return sp.read_text(encoding="utf-8"), f"shared/{name}"
    return None, ""


def assemble_css(style: str | None) -> tuple[str, list[str]]:
    """Assemble CSS block: shared base layer + optional style override."""
    parts: list[str] = []
    order: list[str] = []

    for name in SHARED_CSS:
        content = read(name, style=None)
        parts.append(content.strip())
        order.append(f"shared/{name}")

    # Style-specific CSS overlay (adds on top of shared)
    if style and style in STYLE_CSS_MAP:
        for name in STYLE_CSS_MAP[style]:
            content, src = read_optional(name, style=style)
            if content:
                parts.append(content.strip())
                order.append(src)

    return "\n\n".join(parts), order


def assemble_js(style: str | None) -> tuple[str, list[str]]:
    """Assemble JS block: shared base layer + optional style override."""
    parts: list[str] = []
    order: list[str] = []

    for name in SHARED_JS:
        content = read(name, style=None)
        parts.append(content.strip())
        order.append(f"shared/{name}")

    if style and style in STYLE_JS_MAP:
        for name in STYLE_JS_MAP[style]:
            content, src = read_optional(name, style=style)
            if content:
                parts.append(content.strip())
                order.append(src)

    return "\n\n".join(parts), order


def main() -> None:
    e2 = load_json(E2_OUT)
    if e2.get("status") != "pass":
        print("E2 must pass before E3 can run")
        sys.exit(1)

    plan = load_json(BASE / "artifact-plan.json")

    errors: list[str] = []

    # Resolve style from plan or CLI
    style = None
    style = sys.argv[2] if len(sys.argv) > 2 else None
    if not style:
        style = plan.get("presentation", {}).get("style") or plan.get("style")

    # CSS
    css_block, css_order = assemble_css(style)

    # JS
    js_block, js_order = assemble_js(style)

    # Inline selected palette
    palette_name = plan.get("ui_config", {}).get("palette", "tailwind-modern")
    try:
        palettes = json.loads(read("mermaid-palettes.json"))
    except Exception as ex:
        errors.append(f"failed to load palettes: {ex}")
        palettes = {}

    if palette_name not in palettes:
        errors.append(f"palette '{palette_name}' not in mermaid-palettes.json")
    else:
        palette_data = palettes[palette_name]
        palettes_json = json.dumps(palette_data, indent=2)
        palettes_inject = f"const PALETTES = {palettes_json};"
        js_block = palettes_inject + "\n\n" + js_block

    # Verify required DOM IDs are not stripped by style CSS
    # (These IDs live in base-shell; style CSS should only affect visual styling.)
    missing = [rid for rid in ["tocToggle", "themeToggle", "searchInput", "diagramViewport",
                               "diagramStage", "zoomIn", "zoomReset", "diagramResizeHandle"]
               if rid not in css_block and rid not in js_block and rid not in read("base-shell.html", style=style)]
    if missing:
        errors.append(f"DOM ID references may be stripped in CSS/JS: {missing}")

    output = {
        "stage": "E3",
        "status": "fail" if errors else "pass",
        "style": style or "deepwiki",
        "css_parts": css_order,
        "js_parts": js_order,
        "palette_inlined": palette_name if not errors else None,
        "css_size": len(css_block),
        "js_size": len(js_block),
        "errors": errors,
    }

    out_path = BASE / "e3-output.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    (BASE / "e3_css_block.css").write_text(css_block, encoding="utf-8")
    (BASE / "e3_js_block.js").write_text(js_block, encoding="utf-8")

    print(f"E3: {'PASS' if not errors else 'FAIL'} — CSS {len(css_block)} chars, JS {len(js_block)} chars, style={style}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    print(f"E3 written to {out_path}")


if __name__ == "__main__":
    main()
