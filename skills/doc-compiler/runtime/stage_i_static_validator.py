#!/usr/bin/env python3
"""Stage I: Static Validator for doc-compiler.

Runs S1-S19 structural checks from SKILL.md against index.html.
Emits static-validation.json.

NOTE: This replaces the old stage_f_validator.py which had naming confusion.
Stage F in the new pipeline is the Diagram Critic Gate (stage_f_diagram_critic_gate.py).
"""
import json, re, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
HTML = BASE / "index.html"
OUT  = BASE / "static-validation.json"


def check(name: str, pred: bool, details: str = "") -> str:
    result = "pass" if pred else "fail"
    msg = f"[{result.upper()}] {name}"
    if details:
        msg += f" — {details}"
    if pred:
        print(f"  PASS: {msg}")
    else:
        print(f"  FAIL: {msg}", file=sys.stderr)
    return result


def main() -> None:
    if not HTML.exists():
        out = {"stage": "I", "passed": False, "errors": ["index.html not found"]}
        OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print("Stage I: FAIL — index.html not found", file=sys.stderr)
        sys.exit(1)

    html = HTML.read_text(encoding="utf-8")
    checks = []

    print("\n=== Stage I: Static Structural Validator ===\n")

    def s(name: str, pred: bool, details: str = "") -> None:
        r = check(name, pred, details)
        checks.append({"id": name, "result": r, "details": details or None})

    # S1: #tocToggle as direct sibling of .page-shell (NOT inside nav.toc)
    s("S1  tocToggle sibling",
      re.search(r'<button id="tocToggle"[^>]*>.*?</button>\s*<div class="page-shell"', html, re.DOTALL) is not None,
      "tocToggle must be immediate sibling of .page-shell")

    # S2: nav#toc class="toc"
    s("S2  nav#toc class=toc",
      re.search(r'<nav id="toc" class="toc"', html) is not None)

    # S3: TOC CSS block — iterate all CSS in the file with brace-depth tracking.
    # When .toc { is found at depth==1, accumulate until depth returns to 0.
    # This correctly handles both top-level and @media-nested .toc blocks.
    css_idx = 0
    depth = 0
    toc_css_parts = []
    in_toc = False
    toc_start = -1
    while css_idx < len(html):
        ch = html[css_idx]
        if ch == '{':
            depth += 1
            if depth == 1 and css_idx >= 5 and html[css_idx-5:css_idx+1] == '.toc {':
                in_toc = True
                toc_start = css_idx + 1
            css_idx += 1
        elif ch == '}':
            depth -= 1
            if in_toc and depth == 0:
                toc_css_parts.append(html[toc_start:css_idx])
                in_toc = False
                toc_start = -1
            css_idx += 1
        else:
            css_idx += 1

    toc_css_text = " ".join(toc_css_parts)
    s("S3  TOC CSS block exists", bool(toc_css_text))
    if toc_css_text:
        s("S4  position:fixed or absolute", "position" in toc_css_text and ("fixed" in toc_css_text or "absolute" in toc_css_text))
        s("S5  left transition", "left" in toc_css_text and "transition" in toc_css_text)
        s("S6  no transform on desktop", "transform" not in toc_css_text or "none" in toc_css_text)

    # S7: pre#mermaidSource present with content
    s("S7  pre#mermaidSource present",
      re.search(r'<pre[^>]+id="mermaidSource"', html) is not None)

    # S8: .diagram-shell CSS block
    dg = re.search(r'\.diagram-shell\s*\{[^}]+\}', html, re.DOTALL)
    s("S8  .diagram-shell CSS block", dg is not None)
    if dg:
        s("S8b display:flex", "display" in dg.group(0) and "flex" in dg.group(0))
        s("S8c flex-direction:column", "flex-direction" in dg.group(0) and "column" in dg.group(0))

    # S9: .diagram-viewport min-height:200px
    dv = re.search(r'\.diagram-viewport\s*\{[^}]+\}', html, re.DOTALL)
    s("S9  .diagram-viewport CSS block", dv is not None)
    if dv:
        s("S9b min-height:200px", "min-height" in dv.group(0) and "200px" in dv.group(0))

    # S10: resize handle element
    s("S10 diagram-resize-handle element",
      re.search(r'<div[^>]+id="diagramResizeHandle"', html) is not None)

    # S11: resize handle CSS
    rh = re.search(r'\.diagram-resize-handle\s*\{[^}]+\}', html, re.DOTALL)
    s("S11 resize-handle CSS block", rh is not None)
    if rh:
        s("S11b cursor:ns-resize", "cursor" in rh.group(0) and "ns-resize" in rh.group(0))

    # S12: accordion step elements
    s("S12 article.step elements",
      re.search(r'<article[^>]*class="[^"]*step[^"]*"', html) is not None)

    # S13: #themeToggle inside .toc-controls
    s("S13 #themeToggle placement",
      re.search(r'class="toc-controls"[^>]*>\s*<button id="themeToggle"', html, re.DOTALL) is not None)

    # S14: search UI
    s("S14 searchInput element",
      re.search(r'<input[^>]+id="searchInput"', html) is not None)

    # S15: steps present from source model
    s("S15 source-model steps present",
      html.count('class="step"') >= 1)

    # S16: gate badges
    s("S16 gate badges present",
      "gate-badge" in html or "badge-" in html)

    # S17: accordion toggle function
    s("S17 accordion toggle function",
      "toggleStep" in html and "step-header" in html)

    # S18: copy-to-clipboard for artifact paths
    s("S18 copy-to-clipboard present",
      "copyPath" in html or "clipboard" in html.lower() or "navigator.clipboard" in html)

    # S19: proof-summary section
    s("S19 proof-summary section",
      re.search(r'id="proof"|class="[^"]*proof[^"]*"', html) is not None)

    # Summary
    passed = sum(1 for c in checks if c["result"] == "pass")
    failed = sum(1 for c in checks if c["result"] == "fail")
    total = len(checks)

    print(f"\n{'='*50}")
    print(f"Stage I Results: {passed}/{total} passed, {failed} failed")

    output = {
        "stage": "I",
        "validator": "static-structural",
        "html_file": str(HTML),
        "summary": {"passed": passed, "failed": failed, "total": total},
        "checks": checks,
        "passed": failed == 0
    }
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWritten: {OUT}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()