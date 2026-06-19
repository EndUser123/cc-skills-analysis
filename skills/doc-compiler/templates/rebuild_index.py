#!/usr/bin/env python3
"""Rebuild index.html from extracted template files."""
import os

BASE = "P:/packages/cc-skills-meta/skills/doc-compiler"
TPL = f"{BASE}/templates"

def read(name):
    with open(f"{TPL}/{name}") as f:
        return f.read()

def read_css(name):
    return read(name).strip()

# ── Build <style> block ─────────────────────────────────────────────────────
css_parts = [
    read_css("shared-css.css"),
    read_css("toc-css.css"),
    read_css("section-css.css"),
    read_css("diagram-css.css"),
]

# ── Assemble body sections in order ──────────────────────────────────────
section_order = [
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

body_parts = [read(name) for name in section_order]

# ── Script blocks ────────────────────────────────────────────────────────────
shared_js = read("shared-scripts.js")
diagram_js = read("diagram-scripts.js")

# ── Head section ───────────────────────────────────────────────────────────
# base-shell.html has </head> split across two lines:
#   line 10: "  </head"  (newline stripped by strip())
#   line 11: ">  " (the '>' from </head> plus trailing content)
# We reconstruct a proper head by taking lines 0-8 (first 9 lines) and adding
# a clean "</head>" closing tag.
base = read("base-shell.html")
base_lines = base.split("\n")
head_lines = base_lines[:9]  # lines 1-9 (0-indexed): DOCTYPE through last link
head_lines.append("  </head>")  # proper closing tag on its own line

# toc.html
toc_html = read("toc.html")

# ── Assemble ───────────────────────────────────────────────────────────────
lines = []

# Head (properly formatted)
for hl in head_lines:
    lines.append(hl)

# Style block inside <head>
lines.append("  <style>")
for css in css_parts:
    for cl in css.split("\n"):
        lines.append("    " + cl)
lines.append("  </style>")

# Body open
lines.append("<body>")
lines.append('<button id="tocToggle" aria-label="Toggle table of contents" title="Toggle TOC" aria-expanded="true">☰</button>')
lines.append('<div class="page-shell">')

# TOC sidebar
for tl in toc_html.strip().split("\n"):
    lines.append("  " + tl)

# Main content sections
lines.append('  <div class="main-content">')
for bp in body_parts:
    for bl in bp.strip().split("\n"):
        lines.append("    " + bl)
lines.append("  </div><!-- .main-content -->")
lines.append("</div><!-- .page-shell -->")

# Scripts
lines.append('<script type="module">')
for jl in shared_js.strip().split("\n"):
    lines.append("  " + jl)
lines.append('</script>')

lines.append('<script type="module">')
for jl in diagram_js.strip().split("\n"):
    lines.append("  " + jl)
lines.append('</script>')

lines.append("</body>")
lines.append("</html>")

html = "\n".join(lines)

with open(f"{BASE}/index.html", "w") as f:
    f.write(html)

print(f"Rebuilt index.html ({len(html)} chars)")
