#!/usr/bin/env python3
"""Stage D: Mermaid Critic Review for doc-compiler.

Uses claude --print to run the mermaid critic.
Gate: crossings==0 AND syntax_errors==[] AND legibility_score>=0.8
      AND all coverage checks pass.
"""
import json, subprocess, sys, re
from pathlib import Path

BASE       = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
DIAGRAM     = BASE / "diagram.mmd"
SOURCE      = BASE / "source-model.json"
PLAN        = BASE / "artifact-plan.json"
REPORT_PATH = BASE / "d-output.json"

diagram_text = DIAGRAM.read_text(encoding="utf-8")
source_text  = SOURCE.read_text(encoding="utf-8")

AGENT_PROMPT = f"""\
You are a Mermaid diagram critic for doc-compiler.

Diagram file: {DIAGRAM}
Diagram content length: {len(diagram_text)} chars

Source model file: {SOURCE}

Critic checks (ALL must pass):
1. Start-to-end traceability — trace from Start to every terminal without lifting your pen
2. Edge crossings — count crossing pairs; flag if > 0
3. Label clarity — every node label is self-explanatory standing alone
4. Non-forward edge labeling — every edge that is not a forward/pass has an explicit condition label
5. Readability at 50% zoom — all text legible, no overlapping nodes
5b. Zoom 50% legible — at 50% zoom, effective font size >= 10px
5c. Zoom 100 no overflow — at 100% zoom, no text overflow
5d. Zoom 150 no scroll — at 150% zoom, diagram width * 1.5 <= viewport width
6. Mermaid syntax validity — parse with no errors
7. Coverage of all workflow model steps — every step in source-model.json appears as a node
8. Coverage of all route-outs — every route_out in workflow model appears
9. Coverage of all terminal states — every terminal state in workflow model appears
10. Coverage of all decision points — every decision_point is a diamond or branch
11. Explicit color in each classDef — every classDef has a color: attribute
12. Theme-safe text colors:
    - Dark theme: text color must have >= 4.5:1 contrast ratio against node fill
    - Light theme: text readable on light fills

Perform all checks. Then evaluate the gate:
  gate_passed = (crossings == 0 AND syntax_errors == [] AND legibility_score >= 0.8
      AND missing_steps == [] AND missing_route_outs == []
      AND missing_terminal_states == [] AND dark_theme_contrast_ok == true
      AND light_theme_text_readable == true AND zoom_50_legible == true
      AND zoom_100_no_overflow == true AND zoom_150_no_scroll == true)

Output a JSON block at the end with:
{{
  "stage": "D",
  "critic": "mermaid-critic",
  "checks": [
    {{"check_id": "...", "passed": bool, "evidence": "..."}}
  ],
  "crossings": 0,
  "syntax_errors": [],
  "legibility_score": 0.0,
  "missing_steps": [],
  "missing_route_outs": [],
  "missing_terminal_states": [],
  "dark_theme_contrast_ok": true,
  "light_theme_text_readable": true,
  "zoom_50_legible": true,
  "zoom_100_no_overflow": true,
  "zoom_150_no_scroll": true,
  "gate_passed": bool,
  "gate_summary": "...",
  "failed_checks": [...]
}}
"""

print("Stage D: Running mermaid critic via claude --print...")

result = subprocess.run(
    ["claude", "--print", "--model", "sonnet", AGENT_PROMPT],
    capture_output=True, text=True, encoding="utf-8", timeout=600
)

if result.returncode != 0:
    print(f"claude --print failed with exit code {result.returncode}", file=sys.stderr)
    print(f"stderr: {result.stderr}", file=sys.stderr)
    sys.exit(1)

raw = result.stdout.strip()

# Extract JSON from output
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
    json_text = json_text.replace("```", "").strip()
    output = json.loads(json_text)
except json.JSONDecodeError as e:
    print(f"Failed to parse JSON: {e}")
    print("Last 500 chars:", raw[-500:])
    sys.exit(1)

REPORT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"Stage D written to {REPORT_PATH}")

gate_passed = output.get("gate_passed", False)
passed = sum(1 for c in output.get("checks", []) if c.get("passed"))
total  = len(output.get("checks", []))
print(f"Stage D: {passed}/{total} checks passed, gate={'PASSED' if gate_passed else 'FAILED'}")
sys.exit(0 if gate_passed else 1)
