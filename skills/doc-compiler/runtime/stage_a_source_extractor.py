#!/usr/bin/env python3
"""Stage A: Source Extractor for doc-compiler.

Reads the target source file (SKILL.md, plugin manifest, README.md, workflow YAML/JSON)
and extracts a normalized source-model.json.

Input: CLI arg (primary) or DOCC_TARGET env var (fallback)
Output: source-model.json
"""
import json, re, sys, os
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent
OUT  = BASE / "source-model.json"

# Input: CLI arg (primary) or DOCC_TARGET env var (fallback)
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DOCC_TARGET", "")
STYLE_CLI = None
for i, arg in enumerate(sys.argv):
    if arg == "--style" and i + 1 < len(sys.argv):
        STYLE_CLI = sys.argv[i + 1]
    if arg.startswith("--style="):
        STYLE_CLI = arg.split("=", 1)[1]

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


def extract_presentation(fm: dict) -> dict[str, Any]:
    """Extract presentation/style config from frontmatter."""
    # CLI override wins
    if STYLE_CLI:
        return {"style": STYLE_CLI, "source": "cli"}
    # Try top-level style key
    if fm.get("style"):
        return {"style": fm["style"], "source": "frontmatter"}
    # Try nested presentation block
    pres = fm.get("presentation", {})
    if isinstance(pres, dict):
        style = pres.get("style", "default")
        return {"style": style, "source": "frontmatter", **pres}
    return {"style": "default", "source": "default"}


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

    # First: try frontmatter steps
    if fm and "steps" in fm:
        return normalize_steps(fm["steps"])

    # Second: try workflow_steps from frontmatter
    if fm and "workflow_steps" in fm:
        return normalize_steps(fm["workflow_steps"])

    # Third: scan body for step-like headings (### Step N or ### N. Name)
    step_pattern = re.compile(r'^###\s+(?:\d+[.)]\s*)?(.+)$', re.MULTILINE)
    desc_pattern = re.compile(r'^\s*-\s*\*\*(.+?)\*\*:\s*(.+)$', re.MULTILINE)

    # Also look for step definitions in a workflow model JSON code block
    model_section = re.search(
        r'```json\s*\n.*?"steps"\s*:\s*\[(.*?)\]\s*\n```',
        text, re.DOTALL
    )
    if model_section:
        try:
            import yaml
            steps_data = yaml.safe_load('{"steps": [' + model_section.group(1) + ']}')
            if steps_data and "steps" in steps_data:
                return steps_data["steps"]
        except Exception:
            pass

    # Fallback: major sections become steps
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


def extract_decision_points(text: str) -> list[dict[str, Any]]:
    """Extract decision/gate points from SKILL.md body."""
    decisions = []
    # Pattern: lines containing "gate", "decision", "check", "if/then"
    gate_pattern = re.compile(r'(?i)(gate|decision point|check|if.*then|when.*must|must\s+(?:pass|verify|check))', re.MULTILINE)
    for m in gate_pattern.finditer(text):
        line_start = max(0, m.start() - 200)
        line_end = min(len(text), m.end() + 100)
        context = text[line_start:line_end]
        # Find the heading this belongs to
        heading_match = re.search(r'^##\s+(.+)$', context, re.MULTILINE)
        name = heading_match.group(1).strip() if heading_match else m.group(0)[:40]
        decisions.append({
            "id": f"decision-{len(decisions)+1}",
            "name": name,
            "description": m.group(0)[:100],
            "kind": "decision"
        })
    return decisions


def extract_route_outs(text: str) -> list[dict[str, Any]]:
    """Extract route-out / delegation targets from SKILL.md body."""
    routes = []
    # Pattern: /command-name or references to other skills/commands
    route_pattern = re.compile(r'(?i)(?:route to|delegate to|invoke|/\w+(?:\s+\w+)*)', re.MULTILINE)
    for m in route_pattern.finditer(text):
        target = m.group(0).strip()
        if len(target) > 2 and not target.startswith("http"):
            routes.append({
                "id": f"route-{len(routes)+1}",
                "target": target,
                "trigger": target,
                "description": ""
            })
    return routes


def extract_terminal_states(text: str) -> list[dict[str, Any]]:
    """Extract terminal/end states from SKILL.md body."""
    terminals = []
    terminal_pattern = re.compile(
        r'(?i)(?:terminal state|end state|final state|when.*completes|artifact.*emitted|output.*:)',
        re.MULTILINE
    )
    for m in terminal_pattern.finditer(text):
        name = m.group(0).strip()[:50]
        terminals.append({
            "id": f"terminal-{len(terminals)+1}",
            "name": name,
            "description": m.group(0)[:100]
        })
    return terminals


def extract_artifacts(text: str, fm: dict) -> list[dict[str, Any]]:
    """Extract artifact declarations from SKILL.md body and frontmatter."""
    artifacts = []
    # From frontmatter
    if fm and "artifacts" in fm:
        for a in fm["artifacts"]:
            if isinstance(a, dict):
                artifacts.append(a)
            elif isinstance(a, str):
                artifacts.append({"name": a, "path": ""})
    # From body: look for output artifacts mentioned
    artifact_pattern = re.compile(r'(?i)(?:emits?|outputs?|produces?|writes?)\s+(?:\w+\s+)*([^.!\n]+)', re.MULTILINE)
    for m in artifact_pattern.finditer(text):
        name = m.group(1).strip()[:60]
        if name and len(name) > 2:
            artifacts.append({
                "name": name,
                "path": f".claude/.artifacts/{{terminal_id}}/{name}"
            })
    return artifacts


def extract_from_skill(path: Path) -> dict[str, Any]:
    """Extract source model from a SKILL.md file."""
    text = path.read_text(encoding="utf-8")
    fm = extract_frontmatter(text)
    steps = extract_steps_from_skill(text, fm)
    decisions = extract_decision_points(text)
    routes = extract_route_outs(text)
    terminals = extract_terminal_states(text)
    artifacts = extract_artifacts(text, fm)
    presentation = extract_presentation(fm)

    return {
        "kind": "skill",
        "name": fm.get("name", path.parent.name),
        "version": fm.get("version", "0.0.0"),
        "description": fm.get("description", ""),
        "enforcement": fm.get("enforcement", "strict"),
        "status": fm.get("status", "active"),
        "triggers": fm.get("triggers", []),
        "steps": steps,
        "decision_points": decisions,
        "route_outs": routes,
        "terminal_states": terminals,
        "artifacts": artifacts,
        "gaps": [],
        "ambiguities": [],
        "source_path": str(path.resolve()),
        "presentation": presentation,
    }


def extract_from_plugin(path: Path) -> dict[str, Any]:
    """Extract source model from a plugin manifest (plugin.json)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("name", path.parent.name)
    desc = data.get("description", "")

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
        "triggers": [],
        "steps": steps,
        "decision_points": [],
        "route_outs": [],
        "terminal_states": [],
        "artifacts": data.get("artifacts", []),
        "gaps": [],
        "ambiguities": [],
        "source_path": str(path.resolve()),
        "presentation": {"style": "default", "source": "default"},
    }


def extract_from_readme(path: Path) -> dict[str, Any]:
    """Extract source model from a project README.md."""
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.parent.name

    desc_match = re.search(r'^#.*?\n+\s*(.+?)(?:\n\n|\n#)', text, re.MULTILINE | re.DOTALL)
    description = desc_match.group(1).strip()[:200] if desc_match else ""

    return {
        "kind": "project",
        "name": title,
        "version": "0.0.0",
        "description": description,
        "triggers": [],
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
        "ambiguities": [],
        "source_path": str(path.resolve()),
        "presentation": {"style": "default", "source": "default"},
    }


def extract_from_yaml(path: Path) -> dict[str, Any]:
    """Extract source model from a workflow YAML/JSON file."""
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
    elif isinstance(data, dict):
        name = data.get("name", path.stem)
        description = data.get("description", "")
        raw_steps = data.get("steps", [])
        if isinstance(raw_steps, list):
            for i, item in enumerate(raw_steps, 1):
                if isinstance(item, str):
                    steps.append({
                        "id": f"step-{i}", "index": i, "name": item,
                        "display_name": item, "description": "",
                        "kind": "step", "conditions": [], "inputs": [],
                        "outputs": [], "routes_to": [], "artifacts_emitted": []
                    })
                elif isinstance(item, dict):
                    steps.append(item)

    return {
        "kind": "workflow",
        "name": data.get("name", path.stem) if isinstance(data, dict) else path.stem,
        "version": "0.0.0",
        "description": data.get("description", "") if isinstance(data, dict) else "",
        "triggers": [],
        "steps": steps,
        "decision_points": [],
        "route_outs": data.get("routes", []) if isinstance(data, dict) else [],
        "terminal_states": data.get("terminals", []) if isinstance(data, dict) else [],
        "artifacts": data.get("artifacts", []) if isinstance(data, dict) else [],
        "gaps": [],
        "ambiguities": [],
        "source_path": str(path.resolve()),
        "presentation": {"style": "default", "source": "default"},
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
        elif suffix.endswith((".yaml", ".yml", ".json")):
            model = extract_from_yaml(target)
        else:
            model = extract_from_skill(target)

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
