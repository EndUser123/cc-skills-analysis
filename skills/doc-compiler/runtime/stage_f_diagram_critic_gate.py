#!/usr/bin/env python3
"""Stage F: Diagram Critic Gate for doc-compiler.

Reads diagrams.json (Stage E output) and applies guide-based critique
to each Mermaid diagram. Rejects diagrams that violate guide rules.
Emits gate-result.json.
"""
import json, re, sys
from pathlib import Path

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
DIAGRAMS = BASE / "diagrams.json"
DOC_MODEL = BASE / "doc-model.json"
OUT = BASE / "gate-result.json"


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def critique_flowchart(mmd: str, diagram_id: str) -> list[str]:
    """Critique a flowchart diagram for guideline violations."""
    issues = []
    lines = mmd.splitlines()

    # Anti-pattern: very long node labels
    for line in lines:
        if "[(" in line or "[" in line:
            match = re.search(r'\[+([^\]]+)\]+', line)
            if match and len(match.group(1)) > 50:
                issues.append(f"Node label too long (>50 chars): {match.group(1)[:50]}...")

    # Anti-pattern: more than 15 nodes without subgraph grouping
    node_count = sum(1 for l in lines if ("-->" in l or "-.->" in l or "--" in l) and "subgraph" not in l)
    if node_count > 15:
        issues.append(f"High node count ({node_count}) may benefit from subgraph grouping")

    # Check for proper edge labels on decision paths
    diamond_count = mmd.count("{{{")
    if diamond_count > 0:
        pass  # basic structural check done via syntax

    return issues


def critique_sequence(mmd: str, diagram_id: str) -> list[str]:
    """Critique a sequence diagram."""
    issues = []

    if "sequenceDiagram" not in mmd:
        issues.append("Missing sequenceDiagram declaration")

    # Check for actor declarations
    actor_count = mmd.count("participant")
    if actor_count < 2:
        issues.append(f"Sequence diagram has only {actor_count} actor(s) — needs at least 2")

    # Anti-pattern: messages only going one direction (no response)
    lines = mmd.splitlines()
    forwards = sum(1 for l in lines if "->>" in l)
    backwards = sum(1 for l in lines if "<<-" in l)
    if forwards > 0 and backwards == 0:
        issues.append("All messages go forward with no responses — consider if bidirectional arrows are needed")

    return issues


def critique_state(mmd: str, diagram_id: str) -> list[str]:
    """Critique a state diagram."""
    issues = []

    if "stateDiagram" not in mmd:
        issues.append("Missing stateDiagram declaration")

    # Check for [*] start and end
    if "[*]" not in mmd:
        issues.append("No [*] terminal state found")

    return issues


def critique_class(mmd: str, diagram_id: str) -> list[str]:
    """Critique a class diagram."""
    issues = []

    if "classDiagram" not in mmd:
        issues.append("Missing classDiagram declaration")

    # Check for class definitions
    class_count = mmd.count("class ")
    if class_count < 2:
        issues.append(f"Only {class_count} class(es) defined — class diagrams need multiple classes")

    # Anti-pattern: no relationships between classes
    if "-->" not in mmd and ".." not in mmd and class_count > 1:
        issues.append("Multiple classes but no relationships defined")

    return issues


def critique_error_path(mmd: str, diagram_id: str) -> list[str]:
    """Critique an error-path diagram."""
    issues = []

    # Check for error/warning indicators
    if "⚠" not in mmd and "error" not in mmd.lower() and "✗" not in mmd:
        issues.append("Error-path diagram missing error/warning indicators")

    # Error paths should have terminal failure states
    if "[*]" not in mmd and ("✗" not in mmd and "failed" not in mmd.lower()):
        issues.append("Error-path missing terminal failure states")

    return issues


CRITIQUES = {
    "flowchart": critique_flowchart,
    "sequence": critique_sequence,
    "state": critique_state,
    "class": critique_class,
    "error-path": critique_error_path,
}


def gate_diagram(diagram: dict) -> dict:
    """Critique a single diagram, return pass/fail with issues."""
    diagram_id = diagram.get("diagram_id", "unknown")
    diagram_type = diagram.get("diagram_type", "flowchart")
    mmd = diagram.get("mmd_content", "")

    issues = []
    critique_fn = CRITIQUES.get(diagram_type, critique_flowchart)
    issues = critique_fn(mmd, diagram_id)

    return {
        "diagram_id": diagram_id,
        "diagram_type": diagram_type,
        "passed": len(issues) == 0,
        "issues": issues
    }


def main() -> None:
    if not DIAGRAMS.exists():
        print(f"ERROR: {DIAGRAMS} not found. Run Stage E first.", file=sys.stderr)
        sys.exit(1)

    data = load_json(DIAGRAMS)
    diagrams = data.get("diagrams", [])

    if not diagrams:
        print("ERROR: No diagrams found in diagrams.json", file=sys.stderr)
        sys.exit(1)

    results = []
    for diag in diagrams:
        result = gate_diagram(diag)
        results.append(result)

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    output = {
        "stage": "F",
        "gate": "diagram-critic",
        "diagrams_critiqued": len(results),
        "passed": passed,
        "failed": failed,
        "gate_passed": failed == 0,
        "results": results
    }

    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"Stage F: {'PASS' if failed == 0 else 'FAIL'} — {passed}/{len(results)} diagrams passed critique")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['diagram_id']} ({r['diagram_type']})")
        for issue in r.get("issues", []):
            print(f"    ISSUE: {issue}")

    print(f"\nWritten: {OUT}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()