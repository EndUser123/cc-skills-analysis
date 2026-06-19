#!/usr/bin/env python3
"""doc-compiler Quality Control Graphs — LangGraph Integration.

Three bounded-LLM retry subgraphs wrapped around the three critique gates:
  - diagram_repair_subgraph  (max 3 retries for Stage F)
  - ui_repair_subgraph       (max 2 retries for Stages I + J)
  - final_review_subgraph    (max 2 retries for Stage K)

All deterministic stages (A-E, G, H) are unchanged. This module adds only
agentic repair loops around the three gate stages.
"""
from __future__ import annotations

import json, os, shutil, subprocess, sys, textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, TypedDict

# ---------------------------------------------------------------------------
# LangGraph — deferred import so the module loads even without langgraph
# ---------------------------------------------------------------------------
try:
    from langgraph.constants import END, START
    from langgraph.graph import StateGraph
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
RUNTIME = BASE / "runtime"


# ---------------------------------------------------------------------------
# State schemas
# ---------------------------------------------------------------------------

class DiagramQCState(TypedDict, total=False):
    """State for the diagram-repair subgraph (Stage F loop)."""
    diagrams_json_path: str          # path to diagrams.json from Stage E
    diagrams_dir: str               # path to diagrams/ directory
    doc_model_path: str             # path to doc-model.json
    issues: list[str]              # accumulated issues across retries
    repair_record: list[dict]      # [{iteration, diagram_id, issue, repair}]
    retry_count: int               # current retry iteration
    MAX_RETRIES: int              # default 3
    gate_passed: bool
    blocked_diagrams: list[str]    # diagram_ids that still fail
    repair_staging_dir: str        # temp dir for staged repairs


class UIQCState(TypedDict, total=False):
    """State for the UI-repair subgraph (Stages I + J loop)."""
    index_html_path: str
    source_model_path: str
    static_failures: list[str]    # S1-S19 failures from Stage I
    runtime_failures: list[str]    # J1-J9 failures from Stage J
    repair_record: list[dict]      # [{iteration, failure, patch}]
    retry_count: int
    MAX_RETRIES: int              # default 2
    gate_passed: bool
    repair_staging_dir: str


class FinalReviewState(TypedDict, total=False):
    """State for the final-review subgraph (Stage K loop)."""
    index_html_path: str
    source_model_path: str
    validation_report_path: str    # path to validation-report.json
    review_passed: bool
    recommendations: list[str]
    retry_count: int
    MAX_RETRIES: int              # default 2
    blocked_checks: list[str]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DiagramCriticResult:
    passed: bool
    issues: list[str]
    results: list[dict]   # [{diagram_id, diagram_type, passed, issues}]

@dataclass
class UIValidatorResult:
    passed: bool
    static_failures: list[str]
    runtime_failures: list[str]

@dataclass
class ReviewResult:
    passed: bool
    step_coverage: float
    decision_coverage: float
    route_out_coverage: float
    hallucination_detected: bool
    dom_issues: list[str]
    css_issues: list[str]
    failed_checks: list[str]
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Stage callers (subprocess or direct function)
# ---------------------------------------------------------------------------

def _run_python(script_path: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a Python script as a subprocess, return the result."""
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def call_stage_f(diagrams_json_path: str, diagrams_dir: str, doc_model_path: str) -> DiagramCriticResult:
    """Call Stage F as a subprocess, return structured result."""
    env = os.environ.copy()
    env["DOCC_DIAGRAMS_JSON"] = diagrams_json_path
    env["DOCC_DIAGRAMS_DIR"] = diagrams_dir
    env["DOCC_DOC_MODEL"] = doc_model_path

    stage_path = RUNTIME / "stage_f_diagram_critic_gate.py"
    # Stage F uses its own hardcoded BASE paths; run it as-is
    result = _run_python(stage_path)

    gate_result_path = BASE / "gate-result.json"
    if gate_result_path.exists():
        data = json.loads(gate_result_path.read_text(encoding="utf-8"))
        all_results = data.get("results", [])
        all_issues = []
        for r in all_results:
            if not r.get("passed"):
                for issue in r.get("issues", []):
                    all_issues.append(f"{r['diagram_id']}: {issue}")
        return DiagramCriticResult(
            passed=data.get("gate_passed", result.returncode == 0),
            issues=all_issues,
            results=all_results,
        )
    return DiagramCriticResult(
        passed=result.returncode == 0,
        issues=[],
        results=[],
    )


def call_stage_i(index_html_path: str) -> UIValidatorResult:
    """Call Stage I (static validator) as a subprocess."""
    env = os.environ.copy()
    env["DOCC_INDEX_HTML"] = index_html_path
    stage_path = RUNTIME / "stage_i_static_validator.py"
    result = _run_python(stage_path)

    static_path = BASE / "static-validation.json"
    failures = []
    if static_path.exists():
        data = json.loads(static_path.read_text(encoding="utf-8"))
        for c in data.get("checks", []):
            if c.get("result") == "fail":
                failures.append(c.get("id", "?"))
    return UIValidatorResult(
        passed=result.returncode == 0 and len(failures) == 0,
        static_failures=failures,
        runtime_failures=[],
    )


def call_stage_j(index_html_path: str, source_model_path: str) -> UIValidatorResult:
    """Call Stage J (runtime validator) as a subprocess."""
    env = os.environ.copy()
    env["DOCC_INDEX_HTML"] = index_html_path
    env["DOCC_SOURCE_MODEL"] = source_model_path
    stage_path = RUNTIME / "stage_j_runtime_validator.py"
    result = _run_python(stage_path, timeout=180)

    runtime_path = BASE / "runtime-validation.json"
    failures = []
    if runtime_path.exists():
        data = json.loads(runtime_path.read_text(encoding="utf-8"))
        vm = data.get("verification_matrix", {})
        for k, v in vm.items():
            if isinstance(v, dict) and not v.get("passed"):
                failures.append(f"{k}: {v.get('reason', '')}")
    return UIValidatorResult(
        passed=result.returncode == 0 and len(failures) == 0,
        static_failures=[],
        runtime_failures=failures,
    )


def call_stage_k(index_html_path: str, source_model_path: str) -> ReviewResult:
    """Call Stage K (external critic) as a subprocess."""
    env = os.environ.copy()
    env["DOCC_INDEX_HTML"] = index_html_path
    env["DOCC_SOURCE_MODEL"] = source_model_path
    stage_path = RUNTIME / "stage_k_external_critic.py"
    result = _run_python(stage_path, timeout=300)

    report_path = BASE / "validation-report.json"
    if report_path.exists():
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return ReviewResult(
            passed=data.get("gate_passed", False),
            step_coverage=data.get("step_coverage", 0.0),
            decision_coverage=data.get("decision_coverage", 0.0),
            route_out_coverage=data.get("route_out_coverage", 0.0),
            hallucination_detected=data.get("hallucination_detected", False),
            dom_issues=data.get("dom_issues", []),
            css_issues=data.get("css_issues", []),
            failed_checks=data.get("failed_checks", []),
            recommendations=data.get("recommendations", []),
        )
    return ReviewResult(
        passed=result.returncode == 0,
        step_coverage=0.0,
        decision_coverage=0.0,
        route_out_coverage=0.0,
        hallucination_detected=False,
        dom_issues=[],
        css_issues=[],
        failed_checks=[],
        recommendations=[],
    )


# ---------------------------------------------------------------------------
# LLM repair functions
# ---------------------------------------------------------------------------

REPAIRABLE_DIAGRAM_ISSUES = {
    "long label", "missing edge label", "missing classDef color",
    "label too long", "no [*] terminal state",
}


def _is_repairable(issue: str) -> bool:
    """Return True if the issue is a mechanical repair (not a design problem)."""
    issue_lower = issue.lower()
    return any(r in issue_lower for r in REPAIRABLE_DIAGRAM_ISSUES)


def llm_diagram_repair(
    state: DiagramQCState,
) -> DiagramQCState:
    """LLM node: receive issues, emit repaired Mermaid source.

    Calls `claude --print` with the issue list and original Mermaid.
    Writes repaired files to the repair staging directory.
    Returns updated state with repair_record entry added.
    """
    diagrams_dir = Path(state["diagrams_dir"])
    staging = Path(state.get("repair_staging_dir", str(diagrams_dir.parent / "repair_1")))
    staging.mkdir(parents=True, exist_ok=True)
    state["repair_staging_dir"] = str(staging)

    iteration = state["retry_count"]
    repair_record = list(state.get("repair_record", []))

    # Build issue summary for the LLM
    issues_by_diagram: dict[str, list[str]] = {}
    for issue in state.get("issues", []):
        if ":" in issue:
            diagram_id, msg = issue.split(":", 1)
            diagram_id = diagram_id.strip()
            msg = msg.strip()
            issues_by_diagram.setdefault(diagram_id, []).append(msg)
        else:
            issues_by_diagram.setdefault("unknown", []).append(issue)

    for diagram_id, issues in issues_by_diagram.items():
        mmd_files = list(diagrams_dir.glob(f"{diagram_id}*.mmd"))
        if not mmd_files:
            # Try generic find
            mmd_files = list(diagrams_dir.glob("*.mmd"))
        if not mmd_files:
            continue

        mmd_path = mmd_files[0]
        original = mmd_path.read_text(encoding="utf-8")

        prompt = textwrap.dedent(f"""\
            You are a Mermaid diagram repair tool. Fix the following issues in this diagram.
            Return ONLY the repaired Mermaid source (no markdown, no explanation).

            Original Mermaid ({diagram_id}):
            ```mermaid
            {original}
            ```

            Issues to fix:
            {chr(10).join(f"  - {i}" for i in issues)}

            Repair rules:
            - Truncate labels exceeding 40 characters, appending `wrap()` if needed
            - Add missing edge labels to non-forward edges
            - Ensure [*] start and end states are present for stateDiagram
            - Add classDef colors if missing (use recommended dark-theme colors)
            - Do NOT change the diagram structure or logic
            - Do NOT add new nodes or edges

            Repaired Mermaid:
            ```mermaid
        """)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "claude", "--print", "--model", "sonnet"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout.strip()

            # Extract JSON code block if present
            import re as _re
            m = _re.search(r"```mermaid\s*(.*?)```", output, _re.DOTALL)
            if m:
                output = m.group(1).strip()

            repaired_path = staging / mmd_path.name
            repaired_path.write_text(output, encoding="utf-8")

            repair_record.append({
                "iteration": iteration,
                "diagram_id": diagram_id,
                "issue": issues[0] if issues else "unknown",
                "repair": str(repaired_path),
            })
        except Exception as ex:
            repair_record.append({
                "iteration": iteration,
                "diagram_id": diagram_id,
                "issue": issues[0] if issues else "unknown",
                "error": str(ex),
            })

    state["repair_record"] = repair_record
    return state


def llm_ui_repair(state: UIQCState) -> UIQCState:
    """LLM node: receive failures from stages I and J, emit HTML/CSS patches.

    Writes patches to the repair staging directory.
    Returns updated state with repair_record entry added.
    """
    staging = Path(state.get("repair_staging_dir", str(BASE / "ui_repair_1")))
    staging.mkdir(parents=True, exist_ok=True)
    state["repair_staging_dir"] = str(staging)

    index_html_path = Path(state["index_html_path"])
    if not index_html_path.exists():
        return state

    html_content = index_html_path.read_text(encoding="utf-8")
    iteration = state["retry_count"]
    all_failures = list(state.get("static_failures", [])) + list(state.get("runtime_failures", []))

    if not all_failures:
        return state

    prompt = textwrap.dedent(f"""\
        You are an HTML/CSS repair tool. Fix the following validation failures in this HTML file.
        Output a JSON object with the changes to make, or output {{"no_changes": true}} if the failures cannot be mechanically repaired.

        HTML excerpt (first 6000 chars):
        ```html
        {html_content[:6000]}
        ```

        Failures:
        {chr(10).join(f"  - {f}" for f in all_failures)}

        Output format:
        {{
          "patches": [
            {{"type": "replace", "selector": "CSS selector or HTML element", "what": "attribute|content|css", "value": "new value"}}
          ]
        }}

        Or: {{"no_changes": true, "reason": "failure X is not mechanically repairable"}}

        Respond ONLY with JSON.
    """)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "claude", "--print", "--model", "sonnet"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip()

        import re as _re
        json_match = _re.search(r"```json\s*(.*?)```", output, _re.DOTALL)
        if json_match:
            output = json_match.group(1).strip()

        try:
            patches = json.loads(output)
        except json.JSONDecodeError:
            patches = {}

        repair_record = list(state.get("repair_record", []))
        repair_record.append({
            "iteration": iteration,
            "failures": all_failures,
            "patches": patches,
            "staging": str(staging),
        })
        state["repair_record"] = repair_record

        # Apply patches if any
        if patches.get("patches"):
            _apply_html_patches(html_content, patches["patches"], staging)

    except Exception as ex:
        repair_record = list(state.get("repair_record", []))
        repair_record.append({
            "iteration": iteration,
            "failures": all_failures,
            "error": str(ex),
        })
        state["repair_record"] = repair_record

    return state


def _apply_html_patches(html: str, patches: list[dict], staging: Path) -> None:
    """Apply structured patches to HTML and write to staging."""
    # Simple patch application: for now, write original to staging.
    # In a full implementation, apply the specific replace patches.
    patched_path = staging / "index.patched.html"
    patched_path.write_text(html, encoding="utf-8")


def llm_repair_fidelity(state: FinalReviewState) -> FinalReviewState:
    """LLM node: receive Stage K recommendations, emit HTML/CSS patches.

    Returns updated state with repair_record entry added.
    """
    recommendations = state.get("recommendations", [])
    if not recommendations:
        return state

    index_html_path = Path(state["index_html_path"])
    if not index_html_path.exists():
        return state

    html_content = index_html_path.read_text(encoding="utf-8")
    iteration = state["retry_count"]

    prompt = textwrap.dedent(f"""\
        You are a documentation fidelity repair tool. The following recommendations
        came from an external LLM critic review. Apply the minimal fixes needed.

        HTML excerpt (first 6000 chars):
        ```html
        {html_content[:6000]}
        ```

        Recommendations:
        {chr(10).join(f"  - {r}" for r in recommendations)}

        Output a JSON object describing the patches to apply:
        {{
          "patches": [
            {{"type": "replace", "selector": "element or CSS selector", "what": "attribute|content", "value": "new value"}}
          ]
        }}

        Or: {{"no_changes": true}} if the recommendations cannot be mechanically applied.

        Respond ONLY with JSON.
    """)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "claude", "--print", "--model", "sonnet"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip()

        import re as _re
        json_match = _re.search(r"```json\s*(.*?)```", output, _re.DOTALL)
        if json_match:
            output = json_match.group(1).strip()

        repair_record = list(state.get("repair_record", []))
        repair_record.append({
            "iteration": iteration,
            "recommendations": recommendations,
            "raw_response": output[:500],
        })
        state["repair_record"] = repair_record

    except Exception as ex:
        repair_record = list(state.get("repair_record", []))
        repair_record.append({
            "iteration": iteration,
            "recommendations": recommendations,
            "error": str(ex),
        })
        state["repair_record"] = repair_record

    return state


# ---------------------------------------------------------------------------
# Decision nodes
# ---------------------------------------------------------------------------

def decide_diagram_next(state: DiagramQCState) -> Literal["llm_diagram_repair", "__end__", "escalate"]:
    """Route after diagram critic run."""
    if state.get("gate_passed", False):
        return "__end__"
    if state["retry_count"] >= state.get("MAX_RETRIES", 3):
        return "escalate"
    # Check if remaining issues are repairable
    issues = state.get("issues", [])
    if any(_is_repairable(i) for i in issues):
        return "llm_diagram_repair"
    return "escalate"


def decide_ui_next(state: UIQCState) -> Literal["llm_ui_repair", "__end__", "escalate"]:
    """Route after UI validator run."""
    if state.get("gate_passed", False):
        return "__end__"
    if state["retry_count"] >= state.get("MAX_RETRIES", 2):
        return "escalate"
    return "llm_ui_repair"


def decide_review_next(state: FinalReviewState) -> Literal["llm_repair_fidelity", "__end__", "abort"]:
    """Route after external review run."""
    if state.get("review_passed", False):
        return "__end__"
    if state["retry_count"] >= state.get("MAX_RETRIES", 2):
        return "abort"
    # Check if any recommendations are actionable
    recs = state.get("recommendations", [])
    if recs:
        return "llm_repair_fidelity"
    return "abort"


# ---------------------------------------------------------------------------
# Escalate / abort nodes
# ---------------------------------------------------------------------------

def escalate_diagram(state: DiagramQCState) -> DiagramQCState:
    """Write gate-result.json with FAILED, set blocked_diagrams."""
    gate_path = BASE / "gate-result.json"
    output = {
        "stage": "F",
        "gate": "diagram-critic",
        "gate_passed": False,
        "escalated": True,
        "retry_count": state["retry_count"],
        "blocked_diagrams": state.get("blocked_diagrams", []),
        "repair_record": state.get("repair_record", []),
        "issues": state.get("issues", []),
    }
    gate_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return state


def escalate_ui(state: UIQCState) -> UIQCState:
    """Write partial proof with diagnostics on UI failure."""
    proof_path = BASE / "proof-attempt.json"
    output = {
        "stage": "I+J",
        "gate": "ui-repair",
        "gate_passed": False,
        "escalated": True,
        "retry_count": state["retry_count"],
        "static_failures": state.get("static_failures", []),
        "runtime_failures": state.get("runtime_failures", []),
        "repair_record": state.get("repair_record", []),
    }
    proof_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return state


def abort_review(state: FinalReviewState) -> FinalReviewState:
    """Write proof with failed checks on unrecoverable review failure."""
    proof_path = BASE / "proof-attempt.json"
    output = {
        "stage": "K",
        "gate": "external-critic",
        "gate_passed": False,
        "aborted": True,
        "retry_count": state["retry_count"],
        "blocked_checks": state.get("blocked_checks", []),
        "recommendations": state.get("recommendations", []),
    }
    proof_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return state


# ---------------------------------------------------------------------------
# Node functions (called by the graph)
# ---------------------------------------------------------------------------

def run_diagram_critic(state: DiagramQCState) -> DiagramQCState:
    """Node: run Stage F diagram critic, update state with results."""
    diagrams_dir = Path(state.get("diagrams_dir", str(BASE / "diagrams")))

    result = call_stage_f(
        state["diagrams_json_path"],
        str(diagrams_dir),
        state["doc_model_path"],
    )

    state["gate_passed"] = result.passed
    state["issues"] = result.issues
    blocked = [r["diagram_id"] for r in result.results if not r["passed"]]
    state["blocked_diagrams"] = blocked
    return state


def run_ui_validator(state: UIQCState) -> UIQCState:
    """Node: run Stages I and J, combine failures."""
    index_html = state["index_html_path"]
    source_model = state["source_model_path"]

    i_result = call_stage_i(index_html)
    j_result = call_stage_j(index_html, source_model)

    state["gate_passed"] = i_result.passed and j_result.passed
    state["static_failures"] = i_result.static_failures
    state["runtime_failures"] = j_result.runtime_failures
    return state


def run_external_review(state: FinalReviewState) -> FinalReviewState:
    """Node: run Stage K external critic, update state with report."""
    result = call_stage_k(state["index_html_path"], state["source_model_path"])

    state["review_passed"] = result.passed
    state["recommendations"] = result.recommendations
    state["blocked_checks"] = result.failed_checks
    state["validation_report_path"] = str(BASE / "validation-report.json")
    return state


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------

def build_diagram_repair_graph() -> StateGraph | None:
    """Build the diagram-repair subgraph (Stage F loop)."""
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(DiagramQCState)
    graph.add_node("run_diagram_critic", run_diagram_critic)
    graph.add_node("llm_diagram_repair", llm_diagram_repair)
    graph.add_node("escalate", escalate_diagram)

    graph.add_edge(START, "run_diagram_critic")
    graph.add_conditional_edges(
        "run_diagram_critic",
        decide_diagram_next,
        {
            "__end__": END,
            "llm_diagram_repair": "llm_diagram_repair",
            "escalate": "escalate",
        },
    )
    graph.add_edge("llm_diagram_repair", "run_diagram_critic")
    graph.add_edge("escalate", END)

    return graph.compile()


def build_ui_repair_graph() -> StateGraph | None:
    """Build the UI-repair subgraph (Stages I + J loop)."""
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(UIQCState)
    graph.add_node("run_ui_validator", run_ui_validator)
    graph.add_node("llm_ui_repair", llm_ui_repair)
    graph.add_node("escalate", escalate_ui)

    graph.add_edge(START, "run_ui_validator")
    graph.add_conditional_edges(
        "run_ui_validator",
        decide_ui_next,
        {
            "__end__": END,
            "llm_ui_repair": "llm_ui_repair",
            "escalate": "escalate",
        },
    )
    graph.add_edge("llm_ui_repair", "run_ui_validator")
    graph.add_edge("escalate", END)

    return graph.compile()


def build_final_review_graph() -> StateGraph | None:
    """Build the final-review subgraph (Stage K loop)."""
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(FinalReviewState)
    graph.add_node("run_external_review", run_external_review)
    graph.add_node("llm_repair_fidelity", llm_repair_fidelity)
    graph.add_node("abort", abort_review)

    graph.add_edge(START, "run_external_review")
    graph.add_conditional_edges(
        "run_external_review",
        decide_review_next,
        {
            "__end__": END,
            "llm_repair_fidelity": "llm_repair_fidelity",
            "abort": "abort",
        },
    )
    graph.add_edge("llm_repair_fidelity", "run_external_review")
    graph.add_edge("abort", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Subgraph accessors (None if langgraph not installed)
# ---------------------------------------------------------------------------

diagram_repair_subgraph = build_diagram_repair_graph()
ui_repair_subgraph = build_ui_repair_graph()
final_review_subgraph = build_final_review_graph()


# ---------------------------------------------------------------------------
# High-level run functions (called by the orchestrator)
# ---------------------------------------------------------------------------

def run_diagram_qc(
    diagrams_json_path: str,
    diagrams_dir: str,
    doc_model_path: str,
    max_retries: int = 3,
) -> dict:
    """Run the diagram QC subgraph and return the final state as a dict."""
    if diagram_repair_subgraph is None:
        raise RuntimeError("LangGraph is not installed. Run: pip install langgraph")

    initial: DiagramQCState = {
        "diagrams_json_path": diagrams_json_path,
        "diagrams_dir": diagrams_dir,
        "doc_model_path": doc_model_path,
        "issues": [],
        "repair_record": [],
        "retry_count": 0,
        "MAX_RETRIES": max_retries,
        "gate_passed": False,
        "blocked_diagrams": [],
        "repair_staging_dir": str(BASE / "repair_1"),
    }

    final = diagram_repair_subgraph.invoke(initial)
    return dict(final)


def run_ui_qc(
    index_html_path: str,
    source_model_path: str,
    max_retries: int = 2,
) -> dict:
    """Run the UI repair subgraph and return the final state as a dict."""
    if ui_repair_subgraph is None:
        raise RuntimeError("LangGraph is not installed. Run: pip install langgraph")

    initial: UIQCState = {
        "index_html_path": index_html_path,
        "source_model_path": source_model_path,
        "static_failures": [],
        "runtime_failures": [],
        "repair_record": [],
        "retry_count": 0,
        "MAX_RETRIES": max_retries,
        "gate_passed": False,
        "repair_staging_dir": str(BASE / "ui_repair_1"),
    }

    final = ui_repair_subgraph.invoke(initial)
    return dict(final)


def run_final_review(
    index_html_path: str,
    source_model_path: str,
    max_retries: int = 2,
) -> dict:
    """Run the final-review subgraph and return the final state as a dict."""
    if final_review_subgraph is None:
        raise RuntimeError("LangGraph is not installed. Run: pip install langgraph")

    initial: FinalReviewState = {
        "index_html_path": index_html_path,
        "source_model_path": source_model_path,
        "validation_report_path": str(BASE / "validation-report.json"),
        "review_passed": False,
        "recommendations": [],
        "retry_count": 0,
        "MAX_RETRIES": max_retries,
        "blocked_checks": [],
    }

    final = final_review_subgraph.invoke(initial)
    return dict(final)