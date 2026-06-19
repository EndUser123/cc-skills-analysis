#!/usr/bin/env python3
"""Stage H: External Critic for doc-compiler index.html.

Uses claude --print to run the external critic sub-agent.
Gate: no_invented_routes AND toc_initial_state_synced AND toc_handler_atomic
"""
import json, subprocess, sys, re
from pathlib import Path

BASE   = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
HTML   = BASE / "index.html"
REPORT = BASE / "validation-report.json"

html_content = HTML.read_text(encoding="utf-8")

AGENT_PROMPT = f"""\
You are validating the doc-compiler HTML output against the skill's contract.

HTML file: {HTML}
Content length: {len(html_content)} chars

Contract checks (ALL must pass):
1. no_invented_routes: HTML must not contain route targets (hrefs, delegations) not present in source-model.json steps
2. toc_initial_state_synced: TOC sidebar must be visible by default (not collapsed) on desktop
3. toc_handler_atomic: TOC toggle handler must be a single atomic handler (not split across multiple listeners)
4. html_represents_source: All steps from the source appear in the accordion
5. steps_complete: Each step card has title + description text
6. no_internal_policy_prose: HTML must not contain internal SKILL.md policy prose or control-flow headings

Read the HTML file and perform the checks above.

For each check, report:
  - check_id: string
  - passed: boolean
  - evidence: string (snippet or explanation)

Then evaluate the gate:
  gate_passed = (no_invented_routes AND toc_initial_state_synced AND toc_handler_atomic)

Output a JSON block at the end with:
{{
  "stage": "H",
  "validator": "external-critic",
  "checks": [
    {{"check_id": "...", "passed": bool, "evidence": "..."}}
  ],
  "gate_passed": bool,
  "gate_summary": "...",
  "failed_checks": [...]
}}
"""

print("Stage H: Running external critic via claude --print...")

result = subprocess.run(
    ["claude", "--print", "--model", "sonnet", AGENT_PROMPT],
    capture_output=True, text=True, encoding="utf-8", timeout=600
)

if result.returncode != 0:
    print(f"claude --print failed with exit code {result.returncode}", file=sys.stderr)
    print(f"stderr: {result.stderr}", file=sys.stderr)
    sys.exit(1)

raw = result.stdout.strip()

# Extract JSON from the output
# claude --print wraps JSON in a markdown code block:
#   ```json
#   { "stage": "H", ... }
#   ```
# The JSON may span multiple lines and extend past the closing fence.
# Strategy: find ```json, skip to next line, then parse from the first '{' to EOF.
output = None
json_start_line = None
in_json_block = False

for i, line in enumerate(raw.splitlines()):
    stripped = line.strip()
    if stripped.startswith("```json"):
        in_json_block = True
        continue
    if in_json_block and stripped.startswith("{"):
        json_start_line = i
        break

if json_start_line is None:
    print("Could not find JSON object in claude --print output")
    print("Last 500 chars:", raw[-500:])
    sys.exit(1)

try:
    json_text = "\n".join(raw.splitlines()[json_start_line:])
    # Strip trailing ``` fence and any whitespace after the closing brace
    json_text = json_text.replace('```', '').strip()
    output = json.loads(json_text)
except json.JSONDecodeError as e:
    print(f"Failed to parse JSON: {e}")
    print("Last 500 chars:", raw[-500:])
    sys.exit(1)

REPORT.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"Stage H written to {REPORT}")

gate_passed = output.get("gate_passed", False)
passed = sum(1 for c in output.get("checks", []) if c.get("passed"))
total  = len(output.get("checks", []))
print(f"Stage H: {passed}/{total} checks passed, gate={'PASSED' if gate_passed else 'FAILED'}")
sys.exit(0 if gate_passed else 1)
