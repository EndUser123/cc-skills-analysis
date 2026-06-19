#!/usr/bin/env python3
"""Stage A: Source Extractor for doc-compiler.

Reads the target source file (SKILL.md, plugin manifest, README.md, workflow YAML)
and extracts a normalized source-model.json.
"""
import json, re, sys, os
from pathlib import Path
from typing import Any

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
OUT  = BASE / "source-model.json"

# Input: CLI arg (primary) or DOCC_TARGET env var (fallback)
if len(sys.argv) > 1:
    TARGET = sys.argv[1]
else:
    TARGET = os.environ.get("DOCC_TARGET", "")
    if not TARGET:
        print("ERROR: Provide target path as CLI arg or set DOCC_TARGET", file=sys.stderr)
        sys.exit(1)


def extract_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from SKILL.md style files."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        import yaml
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def normalize_steps(raw_steps: list) -> list[dict[str, Any]]:
    """Convert string steps to dicts, leave dicts as-is."""
    result = []
    for i, s in enumerate(raw_steps, 1):
        if isinstance(s, str):
            result.append({
                "id": f"step-{i}",
                "index": i,
                "name": s,
                "display_name": s,
                "description": "",
                "kind": "step",
                "conditions": [],
                "inputs": [],
                "outputs": [],
                "routes_to": [],
                "artifacts_emitted": []
            })
        elif isinstance(s, dict):
            result.append(s)
    return result


def extract_steps_from_skill(text: str, fm: dict) -> list[dict[str, Any]]:
    """Extract workflow steps from SKILL.md body and frontmatter."""
    steps = []

    # First: try frontmatter
    if fm and "steps" in fm:
        return normalize_steps(fm["steps"])

    # Second: try workflow_steps from frontmatter
    if fm and "workflow_steps" in fm:
        return normalize_steps(fm["workflow_steps"])

    # Third: scan body for step-like headings (### Step N or ### N. Name)
    step_pattern = re.compile(r'^###\s+(?:\d+[.)]\s*)?(.+)$', re.MULTILINE)
    desc_pattern = re.compile(r'^\s*-\s*\*\*(.+?)\*\*:\s*(.+)$', re.MULTILINE)

    # Also look for step definitions in the workflow model section
    # Scan for "steps:" block in the body text (sometimes inline)
    model_section = re.search(r'```json\s*\n.*?"steps"\s*:\s*\[(.*?)\]\s*\n```', text, re.DOTALL)
    if model_section:
        try:
            import yaml
            steps_data = yaml.safe_load('{"steps": [' + model_section.group(1) + ']}')
            if steps_data and "steps" in steps_data:
                return steps_data["steps"]
        except Exception:
            pass

    # Fallback: scan for ## When to Use, ## Input Contract sections
    # and treat major sections as steps
    heading_pattern = re.compile(r'^##\s+(.+)$', re.MULTILINE)
    for i, m in enumerate(heading_pattern.finditer(text), 1):
        name = m.group(1).strip()
        if name.lower() in ("when to use", "input contract", "output requirements"):
            continue
        steps.append({
            "id": f"step-{i}",
            "index": i,
            "name": name,
            "display_name": name,
            "description": "",
            "kind": "step",
            "conditions": [],
            "inputs": [],
            "outputs": [],
            "routes_to": [],
            "artifacts_emitted": []
        })

    # If nothing found, create a minimal default
    if not steps:
        steps.append({
            "id": "step-1",
            "index": 1,
            "name": "Read Source",
            "display_name": "Read Source",
            "description": "Read and extract content from source file",
            "kind": "step",
            "conditions": [],
            "inputs": [],
            "outputs": [],
            "routes_to": [],
            "artifacts_emitted": []
        })

    return steps


def extract_from_skill(path: Path) -> dict[str, Any]:
    """Extract source model from a SKILL.md file."""
    text = path.read_text(encoding="utf-8")
    fm = extract_frontmatter(text)
    steps = extract_steps_from_skill(text, fm)

    # style hint from frontmatter; CLI/env can override at plan stage
    style = fm.get("style", "") or ""

    return {
        "kind": "skill",
        "name": fm.get("name", path.parent.name),
        "version": fm.get("version", "0.0.0"),
        "style": style,
        "description": fm.get("description", ""),
        "steps": steps,
        "decision_points": [],
        "route_outs": [],
        "terminal_states": [],
        "artifacts": [],
        "gaps": [],
        "ambiguities": []
    }


def extract_from_plugin(path: Path) -> dict[str, Any]:
    """Extract source model from a plugin manifest (plugin.json)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("name", path.parent.name)
    desc = data.get("description", "")

    # Build steps from what the plugin actually does
    steps = [
        {
            "id": "install",
            "index": 1,
            "name": "Install Plugin",
            "display_name": "Install Plugin",
            "description": f"Install via /plugin install {name}",
            "kind": "step",
            "conditions": [],
            "inputs": [],
            "outputs": [],
            "routes_to": [],
            "artifacts_emitted": []
        },
        {
            "id": "configure",
            "index": 2,
            "name": "Configure",
            "display_name": "Configure",
            "description": "Configure plugin settings and hooks",
            "kind": "step",
            "conditions": [],
            "inputs": [],
            "outputs": [],
            "routes_to": [],
            "artifacts_emitted": []
        }
    ]

    # Add hooks as steps if present
    hooks = data.get("hooks", {})
    for i, (hook_name, hook_data) in enumerate(hooks.items(), 3):
        steps.append({
            "id": f"hook-{hook_name}",
            "index": i,
            "name": f"Hook: {hook_name}",
            "display_name": f"Hook: {hook_name}",
            "description": f"Process {hook_name} hook events",
            "kind": "step",
            "conditions": [],
            "inputs": [],
            "outputs": [],
            "routes_to": [],
            "artifacts_emitted": []
        })

    return {
        "kind": "plugin",
        "name": name,
        "version": data.get("version", "0.0.0"),
        "description": desc,
        "steps": steps,
        "decision_points": [],
        "route_outs": [],
        "terminal_states": [],
        "artifacts": data.get("artifacts", []),
        "gaps": [],
        "ambiguities": []
    }


def extract_from_readme(path: Path) -> dict[str, Any]:
    """Extract source model from a project README.md."""
    text = path.read_text(encoding="utf-8")
    # Extract title from first # heading
    title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    title = title_match.group(1) if title_match else path.parent.name

    # Extract description from first paragraph
    desc_match = re.search(r'^#.*?\n+\s*(.+?)(?:\n\n|\n#)', text, re.MULTILINE | re.DOTALL)
    description = desc_match.group(1).strip()[:200] if desc_match else ""

    return {
        "kind": "project",
        "name": title,
        "version": "0.0.0",
        "description": description,
        "steps": [
            {
                "id": "overview",
                "index": 1,
                "name": "Overview",
                "display_name": "Overview",
                "description": "Project overview and setup",
                "kind": "step",
                "conditions": [],
                "inputs": [],
                "outputs": [],
                "routes_to": [],
                "artifacts_emitted": []
            }
        ],
        "decision_points": [],
        "route_outs": [],
        "terminal_states": [],
        "artifacts": [],
        "gaps": [],
        "ambiguities": []
    }


def extract_from_yaml(path: Path) -> dict[str, Any]:
    """Extract source model from a workflow YAML file."""
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = []
    if isinstance(data, list):
        for i, item in enumerate(data, 1):
            steps.append({
                "id": item.get("id", f"step-{i}"),
                "index": i,
                "name": item.get("name", f"Step {i}"),
                "display_name": item.get("name", f"Step {i}"),
                "description": item.get("description", ""),
                "kind": item.get("kind", "step"),
                "conditions": item.get("conditions", []),
                "inputs": item.get("inputs", []),
                "outputs": item.get("outputs", []),
                "routes_to": item.get("routes_to", []),
                "artifacts_emitted": item.get("artifacts_emitted", [])
            })
    return {
        "kind": "workflow",
        "name": data.get("name", path.stem) if isinstance(data, dict) else path.stem,
        "version": "0.0.0",
        "description": data.get("description", "") if isinstance(data, dict) else "",
        "steps": steps,
        "decision_points": [],
        "route_outs": [],
        "terminal_states": [],
        "artifacts": [],
        "gaps": [],
        "ambiguities": []
    }


def main() -> None:
    if not TARGET or not Path(TARGET).exists():
        print(f"ERROR: DOCC_TARGET must point to a valid file. Got: {TARGET}", file=sys.stderr)
        sys.exit(1)

    target = Path(TARGET)
    suffix = target.name.lower()

    try:
        if suffix == "skill.md":
            model = extract_from_skill(target)
        elif suffix == "plugin.json" or "plugin" in target.parent.name:
            model = extract_from_plugin(target)
        elif suffix in ("readme.md", "readme"):
            model = extract_from_readme(target)
        elif suffix.endswith((".yaml", ".yml")):
            model = extract_from_yaml(target)
        else:
            # Default: try as SKILL.md
            model = extract_from_skill(target)

        model["source_path"] = str(target.resolve())
        model["generated_at"] = __import__("datetime").datetime.now().isoformat()

        OUT.write_text(json.dumps(model, indent=2), encoding="utf-8")
        steps_count = len(model.get("steps", []))
        print(f"Stage A: PASS — {steps_count} steps extracted from {target.name}")
        print(f"Written: {OUT}")
        sys.exit(0)

    except Exception as ex:
        print(f"Stage A: FAIL — {ex}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
