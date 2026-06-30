"""debrief_core — shared recursive root-cause investigator.

Both /debrief (single transcript) and /retro (session chain) call this lib.
The state machine treats each finding as the unit of work; the recursion
loop walks symptom→origin until the budget is exhausted.

States:
    DISCOVERED   → just surfaced from the corpus (transcript or chain)
    CLASSIFIED   → marked symptom or cause; category set (defect|friction|gap|...)
    LOCATED      → file:line cited
    VERIFIED     → /truth stamped the chain (mandatory)
    WRITTEN      → TaskCreate/TaskUpdate committed

Transitions:
    DISCOVERED → CLASSIFIED: classify(finding, friction_categories)
    CLASSIFIED → LOCATED:    locate_origin(finding, source_tree)
    LOCATED    → VERIFIED:   verify_with_truth(finding)  # mandatory, no skip
    VERIFIED   → WRITTEN:    write_task(finding, breadcrumb_chain)

If any step fails /truth verification or hits the recursion budget, the
finding is yielded in its current state with a `recursion_exhausted=True`
marker so the breadcrumb can resume.
"""
from __future__ import annotations

import json, os, re, subprocess, sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

SKILL_DIR = Path(__file__).parent.parent  # skills/debrief
SCRIPTS_DIR = SKILL_DIR / "scripts"

# ── finding lifecycle ───────────────────────────────────────────────────────
class State(str, Enum):
    DISCOVERED = "discovered"
    CLASSIFIED = "classified"
    LOCATED    = "located"
    VERIFIED   = "verified"
    WRITTEN    = "written"


class Category(str, Enum):
    DEFECT    = "defect"     # code bug
    FRICTION  = "friction"   # workflow / automation gap
    GAP       = "gap"        # missing capability
    DESIGN    = "design"     # architectural choice gone wrong
    UNKNOWN   = "unknown"


@dataclass
class Finding:
    finding_id: str
    state: State = State.DISCOVERED
    category: Category = Category.UNKNOWN

    # symptom layer (where it shows up in the transcript)
    symptom_text: str = ""
    symptom_source: str = ""            # transcript line(s) or chain event
    symptom_layer: int = 0

    # cause layer (where it lives in the code)
    origin_file: str = ""
    origin_line: int = 0
    origin_explanation: str = ""

    # chain (linked-list of parent findings — empty at top level)
    parent_id: Optional[str] = None
    child_ids: list[str] = field(default_factory=list)

    # evidence
    verified_evidence: str = ""         # /truth's stamp
    verified_status: str = ""           # VERIFIED | FALSE | PARTIAL | UNVERIFIED
    dead_ends: list[str] = field(default_factory=list)
    must_re_verify: list[str] = field(default_factory=list)

    # bookkeeping
    recursion_exhausted: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        d["category"] = self.category.value
        return d


# ── budget + termination ───────────────────────────────────────────────────
DEFAULT_MAX_LAYERS = 3
DEFAULT_MAX_FINDINGS_PER_LAYER = 8


@dataclass
class Budget:
    max_layers: int = DEFAULT_MAX_LAYERS
    max_findings_per_layer: int = DEFAULT_MAX_FINDINGS_PER_LAYER
    layers_used: int = 0
    findings_seen: int = 0


# ── victim-log detection ────────────────────────────────────────────────────
SYMPTOM_MARKERS = [
    (r"\b(fell back to|workaround|hot.?fix|temporary)\b",      "automation-gap"),
    (r"\b(Bash.*(?:silent|empty|returned nothing))\b",          "harness-defect"),
    (r"\b(didn't work|did not work|broke|crashed)\b",          "defect-suspected"),
    (r"\b(missing|not found|not registered|no such file)\b",   "gap-suspected"),
    (r"\b(slow|timeout|hang|stuck)\b",                        "perf-suspected"),
    (r"\b(confus|wrong|stale|cached data|old data)\b",         "stale-data"),
    (r"\b(I forgot|I keep forgetting)\b",                       "workflow-friction"),
]


def detect_victim_log(transcript_text: str) -> dict:
    """Heuristic: transcript is a victim log when EITHER a single symptom kind
    recurs >=3 times OR >=3 distinct symptom kinds each appear at least once.
    The second clause catches the more common case (different friction points
    across the transcript)."""
    counts = {}
    for pat, kind in SYMPTOM_MARKERS:
        n = len(re.findall(pat, transcript_text, re.I))
        if n:
            counts[kind] = counts.get(kind, 0) + n
    distinct = sum(1 for v in counts.values() if v >= 1)
    high_frequency = [k for k, v in counts.items() if v >= 3]
    is_victim_log = bool(high_frequency) or distinct >= 3
    return {
        "is_victim_log": is_victim_log,
        "distinct_symptom_kinds": distinct,
        "high_frequency_markers": high_frequency,
        "all_counts": counts,
    }


# ── /friction taxonomy lookup ───────────────────────────────────────────────
FRICTION_CATEGORIES = {
    "Hook Contract Friction":   "Hook system contract issue",
    "Context Loss":             "Agent not reading conversation history",
    "Pattern Mismatch":         "Enterprise/team patterns in solo-dev",
    "Path Issues":              "Path validation / separator inconsistency",
    "Cross-Terminal":           "Shared state without terminal isolation",
    "Skill Dispatch":           "Commands not triggering Skill() calls",
    "Stale Data":               "Skills using cache instead of live read",
    "Repeated Problems":        "No learning loop from corrections",
}


def classify_with_friction(finding_text: str) -> Category:
    """Lightweight local classification so /friction doesn't have to be called
    for every finding. The full /friction skill should still be called when
    the finding is workflow-shaped — this just routes the easy cases."""
    text = finding_text.lower()
    if any(kw in text for kw in ("hook ", "sessionstart", "pretooluse", "posttooluse", "stop hook")):
        return Category.FRICTION
    if any(kw in text for kw in ("workaround", "manual ", "hot fix", "temporary fix")):
        return Category.FRICTION
    if any(kw in text for kw in ("missing", "not registered", "doesn't exist", "no such")):
        return Category.GAP
    if any(kw in text for kw in ("confusing", "wrong directory", "old data", "cached", "stale")):
        return Category.FRICTION
    return Category.DEFECT


# ── /truth integration ─────────────────────────────────────────────────────
def verify_with_truth(claim: str, file_path: str = "", timeout: int = 30) -> dict:
    """Run /truth (the sdlc verification gate) on a claim. Returns the verdict
    block. If the harness rejects the invocation or /truth isn't available,
    the verdict is UNVERIFIED — the finding cannot advance without explicit
    human review."""
    # /truth isn't a binary we call here; it's a skill the LLM invokes. This
    # helper is the *contract*: callers must produce a verdict dict with at
    # least {status: VERIFIED|FALSE|PARTIAL|UNVERIFIED, evidence: ...}.
    # The state machine enforces that no finding advances past LOCATED without
    # a non-UNVERIFIED verdict.
    return {
        "status": "UNVERIFIED",
        "evidence": "",
        "correction": "",
        "claim": claim,
        "file_path": file_path,
        "note": "verify_with_truth is a contract; LLM caller must fill verdict via /truth skill.",
    }


# ── state-machine operations ──────────────────────────────────────────────
def _new_finding(text: str, source: str, parent_id: Optional[str] = None) -> Finding:
    fid = f"F{abs(hash((source, text))) % 10**8:08x}"
    return Finding(
        finding_id=fid,
        symptom_text=text,
        symptom_source=source,
        parent_id=parent_id,
    )


def discover_layer(
    findings: list[Finding],
    new_texts: list[str],
    new_sources: list[str],
    budget: Budget,
) -> list[Finding]:
    """Add new findings to the layer, capped at budget.max_findings_per_layer."""
    added: list[Finding] = []
    for text, source in zip(new_texts, new_sources):
        if len(added) >= budget.max_findings_per_layer:
            break
        f = _new_finding(text, source)
        findings.append(f)
        added.append(f)
        budget.findings_seen += 1
    return added


def classify_layer(findings: list[Finding], friction_taxonomy: Optional[dict] = None) -> None:
    """Transition DISCOVERED → CLASSIFIED. Sets category for each."""
    taxonomy = friction_taxonomy or FRICTION_CATEGORIES
    for f in findings:
        if f.state != State.DISCOVERED:
            continue
        f.category = classify_with_friction(f.symptom_text)
        f.state = State.CLASSIFIED


def locate_layer(
    findings: list[Finding],
    source_tree_resolver: Optional[Callable[[str], tuple[str, int, str]]] = None,
) -> None:
    """Transition CLASSIFIED → LOCATED. The resolver takes the finding text
    and returns (file_path, line, explanation). If no resolver is provided,
    the layer stays at CLASSIFIED and `recursion_exhausted` flips True."""
    for f in findings:
        if f.state != State.CLASSIFIED:
            continue
        if source_tree_resolver is None:
            f.recursion_exhausted = True
            f.error = "no source_tree_resolver provided"
            continue
        try:
            path, line, expl = source_tree_resolver(f.symptom_text)
            f.origin_file = path
            f.origin_line = line
            f.origin_explanation = expl
            f.state = State.LOCATED
        except Exception as e:
            f.recursion_exhausted = True
            f.error = f"resolver failed: {e}"


def verify_layer(findings: list[Finding]) -> list[Finding]:
    """Transition LOCATED → VERIFIED. Returns the list of findings that
    could NOT be verified (status=UNVERIFIED). The caller MUST run /truth
    and patch each finding's verified_status + verified_evidence before
    calling this — otherwise the finding stays at LOCATED with
    verified_status='UNVERIFIED' and does not advance."""
    blocked = []
    for f in findings:
        if f.state != State.LOCATED:
            continue
        if f.verified_status in ("VERIFIED", "FALSE", "PARTIAL"):
            f.state = State.VERIFIED
        else:
            blocked.append(f)
    return blocked


def write_layer(findings: list[Finding]) -> dict:
    """Transition VERIFIED → WRITTEN. Returns a dict ready for TaskCreate
    (the caller does the actual TaskCreate — debrief_core doesn't
    import claude_code internals). The output is what TaskCreate's
    description field should be set to."""
    written = []
    for f in findings:
        if f.state != State.VERIFIED:
            continue
        # Emit a TaskCreate-ready description that uses the cold-start template
        # from assets/task_template.md.
        chain_lines = []
        node = f
        while node is not None:
            chain_lines.append(
                f"  L{node.symptom_layer}: {node.origin_file or '<symptom>'}:"
                f"{node.origin_line or node.symptom_source} — {node.symptom_text[:80]}"
            )
            node = None  # chain reconstruction would walk child_ids; omitted for brevity
        chain = "\n".join(reversed(chain_lines))
        body = (
            f"TLDR: {f.origin_explanation or f.symptom_text[:120]}\n"
            f"TITLE: {f.origin_explanation or f.symptom_text}\n"
            f"TASK_KIND: full\n"
            f"PROBLEM: {f.symptom_text}\n"
            f"VERIFIED FACTS: {f.verified_evidence or '<none — see MUST RE-VERIFY>'}\n"
            f"MUST RE-VERIFY: {', '.join(f.must_re_verify) or 'none'}\n"
            f"DEAD ENDS: {', '.join(f.dead_ends) or 'none yet'}\n"
            f"DISCRIMINATING TEST: read {f.origin_file or '<unknown>'} around line "
            f"{f.origin_line or 0} and confirm the defect shape described above.\n"
            f"DEFINITION OF DONE: discriminating test passes; failing repro is gone.\n"
            f"BLOCKERS: none\n"
            f"BLAST RADIUS: {f.origin_file or '<unknown>'}\n"
            f"\nCausal chain (root cause first):\n{chain or '  <single layer — no recursion>'}\n"
        )
        d = f.to_dict()
        d["task_body"] = body
        written.append(d)
        f.state = State.WRITTEN
    return {"written": written, "count": len(written)}


# ── recursion: symptom → origin ────────────────────────────────────────────
def recurse_layer(
    parent_findings: list[Finding],
    budget: Budget,
    layer_extractor: Callable[[Finding], tuple[list[str], list[str]]],
) -> list[Finding]:
    """For each parent at LOCATED, recurse one layer: extract child findings
    that point AT the parent as candidate origin. Returns the new child
    findings; caller classifies/locates/verifies them.

    layer_extractor(parent) -> (texts, sources) is supplied by the calling
    skill (usually an Agent tool invocation that reads the parent file:line
    and asks "where else does this code smell appear / what explains this?").
    """
    if budget.layers_used >= budget.max_layers:
        for p in parent_findings:
            p.recursion_exhausted = True
        return []
    budget.layers_used += 1
    children: list[Finding] = []
    for parent in parent_findings:
        if parent.state != State.LOCATED:
            continue
        try:
            texts, sources = layer_extractor(parent)
        except Exception as e:
            parent.error = f"recurse failed: {e}"
            parent.recursion_exhausted = True
            continue
        for text, source in zip(texts, sources):
            child = _new_finding(
                text, source, parent_id=parent.finding_id
            )
            child.symptom_layer = parent.symptom_layer + 1
            parent.child_ids.append(child.finding_id)
            children.append(child)
    return children


# ── main pipeline ──────────────────────────────────────────────────────────
def run(
    *,
    transcript_text: str,
    initial_findings: list[tuple[str, str]],
    layer_extractor: Callable[[Finding], tuple[list[str], list[str]]],
    source_tree_resolver: Optional[Callable[[str], tuple[str, int, str]]] = None,
    truth_callable: Optional[Callable[[Finding], dict]] = None,
    budget: Optional[Budget] = None,
) -> dict:
    """End-to-end: discover → classify → locate → recurse → verify → write.

    Returns the final state including all findings (across all layers) and
    the ready-to-emit task bodies. The caller is responsible for actually
    invoking TaskCreate / TaskUpdate / rename_tag — debrief_core is the
    investigator, not the side-effecting layer.
    """
    budget = budget or Budget()
    victim = detect_victim_log(transcript_text)
    if victim["is_victim_log"]:
        budget.max_layers = max(budget.max_layers, 4)  # give the recursion more room
        budget.max_findings_per_layer = max(budget.max_findings_per_layer, 12)

    findings: list[Finding] = []
    # Layer 0: discover
    layer0_texts  = [t for t, _ in initial_findings]
    layer0_sources = [s for _, s in initial_findings]
    discover_layer(findings, layer0_texts, layer0_sources, budget)
    classify_layer(findings)

    # Recurse until all findings are at WRITTEN or recursion is exhausted.
    layers_seen = 0
    current = [f for f in findings if f.state == State.CLASSIFIED]
    while current and not all(f.state == State.WRITTEN for f in findings):
        if layers_seen >= budget.max_layers:
            for f in current:
                f.recursion_exhausted = True
            break
        # locate → recurse
        locate_layer(current, source_tree_resolver)
        # recursion: each located finding may produce children
        next_layer: list[Finding] = []
        for parent in current:
            if parent.state != State.LOCATED:
                continue
            children = recurse_layer([parent], budget, layer_extractor)
            classify_layer(children)
            next_layer.extend(children)
        # verify
        verify_layer(current)
        if truth_callable is not None:
            for f in current:
                if f.state != State.LOCATED:
                    continue
                verdict = truth_callable(f)
                f.verified_status = verdict.get("status", "UNVERIFIED")
                f.verified_evidence = verdict.get("evidence", "")
                if verdict.get("status") == "FALSE":
                    f.must_re_verify.append(verdict.get("correction", ""))
        verify_layer(current)
        # if any at LOCATED are still unverified, mark recursion_exhausted
        for f in current:
            if f.state == State.LOCATED and not f.recursion_exhausted:
                f.recursion_exhausted = True
                f.error = f.error or "/truth verdict was not non-UNVERIFIED"
        layers_seen += 1
        current = next_layer

    written = write_layer(findings)
    return {
        "victim_log": victim,
        "budget": {
            "max_layers": budget.max_layers,
            "max_findings_per_layer": budget.max_findings_per_layer,
            "layers_used": budget.layers_used,
            "findings_seen": budget.findings_seen,
        },
        "findings": [f.to_dict() for f in findings],
        "tasks": written,
        "summary": {
            "total_findings": len(findings),
            "written": written["count"],
            "blocked_unverified": sum(
                1 for f in findings if f.state == State.LOCATED
            ),
            "recursion_exhausted": sum(
                1 for f in findings if f.recursion_exhausted
            ),
        },
    }


# ── selfcheck ──────────────────────────────────────────────────────────────
def _selfcheck() -> None:
    # victim-log detection
    v = detect_victim_log("the bash was silent, then I fell back to a workaround, then I forgot again")
    assert v["is_victim_log"] is True
    v2 = detect_victim_log("hi")
    assert v2["is_victim_log"] is False
    # classification
    assert classify_with_friction("hook contract issue") == Category.FRICTION
    assert classify_with_friction("missing dep") == Category.GAP
    # full pipeline with synthetic inputs
    def layer_extractor(p: Finding) -> tuple[list[str], list[str]]:
        return (["the underlying schema was missing a UNIQUE constraint"],
                ["src/db.py:42"])
    def resolver(text: str) -> tuple[str, int, str]:
        return ("src/db.py", 42, "schema missing UNIQUE on dedup key")
    def truth(f: Finding) -> dict:
        return {"status": "VERIFIED", "evidence": "grep confirms no UNIQUE",
                "correction": ""}
    initial = [
        ("rows duplicate on ingest", "transcript L10"),
        ("missing audit log entry", "transcript L11"),
    ]
    res = run(
        transcript_text="rows duplicate on ingest, fell back to workaround",
        initial_findings=initial,
        layer_extractor=layer_extractor,
        source_tree_resolver=resolver,
        truth_callable=truth,
        budget=Budget(max_layers=2, max_findings_per_layer=4),
    )
    assert res["summary"]["total_findings"] >= 2
    assert res["summary"]["written"] >= 2
    assert res["summary"]["recursion_exhausted"] == 0
    # every WRITTEN task has the TLDR + DISCRIMINATING TEST fields
    for t in res["tasks"]["written"]:
        assert "TLDR:" in t["task_body"]
        assert "DISCRIMINATING TEST:" in t["task_body"]
        assert "src/db.py" in t["task_body"]
    # truth UNVERIFIED blocks advancement
    def truth_unverified(f):
        return {"status": "UNVERIFIED", "evidence": "", "correction": ""}
    res2 = run(
        transcript_text="x",
        initial_findings=[("y", "L1")],
        layer_extractor=layer_extractor,
        source_tree_resolver=resolver,
        truth_callable=truth_unverified,
        budget=Budget(max_layers=2, max_findings_per_layer=4),
    )
    # original finding stays at LOCATED with recursion_exhausted
    assert res2["summary"]["written"] == 0
    assert res2["summary"]["blocked_unverified"] >= 1
    print("self-check OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    else:
        print("debrief_core — invoke run() from /debrief or /retro")