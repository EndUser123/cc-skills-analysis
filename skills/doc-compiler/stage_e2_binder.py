#!/usr/bin/env python3
"""Stage E2: Content Binder for doc-compiler.

Reads: e1-output.json + artifact-plan.json
Output: e2-output.json (filled templates as strings)
"""
import html
import json, re, sys
from pathlib import Path

BASE  = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
TPL   = BASE / "templates"
E1_OUT = BASE / "e1-output.json"
PLAN   = BASE / "artifact-plan.json"


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def slot_fill(template: str, bindings: dict) -> str:
    """Replace {{key}} placeholders in template with values from bindings dict."""
    result = template
    for key, value in bindings.items():
        placeholder = "{{" + key + "}}"
        if placeholder in result:
            result = result.replace(placeholder, str(value))
    return result


def fill_hero(template: str, plan: dict) -> str:
    bindings = {
        "skill_name":    plan["content_bindings"]["name"],
        "version":       plan["content_bindings"]["version"],
        "description":   plan["content_bindings"]["description"],
        "enforcement":   plan.get("enforcement", "strict"),
        "status":        plan.get("status", "active"),
    }
    return slot_fill(template, bindings)


def fill_facts(template: str, plan: dict) -> str:
    steps = plan["content_bindings"].get("steps", [])
    route_outs = plan["content_bindings"].get("route_outs", [])
    artifacts = plan.get("artifacts", [])
    first_step = steps[0].get("name", "start") if steps else "start"
    last_step = steps[-1].get("name", "end") if steps else "end"
    bindings = {
        "step_count":   len(steps),
        "step_summary": f"From {first_step} through {last_step}",
        "gate_count":   2,
        "gate_summary": "S5 (Mermaid) and S8 (External Validator) must both pass",
        "check_count":  16,
        "check_summary": "9-matrix + 10 assertions: render, TOC, zoom, search, accordion, console, mobile toggle",
        "artifact_count": len(artifacts) or 4,
        "artifact_summary": "index.html, source-model.json, artifact-proof.json, diagram.mmd",
    }
    return slot_fill(template, bindings)


def fill_mermaid_panel(template: str, plan: dict) -> str:
    mermaid_src = plan.get("mermaid_source", "")
    return template.replace("{{mermaid_source}}", mermaid_src)


def fill_steps(template: str, plan: dict) -> str:
    steps = plan["content_bindings"].get("steps", [])
    new_articles = ""
    for i, step in enumerate(steps, 1):
        name = step.get("display_name", step.get("name", ""))
        desc = step.get("description", "")
        name_escaped = name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        desc_escaped = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        new_articles += f"""
        <article class="step" id="step-{i}">
          <div class="step-header" onclick="toggleStep(this)">
            <h3>Step {i} — {name_escaped}</h3>
            <span class="chevron">▼</span>
          </div>
          <div class="step-body">
            <p>{desc_escaped}</p>
          </div>
        </article>
"""
    result = re.sub(
        r'<article class="step" id="step-\d+">.*?</article>',
        '',
        template,
        flags=re.DOTALL
    )
    result = re.sub(
        r'(<h2>Workflow Steps</h2>\s*)',
        r'\1' + new_articles,
        result,
        count=1
    )
    return result


def fill_route_outs(template: str, plan: dict) -> str:
    route_outs = plan["content_bindings"].get("route_outs", [])
    items = ""
    for ro in route_outs:
        target = html.escape(ro.get("target", ""))
        trigger = html.escape(ro.get("trigger", ""))
        desc = html.escape(ro.get("description", ""))
        items += f'''
        <div class="card">
          <h4>{target}</h4>
          <p>{desc}</p>
          <div class="kv" style="margin-top:0.5rem">
            <dt>Target</dt><dd><span class="code-inline">{target}</span></dd>
            <dt>Trigger</dt><dd>{trigger}</dd>
          </div>
        </div>
'''
    return template.replace("{{route_outs_content}}", items)


def fill_terminals(template: str, plan: dict) -> str:
    terminals = plan["content_bindings"].get("terminal_states", [])
    items = ""
    for t in terminals:
        name = t.get("name", "Done")
        desc = t.get("description", "")
        items += f'''
        <div class="card">
          <h4>{name}</h4>
          <p>{desc}</p>
        </div>
'''
    return template.replace("{{terminals_content}}", items)

def fill_artifacts(template: str, plan: dict) -> str:
    name = plan["content_bindings"].get("name", "doc")
    kind = plan.get("kind", "skill")
    bindings = {
        "artifact_description": f"Self-contained navigable HTML page with Mermaid diagram, TOC, search, theme toggle, accordion steps, proof summary.",
        "index_path": f"P:/.claude/skills/{name}/index.html" if kind == "skill" else f".claude/.artifacts/{{terminal_id}}/doc-compiler/{name}/index.html",
        "model_path": f".claude/.artifacts/{{terminal_id}}/doc-compiler/{name}/source-model.json",
        "proof_path": f".claude/.artifacts/{{terminal_id}}/doc-compiler/{name}/artifact-proof.json",
        "diagram_path": f".claude/.artifacts/{{terminal_id}}/doc-compiler/{name}/diagram.mmd",
    }
    return slot_fill(template, bindings)


def fill_proof_summary(template: str, plan: dict) -> str:
    return template


SECTION_HANDLERS = {
    "hero.html":           fill_hero,
    "facts.html":          fill_facts,
    "mermaid-panel.html":  fill_mermaid_panel,
    "steps-accordion.html": fill_steps,
    "route-outs.html":     fill_route_outs,
    "terminals.html":       fill_terminals,
    "artifacts.html":      fill_artifacts,
    "proof-summary.html":  fill_proof_summary,
}


def main() -> None:
    e1 = load_json(E1_OUT)
    plan = load_json(PLAN)

    if e1.get("status") != "pass":
        print("E1 must pass before E2 can run")
        sys.exit(1)

    errors = []
    filled: dict[str, str] = {}

    for name, handler in SECTION_HANDLERS.items():
        tpl_path = TPL / name
        if not tpl_path.exists():
            errors.append(f"missing template: {name}")
            continue
        template = tpl_path.read_text(encoding="utf-8")
        try:
            filled[name] = handler(template, plan)
        except Exception as ex:
            errors.append(f"error filling {name}: {ex}")
            filled[name] = template

    unfilled = []
    for name, content in filled.items():
        remaining = re.findall(r'\{\{[^}]+\}\}', content)
        if remaining:
            unfilled.append({"template": name, "remaining": remaining})

    output = {
        "stage": "E2",
        "status": "fail" if errors else "pass",
        "templates_filled": list(filled.keys()),
        "slot_fill_report": {name: "filled" for name in filled},
        "unfilled_slots": unfilled,
        "errors": errors,
    }

    out_path = BASE / "e2-output.json"
    for name, content in filled.items():
        (BASE / f"e2-filled_{name}").write_text(content, encoding="utf-8")

    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    n = len(filled)
    print(f"E2: {'PASS' if not errors else 'FAIL'} — {n} templates filled")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    print(f"E2 written to {out_path}")


if __name__ == "__main__":
    main()
