#!/usr/bin/env python3
"""Stage F: Static Structural Validator for doc-compiler index.html.

Runs S1-S19 checks from SKILL.md against the rebuilt index.html.
Emits static-validation.json.
"""

import json, re, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
HTML = BASE / "index.html"
OUT  = BASE / "static-validation.json"

def read_file(fname):
    return (BASE / fname).read_text(encoding="utf-8")

def fail(msg):
    print(f"  FAIL: {msg}", file=sys.stderr)

def pass_(msg):
    print(f"  PASS: {msg}")

def check(name, pred, details=""):
    result = "pass" if pred else "fail"
    msg = f"[{result.upper()}] {name}"
    if details:
        msg += f" — {details}"
    if pred:
        pass_(msg)
    else:
        fail(msg)
    return result

html = HTML.read_text(encoding="utf-8")

checks = []

def s(name, pred, details=""):
    r = check(name, pred, details)
    checks.append({"id": name, "result": r, "details": details or None})

print("\n=== Stage F: Static Validator ===\n")

# S1: #tocToggle as direct sibling of .page-shell
s("S1  tocToggle sibling",
  re.search(r'<button id="tocToggle"[^>]*>.*</button>\s*<div class="page-shell"', html, re.DOTALL) is not None,
  "tocToggle must be immediate sibling of .page-shell, NOT inside nav.toc")

# S2: nav#toc class="toc"
s("S2  nav#toc class=toc",
  re.search(r'<nav id="toc" class="toc"', html) is not None)

# S3: TOC CSS block exists
toc_css = re.search(r'\.toc\s*\{[^}]+\}', html, re.DOTALL)
s("S3  TOC CSS block exists", toc_css is not None)
if toc_css:
    css_text = toc_css.group(0)
    s("S4  position:fixed or absolute",
      "position" in css_text and ("fixed" in css_text or "absolute" in css_text))
    s("S5  left transition",
      "left" in css_text and "transition" in css_text)
    s("S6  no transform on desktop",
      "transform" not in css_text or "none" in css_text)

# S7: #mermaidSource with raw Mermaid text
s("S7  pre#mermaidSource present",
  re.search(r'<pre[^>]+id="mermaidSource"', html) is not None)
s("S7b mermaidSource not empty",
  re.search(r'<pre[^>]+id="mermaidSource"[^>]*>([^<]+)', html) is not None)

# S8: .diagram-shell display:flex; flex-direction:column
dg = re.search(r'\.diagram-shell\s*\{[^}]+\}', html, re.DOTALL)
s("S8  .diagram-shell CSS block", dg is not None)
if dg:
    s("S8b display:flex", "display" in dg.group(0) and "flex" in dg.group(0))
    s("S8c flex-direction:column", "flex-direction" in dg.group(0) and "column" in dg.group(0))

# S9: #diagramViewport min-height:200px
dv = re.search(r'\.diagram-viewport\s*\{[^}]+\}', html, re.DOTALL)
s("S9  .diagram-viewport CSS block", dv is not None)
if dv:
    s("S9b min-height:200px", "min-height" in dv.group(0) and "200px" in dv.group(0))

# S10: resize handle element
s("S10 diagram-resize-handle element",
  re.search(r'<div[^>]+id="diagramResizeHandle"', html) is not None)

# S11: resize handle CSS (cursor:ns-resize)
rh = re.search(r'\.diagram-resize-handle\s*\{[^}]+\}', html, re.DOTALL)
s("S11 resize-handle CSS block", rh is not None)
if rh:
    s("S11b cursor:ns-resize", "cursor" in rh.group(0) and "ns-resize" in rh.group(0))

# S12: accordion step elements
s("S12 article.step elements",
  html.count('class="step"') >= 1 or
  re.search(r'<article[^>]*class="[^"]*step[^"]*"', html) is not None)

# S13: #themeToggle inside .toc-header .toc-controls
s("S13 #themeToggle placement",
  re.search(r'class="toc-controls"[^>]*>\s*<button id="themeToggle"', html, re.DOTALL) is not None)

# S14: search UI (#searchInput)
s("S14 searchInput element",
  re.search(r'<input[^>]+id="searchInput"', html) is not None)

# S15-S19: Content-model binding
s("S15 source-model steps present",
  len(re.findall(r'class="step"', html)) >= 1)

s("S16 gate badges present",
  "gate-badge" in html or "gate-badge" in html)

s("S17 accordion toggle function",
  "toggleStep" in html and "step-header" in html)

s("S18 copy-to-clipboard for artifact paths",
  "copyPath" in html or "clipboard" in html.lower() or "navigator.clipboard" in html)

s("S19 proof-summary section",
  re.search(r'id="proof"|class="[^"]*proof[^"]*"', html) is not None)

# Summary
passed = sum(1 for c in checks if c["result"] == "pass")
failed = sum(1 for c in checks if c["result"] == "fail")
total  = len(checks)

print(f"\n{'='*50}")
print(f"Stage F Results: {passed}/{total} passed, {failed} failed")
if failed:
    print("FAILED checks:")
    for c in checks:
        if c["result"] == "fail":
            print(f"  - {c['id']}: {c['details']}")

output = {
    "stage": "F",
    "validator": "static-structural",
    "html_file": str(HTML),
    "summary": {"passed": passed, "failed": failed, "total": total},
    "checks": checks,
}
OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"\nWritten: {OUT}")
sys.exit(0 if failed == 0 else 1)
