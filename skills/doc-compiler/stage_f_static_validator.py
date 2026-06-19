#!/usr/bin/env python3
"""Stage F: Static Validator for doc-compiler.

Runs S1-S19 static checks on the assembled index.html.
Reads: index.html
Emits: validation-report.json (partial, static-only)
"""
import json, re, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
INDEX = BASE / "index.html"
OUT   = BASE / "validation-report.json"

CHECKS = [
    ("S1",  "DOCTYPE present",           lambda h: h.startswith("<!DOCTYPE html>")),
    ("S2",  "title tag",                 lambda h: "<title>" in h),
    ("S3",  "meta charset",              lambda h: 'charset="UTF-8"' in h),
    ("S4",  "meta viewport",             lambda h: "viewport" in h),
    ("S5",  "Mermaid source present",    lambda h: 'id="mermaidSource"' in h),
    ("S6",  "TOC nav present",           lambda h: 'id="toc"' in h),
    ("S7",  "theme toggle button",        lambda h: 'id="themeToggle"' in h or 'id="tocToggle"' in h),
    ("S8",  "search input present",       lambda h: 'id="searchInput"' in h),
    ("S9",  "steps section present",      lambda h: 'class="step"' in h or "step-" in h),
    ("S10", "script module tags",         lambda h: '<script type="module">' in h),
    ("S11", "style block present",        lambda h: "<style>" in h),
    ("S12", " no broken placeholders",     lambda h: "{{" not in h),
    ("S13", "mermaid CDN or import",     lambda h: "mermaid" in h.lower()),
    ("S14", "accessibility: lang attr",  lambda h: 'lang="' in h),
    ("S15", "body tag present",           lambda h: "<body>" in h),
    ("S16", "head closed",               lambda h: "</head>" in h),
    ("S17", "html closed",               lambda h: "</html>" in h),
    ("S18", "no unclosed tags (basic)",   lambda h: h.count("<script") == h.count("</script>")),
    ("S19", "steps have content",         lambda h: 'class="step-body"' in h),
    ("S20", "style CSS guards reserved IDs",
     lambda h: _check_style_css_no_reserved_id_overrides(h)),
]

# Properties a style CSS must not override on required-DOM-element selectors
_RESERVED_IDS = {
    "tocToggle", "toc", "themeToggle", "searchInput", "clearSearch",
    "mermaidSource", "diagramViewport", "diagramStage", "zoomIn", "zoomOut",
    "zoomReset", "zoomFit", "zoomPct", "paletteSelect", "diagramResizeHandle",
}
# Structural property categories that affect layout behavior, not just visuals
_STRUCTURAL_PROPS = {
    "display", "position", "top", "left", "right", "bottom",
    "width", "height", "z-index", "pointer-events",
}


def _check_style_css_no_reserved_id_overrides(html: str) -> bool:
    """Reject style CSS that overrides structural props on required DOM IDs.

    Style overlays live in <style> blocks and must not touch layout-affecting
    properties on the reserved IDs — those are controlled by the shared CSS
    contract which the runtime validator (Stage G) asserts against.
    """
    # Extract the <style> block(s)
    style_blocks = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
    if not style_blocks:
        return True  # no style block = nothing to check

    violations: list[str] = []
    for block in style_blocks:
        # Parse rules: selector { property: value; ... }
        rules = re.findall(r'([^{}]+)\{([^{}]+)\}', block)
        for selector, decls in rules:
            sel = selector.strip()
            # Check if this rule targets a reserved ID (directly or via descendant)
            target_ids = set(re.findall(r'#(\w+)', sel))
            if not target_ids.intersection(_RESERVED_IDS):
                continue
            # Extract full property names (including hyphens) — (\S+) captures
            # "pointer-events", "z-index", etc. without splitting on hyphens
            props_in_rule = re.findall(r'(\S+)\s*:', decls)
            structural = {p for p in props_in_rule if p in _STRUCTURAL_PROPS}
            if structural:
                violations.append(
                    f"CSS rule '{sel}' sets {structural} on reserved ID"
                )
    if violations:
        print("S20 FAIL:", violations, file=sys.stderr)
        return False
    return True

def main() -> None:
    if not INDEX.exists():
        print("ERROR: index.html not found — run stages A-E first", file=sys.stderr)
        sys.exit(1)

    html = INDEX.read_text(encoding="utf-8")
    results = {}
    passed = 0
    failed = 0

    for cid, desc, check in CHECKS:
        ok = False
        try:
            ok = check(html)
        except Exception:
            ok = False
        results[cid] = {
            "description": desc,
            "passed": ok,
            "reason": "pass" if ok else f"check {cid} failed: {desc}"
        }
        if ok:
            passed += 1
        else:
            failed += 1

    output = {
        "stage": "F",
        "status": "pass" if failed == 0 else "fail",
        "checks_passed": passed,
        "checks_failed": failed,
        "total_checks": len(CHECKS),
        "results": results,
        "passed": failed == 0,
    }

    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Stage F: {'PASS' if failed == 0 else 'FAIL'} — {passed}/{len(CHECKS)} checks passed")
    print(f"Written: {OUT}")
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
