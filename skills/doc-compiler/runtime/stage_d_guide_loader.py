#!/usr/bin/env python3
"""Stage D: Guide Loader for doc-compiler.

Reads diagram-guides.json (from Stage C) and loads the actual guide
content from references/guides/. Emits guides-loaded.json combining
guide metadata with parsed content.
"""
import json, re, sys
from pathlib import Path
from typing import Any

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
GUIDES_PLAN = BASE / "diagram-guides.json"
OUT = BASE / "guides-loaded.json"
GUIDES_DIR = BASE / "references" / "guides"


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def extract_guide_sections(content: str) -> list[dict[str, str]]:
    """Parse guide markdown into named sections."""
    sections = []
    # Split on ## headings
    parts = re.split(r'^##\s+(.+)$', content, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i+1].strip() if i+1 < len(parts) else ""
        sections.append({
            "heading": heading,
            "body": body[:500]  # truncate very long bodies
        })
    return sections


def parse_diagram_hints(content: str, diagram_type: str) -> dict[str, Any]:
    """Extract concrete Mermaid syntax hints from guide content."""
    hints = {
        "diagram_type": diagram_type,
        "syntax_patterns": [],
        "common_pitfalls": [],
        "palette_recommendation": ""
    }

    # Extract code blocks (Mermaid examples)
    code_blocks = re.findall(r'```mermaid(.*?)```', content, re.DOTALL)
    hints["syntax_patterns"] = [cb.strip() for cb in code_blocks if cb.strip()]

    # Extract anti-patterns
    anti_pattern_lines = re.findall(
        r'(?i)(?:anti-pattern|avoid|do not|never|don\'t)\s*[:\-]\s*(.+)',
        content
    )
    hints["common_pitfalls"] = [line.strip() for line in anti_pattern_lines if line.strip()]

    # Extract palette suggestions
    palette_match = re.search(r'palette:\s*(\w+)', content, re.IGNORECASE)
    if palette_match:
        hints["palette_recommendation"] = palette_match.group(1).strip()

    return hints


def load_guides(plan: dict) -> list[dict]:
    """Load all guide files referenced in diagram-guides.json."""
    loaded = []
    for entry in plan:
        guide_file = entry.get("guide_file", "")
        diagram_id = entry.get("diagram_id", "")
        diagram_type = entry.get("diagram_type", "")

        guide_path = GUIDES_DIR / guide_file
        content = ""
        if guide_path.exists():
            content = guide_path.read_text(encoding="utf-8")

        sections = extract_guide_sections(content)
        hints = parse_diagram_hints(content, diagram_type)

        loaded.append({
            "diagram_id": diagram_id,
            "diagram_type": diagram_type,
            "guide_file": guide_file,
            "guide_content": content,
            "guide_sections": sections,
            "mermaid_hints": hints,
            "palette_hint": entry.get("palette_hint", "tailwind-modern"),
            "loaded": bool(content),
            "load_errors": [] if content else [f"Guide file not found: {guide_file}"]
        })

    return loaded


def main() -> None:
    if not GUIDES_PLAN.exists():
        print(f"ERROR: {GUIDES_PLAN} not found. Run Stage C first.", file=sys.stderr)
        sys.exit(1)

    plan = load_json(GUIDES_PLAN)
    if not plan:
        print(f"ERROR: diagram-guides.json is empty", file=sys.stderr)
        sys.exit(1)

    guides = load_guides(plan)

    result = {
        "kind": "guides-loaded",
        "version": "1.0.0",
        "guides_count": len(guides),
        "guides": guides
    }

    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    loaded_count = sum(1 for g in guides if g["loaded"])
    print(f"Stage D: PASS — {loaded_count}/{len(guides)} guides loaded")
    for g in guides:
        status = "OK" if g["loaded"] else "MISSING"
        print(f"  [{status}] {g['diagram_id']} ({g['diagram_type']}) -> {g['guide_file']}")
    print(f"Written: {OUT}")
    sys.exit(0)


if __name__ == "__main__":
    main()