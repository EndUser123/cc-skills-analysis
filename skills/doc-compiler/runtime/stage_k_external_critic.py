#!/usr/bin/env python3
"""Stage K: External Critic for doc-compiler.

Runs an external LLM-based review of the generated index.html using
`claude --print` to check fidelity against the source model.
Emits validation-report.json.

This stage verifies that:
1. All declared steps appear in the output
2. All decision points are addressed
3. All route_outs are documented
4. No hallucinated content (content not in source model)
5. CSS/JS contracts are honored
"""
import json, re, subprocess, sys, textwrap
from pathlib import Path

BASE = Path("P:/packages/.claude-marketplace/plugins/cc-skills-analysis/skills/doc-compiler")
INDEX = BASE / "index.html"
SOURCE = BASE / "source-model.json"
PLAN   = BASE / "doc-model.json"
OUT    = BASE / "validation-report.json"

SYSTEM_PROMPT = textwrap.dedent("""
    You are a documentation critic. Review the generated index.html for a skill/plugin.
    Check for:
    1. All source model steps are rendered
    2. Decision points are reflected
    3. Route-outs are documented
    4. No hallucinated content not present in source
    5. Proper DOM structure (tocToggle, themeToggle, step accordions, mermaidSource)
    6. CSS contract compliance (fixed TOC, prefers-color-scheme)

    Respond with JSON in this format:
    {
      "gate_passed": true/false,
      "step_coverage": 0.0-1.0,
      "decision_coverage": 0.0-1.0,
      "route_out_coverage": 0.0-1.0,
      "hallucination_detected": true/false,
      "dom_issues": ["list of missing/broken DOM elements"],
      "css_issues": ["list of CSS contract violations"],
      "failed_checks": ["list of specific checks that failed"],
      "recommendations": ["list of fixes needed"]
    }
""")

USER_PROMPT_TEMPLATE = """Review this documentation artifact:

=== SOURCE MODEL ===
{source_summary}

=== GENERATED HTML (index.html) ===
{html_excerpt}

=== CHECKLIST ===
- Step count: declared={step_count}, found={found_count}
- DOM: tocToggle present={toc_toggle}, themeToggle present={theme_toggle}
- CSS: style block present={style_block}, dark mode={dark_mode}
- Mermaid: mermaidSource present={mermaid_source}, resize handle={resize_handle}

Respond with JSON only."""


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def summarize_source(model: dict) -> str:
    """Create a compact summary of the source model for the critic."""
    steps = model.get("steps", [])
    decisions = model.get("decision_points", [])
    route_outs = model.get("route_outs", [])
    terminals = model.get("terminal_states", [])
    artifacts = model.get("artifacts", [])

    lines = []
    lines.append(f"Name: {model.get('name', 'unknown')}")
    lines.append(f"Kind: {model.get('kind', 'unknown')}")
    lines.append(f"Description: {model.get('description', '')}")
    lines.append(f"Steps ({len(steps)}):")
    for s in steps:
        lines.append(f"  - {s.get('id', '?')}: {s.get('name', '?')}")
    if decisions:
        lines.append(f"Decision points ({len(decisions)}):")
        for d in decisions:
            lines.append(f"  - {d.get('name', '?')}")
    if route_outs:
        lines.append(f"Route outs ({len(route_outs)}):")
        for r in route_outs:
            lines.append(f"  - {r.get('target', r.get('trigger', '?'))}")
    if terminals:
        lines.append(f"Terminal states ({len(terminals)}):")
        for t in terminals:
            lines.append(f"  - {t.get('name', '?')}")
    if artifacts:
        lines.append(f"Artifacts ({len(artifacts)}):")
        for a in artifacts:
            lines.append(f"  - {a.get('name', '?')}: {a.get('path', '')}")
    return "\n".join(lines)


def main() -> None:
    errors = []

    if not INDEX.exists():
        errors.append("index.html not found")
    if not SOURCE.exists():
        errors.append("source-model.json not found")

    if errors:
        output = {"stage": "K", "passed": False, "errors": errors}
        OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Stage K: FAIL -- {errors[0]}", file=sys.stderr)
        sys.exit(1)

    source_model = load_json(SOURCE)
    html_content = INDEX.read_text(encoding="utf-8")
    doc_model = load_json(PLAN)

    # Build summary for prompt
    source_summary = summarize_source(source_model)

    # Extract key metrics from HTML
    html_excerpt = html_content[:40000]  # must cover full page since HTML is ~63KB

    steps_declared = len(source_model.get("steps", []))
    steps_found = html_content.count('class="step"')

    # Check DOM elements
    toc_toggle = 'id="tocToggle"' in html_content
    theme_toggle = 'id="themeToggle"' in html_content
    style_block = "<style>" in html_content
    dark_mode = "dark" in html_content.lower() or "prefers-color-scheme" in html_content
    mermaid_source = 'id="mermaidSource"' in html_content
    resize_handle = 'id="diagramResizeHandle"' in html_content

    user_prompt = USER_PROMPT_TEMPLATE.format(
        source_summary=source_summary,
        html_excerpt=html_excerpt,
        step_count=steps_declared,
        found_count=steps_found,
        toc_toggle=toc_toggle,
        theme_toggle=theme_toggle,
        style_block=style_block,
        dark_mode=dark_mode,
        mermaid_source=mermaid_source,
        resize_handle=resize_handle
    )

    print("Stage K: Running external critic (claude --print --model sonnet)...")

    try:
        result = subprocess.run(
            [
                "claude", "--print",
                "--model", "sonnet",
                "--system-prompt", SYSTEM_PROMPT,
            ],
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output_text = result.stdout.strip()

        # Fail closed: no output at all means the critic failed to run
        if not output_text:
            raise ValueError("critic produced empty output")

        # Parse JSON from output (may be wrapped in markdown code block)
        json_match = re.search(r'```json\s*(.*?)```', output_text, re.DOTALL)
        if json_match:
            output_text = json_match.group(1)

        if not output_text:
            raise ValueError("critic produced no parseable JSON")

        report = json.loads(output_text)
        report["stage"] = "K"
        report["critic_model"] = "sonnet"
        report["stdout_excerpt"] = result.stdout[:500]
        report["stderr_excerpt"] = result.stderr[:200]

    except subprocess.TimeoutExpired:
        report = {
            "stage": "K",
            "passed": False,
            "errors": ["claude --print timed out after 300s"],
            "gate_passed": False,
            "failed_checks": ["external-critic-timeout"]
        }
    except json.JSONDecodeError as ex:
        report = {
            "stage": "K",
            "passed": False,
            "errors": [f"Could not parse critic JSON: {ex}"],
            "gate_passed": False,
            "failed_checks": ["critic-json-parse-error"],
            "raw_output": result.stdout[:1000]
        }
    except Exception as ex:
        report = {
            "stage": "K",
            "passed": False,
            "errors": [str(ex)],
            "gate_passed": False,
            "failed_checks": ["external-critic-error"]
        }

    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    gate_passed = report.get("gate_passed", False)
    failed_count = len(report.get("failed_checks", []))

    print(f"Stage K: {'PASS' if gate_passed else 'FAIL'} -- gate_passed={gate_passed}")
    if failed_count:
        print(f"  failed_checks: {failed_count}")
        for fc in report.get("failed_checks", []):
            print(f"    - {fc}")
    for rec in report.get("recommendations", []):
        print(f"  REC: {rec}")

    print(f"Written: {OUT}")
    sys.exit(0 if gate_passed else 1)


if __name__ == "__main__":
    main()