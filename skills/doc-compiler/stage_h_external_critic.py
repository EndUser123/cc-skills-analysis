#!/usr/bin/env python3
"""Stage H: External Critic Validator for doc-compiler.

Runs `claude --print` with a critic prompt against the generated index.html.
Reads: artifact-proof.json + index.html
Emits: validation-report.json (full external validation)
"""
import json, sys, subprocess
from pathlib import Path
from datetime import datetime

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
INDEX = BASE / "index.html"
PROOF = BASE / "artifact-proof.json"
OUT = BASE / "validation-report.json"

CRITIC_PROMPT = """You are an external critic reviewing a generated documentation page (index.html) for a Claude Code skill.

You are a SEPARATE LLM instance from the one that generated this page. Your job is to compare the artifact against the workflow contract and report honest findings.

Check these specific items and output ONLY JSON:
1. Does the page have valid HTML structure (DOCTYPE, title, head, body all present)?
2. Are workflow steps from source-model.json rendered in the page?
3. Is the Mermaid diagram present and does the source look valid?
4. Are there any broken placeholders ({{...}}) remaining?
5. Does the page have proper CSS styling (not raw unstyled HTML)?
6. Is the TOC present with working toggle button (#tocToggle)?
7. Are theme toggle and TOC toggle functional (buttons present with listeners)?

Output JSON only, no other text:
{
  "passed": true/false,
  "gate_passed": true/false,
  "failed_checks": ["list", "of", "issues"],
  "summary": "brief specific summary with actual findings"
}
"""


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    errors = []

    if not INDEX.exists():
        errors.append("index.html not found")
    if not PROOF.exists():
        errors.append("artifact-proof.json not found")

    if errors:
        print(f"Stage H: FAIL — {errors[0]}")
        output = {
            "stage": "H",
            "passed": False,
            "gate_passed": False,
            "failed_checks": errors,
            "summary": "prerequisites missing",
        }
        OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
        sys.exit(1)

    # Load proof to check if runtime verification passed
    proof = load_json(PROOF)
    vmatrix = proof.get("verification_matrix", {})
    runtime = proof.get("runtime_verification", {})

    # Run external critic via claude --print
    print("Stage H: Running external critic via claude --print...")

    index_content = INDEX.read_text(encoding="utf-8")
    prompt = CRITIC_PROMPT + f"\n\nFirst 3000 chars of index.html:\n{index_content[:3000]}"

    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout

        # Try to parse JSON from output
        import re
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        critic_result = {
            "passed": False,
            "gate_passed": False,
            "failed_checks": [],
            "summary": "could not parse critic output",
        }
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                critic_result.update(parsed)
            except Exception:
                # Use raw output as summary
                critic_result["summary"] = output[:500]
    except Exception as ex:
        critic_result = {
            "passed": False,
            "gate_passed": False,
            "failed_checks": [f"claude --print failed: {ex}"],
            "summary": f"claude --print error: {ex}",
        }

    # Include runtime verification status
    runtime_passed = runtime.get("all_passed", False)
    if not runtime_passed:
        critic_result.setdefault("failed_checks", [])
        critic_result["failed_checks"].append("runtime verification did not pass all checks")
        critic_result["passed"] = False
        critic_result["gate_passed"] = False

    output = {
        "stage": "H",
        "passed": critic_result.get("passed", False),
        "gate_passed": critic_result.get("gate_passed", False),
        "failed_checks": critic_result.get("failed_checks", []),
        "summary": critic_result.get("summary", ""),
        "critic_raw": critic_result,
        "runtime_verification": runtime,
    }

    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")

    if output["passed"]:
        print(f"Stage H: PASS — external critic approved")
    else:
        print(f"Stage H: FAIL — {output['summary'][:200]}")
    print(f"Written: {OUT}")
    sys.exit(0 if output["passed"] else 1)


if __name__ == "__main__":
    main()
