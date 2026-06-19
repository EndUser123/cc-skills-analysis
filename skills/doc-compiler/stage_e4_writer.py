#!/usr/bin/env python3
"""Stage E4: HTML Writer for doc-compiler.

Assembles the final index.html from filled templates and E3 output.
"""
import json, re, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
TPL  = BASE / "templates"

SECTION_ORDER = [
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


def read(name: str) -> str:
    return (BASE / name).read_text(encoding="utf-8")


def fill_base_shell(base: str, plan: dict) -> str:
    """Fill {{skill_name}} and {{version}} in base-shell.html."""
    name = plan.get("content_bindings", {}).get("name", "doc")
    version = plan.get("content_bindings", {}).get("version", "0.0.0")
    result = base.replace("{{skill_name}}", name).replace("{{version}}", version)
    return result


def main() -> None:
    # Gate: E1, E2, E3 must all pass
    for stage, path in [("E1", BASE / "e1-output.json"),
                      ("E2", BASE / "e2-output.json"),
                      ("E3", BASE / "e3-output.json")]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "pass":
            print(f"{stage} must pass before E4 can run")
            sys.exit(1)

    plan = json.loads((BASE / "artifact-plan.json").read_text(encoding="utf-8"))

    # Load assembled CSS and JS
    css_block = read("e3_css_block.css")
    js_block  = read("e3_js_block.js")

    # Load and fill base-shell.html
    base = read("templates/base-shell.html")
    base = fill_base_shell(base, plan)

    # Split base into head section and body start
    head_end = base.find("</head>")
    head_section = base[:head_end + len("</head>")] if head_end != -1 else ""

    # Body start: from <body> to end of base-shell
    body_start_match = re.search(r'<body>.*?<div class="page-shell">', base, re.DOTALL)
    body_start = body_start_match.group(0) if body_start_match else '<body>\n<button id="tocToggle">☰</button>\n<div class="page-shell">'

    # Load TOC
    toc_html = read("templates/toc.html")

    # Load filled section templates
    filled_sections: dict[str, str] = {}
    for name in SECTION_ORDER:
        try:
            filled_sections[name] = read(f"e2-filled_{name}")
        except FileNotFoundError:
            filled_sections[name] = read(f"templates/{name}")

    # Assemble HTML
    lines = []

    # Head + style block
    for hl in head_section.split("\n"):
        lines.append(hl)
    lines.append("  <style>")
    for cl in css_block.split("\n"):
        lines.append("    " + cl)
    lines.append("  </style>")

    # Body open + TOC
    for bl in body_start.split("\n"):
        lines.append(bl)
    for tl in toc_html.strip().split("\n"):
        lines.append("  " + tl)

    # Main content sections
    lines.append('  <div class="main-content">')
    for name in SECTION_ORDER:
        content = filled_sections.get(name, "")
        for cl in content.strip().split("\n"):
            lines.append("    " + cl)
    lines.append("  </div><!-- .main-content -->")
    lines.append("</div><!-- .page-shell -->")

    # Scripts
    lines.append('<script type="module">')
    for jl in js_block.split("\n"):
        lines.append("  " + jl)
    lines.append('</script>')

    lines.append("</body>")
    lines.append("</html>")

    html = "\n".join(lines)
    out_path = BASE / "index.html"
    out_path.write_text(html, encoding="utf-8")

    # Verify key DOM elements
    checks = {
        "doctype":          html.startswith("<!DOCTYPE html>"),
        "toc_toggle":       'id="tocToggle"' in html,
        "toc_element":       'id="toc"' in html and 'class="toc"' in html,
        "mermaid_source":   'id="mermaidSource"' in html,
        "resize_handle":     'id="diagramResizeHandle"' in html,
        "theme_toggle":     'id="themeToggle"' in html,
        "search_input":      'id="searchInput"' in html,
        "diagram_viewport":  'id="diagramViewport"' in html,
        "diagram_stage":     'id="diagramStage"' in html,
        "zoom_controls":     'id="zoomIn"' in html and 'id="zoomReset"' in html,
        "proof_summary":     'id="proof"' in html,
        "style_block":       "<style>" in html,
        "script_module":     '<script type="module">' in html,
        "steps_present":     html.count('class="step"') >= 1,
    }

    failed = [k for k, v in checks.items() if not v]

    slot_report = {}
    for name in SECTION_ORDER:
        filled = f"e2-filled_{name}"
        exists = (BASE / filled).exists()
        slot_report[name] = "filled" if exists else "template_only"

    output = {
        "stage": "E4",
        "status": "fail" if failed else "pass",
        "file_written": str(out_path),
        "file_size": len(html),
        "dom_checks": checks,
        "dom_failures": failed,
        "slot_fill_report": slot_report,
        "errors": [f"missing DOM element: {f}" for f in failed],
    }

    out_meta = BASE / "e4-output.json"
    out_meta.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"E4: {'PASS' if not failed else 'FAIL'} — {len(html)} chars, {len(html.splitlines())} lines")
    if failed:
        for f in failed:
            print(f"  FAIL: {f} missing")
        sys.exit(1)
    for k, v in checks.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"E4 written to {out_path}")


if __name__ == "__main__":
    main()
