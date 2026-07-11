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

import json, os, re, subprocess, sys, hashlib
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


# NOTE: FindingKind is a new axis, not a replacement for Category. Category
# is the defect-side taxonomy; FindingKind is the lifecycle axis. Defects
# walk vertical recursion; opportunities walk lateral. They are
# orthogonal. Do not collapse one into the other.
class FindingKind(str, Enum):
    DEFECT      = "defect"
    OPPORTUNITY = "opportunity"


@dataclass
class Finding:
    finding_id: str
    state: State = State.DISCOVERED
    category: Category = Category.UNKNOWN
    kind: FindingKind = FindingKind.DEFECT

    # symptom layer (where it shows up in the transcript)
    symptom_text: str = ""
    symptom_source: str = ""            # transcript line(s) or chain event
    symptom_layer: int = 0

    # cause layer (where it lives in the code)
    origin_file: str = ""
    origin_line: int = 0
    origin_explanation: str = ""

    # principle extracted from the fix path (generalizable invariant, not
    # a one-off fix). Populated by the principle-extraction step in run()
    # between verify_layer and write_layer. If /truth verifies it, it goes
    # into the task body as the GENERALIZABLE_PRINCIPLE field.
    generalizable_principle: str = ""
    applies_to: str = ""                      # coding|research|writing|debugging|workflow|tool|unknown

    # opportunity layer (lateral) — populated for opportunities
    idea: str = ""                      # reusable pattern discovered
    generalization_test: str = ""      # how to prove it generalizes
    promote_to: str = ""                # cks|skill|hook|docs|memory|backlog|reject
    evidence_strength: str = ""        # explicit_user_ask|user_correction|repeated_pattern|inferred|weak

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
        d["kind"] = self.kind.value
        d["generalizable_principle"] = self.generalizable_principle
        d["applies_to"] = self.applies_to
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


# NOTE: New function, not a duplicate. detect_victim_log handles defects
# (symptoms of bugs); detect_opportunity_log handles good ideas (what
# worked, what to generalize, what's worth promoting). They are
# orthogonal detectors; the calling skill can run both in parallel.
OPPORTUNITY_MARKERS = [
    (r"\b(this (worked|trick|approach) (really|well)?|the trick was)\b", "what-worked"),
    (r"\b(we should|let's (also|always)|generalize this|make this a habit)\b", "should-do"),
    (r"\b(good idea|useful idea|great idea|worth (keeping|remembering))\b", "explicit-idea"),
    (r"\b(makes? (this|it) (better|more useful|more productive)|better quality|more effective)\b", "quality-improvement"),
    (r"\b(fell back to|switched to|ended up (using|on)|the trick was|workaround that stuck|what worked was|settled on)\b", "problem-recovery"),
    (r"\b(in any domain|cross-?domain|everywhere|always (do|apply))\b", "domain-general"),
    (r"\b(deferral|defer that)\b", "deferred-reminder"),
    # Behavioral/heuristic patterns (added 2026-07-02): surface thinking/behavior
    # quality issues so /debrief pattern-mines for them, not just code/conversation.
    # Tuned LOOSE — false positives cost a tag, false negatives miss a learning.
    # promote_to defaults to docs/memory at the task-creation step.
    (r"\b(marked (the )?(task|verification|smoke).{0,40}complete|complete.{0,30}(task|verification|smoke))", "verification-skip"),
    (r"\b(before (running|actually )?(the )?(verification|smoke|test|it|this)|without (running|actually )?(the )?(verification|smoke|test))", "verification-skip"),
    (r"\b(local (strictly )?dominates|dominates (over|on)|my (local )?(copy|version) dominates)\b", "axis-mismatch"),
    (r"\b(based on (my )?(memory|recall)|I (read|recall) (the|a)? (file|memory|earlier)|from (memory|recall))\b", "memory-as-evidence"),
    (r"\b(skip(ping)? plan(-mode)? ceremony|skip plan mode|just execute|just (do|run) it|skip the ceremony)\b", "plan-mode-bypass"),
    (r"\b(marked .{0,30}complete (before|without)|complete(d)? .{0,30}(before|without|but not))\b", "premature-completion"),
]


def detect_opportunity_log(transcript_text: str) -> dict:
    """Heuristic: transcript is rich in opportunity signals when EITHER
    >=2 distinct opportunity kinds appear OR an explicit-idea marker
    (good/useful/great/worth-keeping) appears at least once. Mirror of
    detect_victim_log's structure so the calling skill can run both
    detectors in parallel and treat them as orthogonal axes.
    """
    counts = {}
    for pat, kind in OPPORTUNITY_MARKERS:
        n = len(re.findall(pat, transcript_text, re.I))
        if n:
            counts[kind] = counts.get(kind, 0) + n
    distinct = sum(1 for v in counts.values() if v >= 1)
    explicit = counts.get("explicit-idea", 0)
    is_opportunity_log = bool(explicit) or distinct >= 2
    return {
        "is_opportunity_log": is_opportunity_log,
        "distinct_kinds": distinct,
        "explicit_idea_count": explicit,
        "all_counts": counts,
    }


# NOTE: New detector, not a duplicate. detect_victim_log and
# detect_opportunity_log aggregate across many marker kinds; this one targets a
# single kind ("deferred-reminder") and fires a cycle when it repeats, because
# re-deferring the same pattern is a system-integrity smell, not a generic
# opportunity. The kind label matches the OPPORTUNITY_MARKERS tuple above.
DEFERRED_REMINDER_MARKER = r"\b(deferral|defer that)\b"


def detect_deferred_reminder_cycle(transcript_text: str) -> dict:
    """Heuristic: a deferred-reminder cycle when the user re-defers the same
    pattern >1 time. Returns count + is_cycle. Re-deferral is a
    system-integrity finding (consolidate, don't re-defer), distinct from a
    one-off opportunity. Kept separate from detect_opportunity_log so the
    emission path can carry a 'system-integrity' topic."""
    count = len(re.findall(DEFERRED_REMINDER_MARKER, transcript_text, re.I))
    return {"count": count, "is_cycle": count > 1, "topic": "deferred-reminder-cycle"}


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


# ── causal chain reconstruction ──────────────────────────────────────────────
def _reconstruct_chain(f: Finding, index: dict[str, Finding]) -> list[str]:
    """Walk parent_id links from a finding to reconstruct the full causal chain.
    Emits root cause first (earliest ancestor). Includes cycle protection via
    a visited set and a missing-parent marker when a parent_id does not resolve.
    Bounded at 100 depth to prevent infinite loops from malformed input."""
    visited: set[str] = set()
    chain: list[str] = []
    node = f
    depth = 0
    while node is not None and depth < 100:
        visited.add(node.finding_id)
        chain.append(
            f"  L{node.symptom_layer}: {node.origin_file or '<symptom>'}:"
            f"{node.origin_line or node.symptom_source} — {node.symptom_text[:80]}"
        )
        if node.parent_id:
            if node.parent_id in visited:
                chain.append(f"  <cycle detected at {node.parent_id} — chain truncated>")
                break
            parent = index.get(node.parent_id)
            if parent is None:
                chain.append(f"  <missing parent {node.parent_id}>")
                break
            node = parent
        else:
            node = None
        depth += 1
    # Reverse: root cause first
    return list(reversed(chain))


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
def _stable_fid(*parts: str) -> str:
    """Deterministic 8-hex finding id from the source+text (and any parent id),
    so two runs of the same input produce byte-identical artifact JSON — the
    'deterministic, auditable run' contract debrief.py:13 promises. Python's
    built-in hash() is salted per-process and breaks that contract."""
    raw = "\x00".join(str(p) for p in parts).encode("utf-8")
    return f"F{hashlib.sha256(raw).hexdigest()[:8]}"


def _new_finding(text: str, source: str, parent_id: Optional[str] = None) -> Finding:
    fid = _stable_fid(source, text)
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
    rejected = []
    findings_by_id = {f.finding_id: f for f in findings}
    for f in findings:
        if f.state != State.VERIFIED:
            continue
        if f.kind != FindingKind.DEFECT:
            # Keep the defect writer closed to lateral findings even if a
            # future caller accidentally supplies an origin for an opportunity.
            f.recursion_exhausted = True
            note = "opportunity cannot enter the defect writer"
            if note not in f.must_re_verify:
                f.must_re_verify.append(note)
            rejected.append(f)
            continue
        # Safety guard: an under-resolved finding must not produce a WRITTEN
        # task with <unknown> placeholders. The cheap experiment showed that
        # defect and opportunity inputs both reach this function; without the
        # guard, opportunity inputs were silently emitted as phantom defect
        # tasks. Now: stay at VERIFIED with recursion_exhausted=True and a
        # clear must_re_verify note.
        if not f.origin_file or f.origin_line == 0:
            f.recursion_exhausted = True
            if "no origin_file resolved; investigation did not converge" not in f.must_re_verify:
                f.must_re_verify.append("no origin_file resolved; investigation did not converge")
            rejected.append(f)
            continue
        # Reconstruct the full causal chain by walking parent_id links.
        chain_lines = _reconstruct_chain(f, findings_by_id)
        chain = "\n".join(reversed(chain_lines))
        body = (
            f"TLDR: {f.origin_explanation or f.symptom_text[:120]}\n"
            f"TITLE: {f.origin_explanation or f.symptom_text}\n"
            f"TASK_KIND: full\n"
            f"PROBLEM: {f.symptom_text}\n"
            f"VERIFIED FACTS: {f.verified_evidence or '<none — see MUST RE-VERIFY>'}\n"
            f"MUST RE-VERIFY: {', '.join(f.must_re_verify) or 'none'}\n"
            + (f"GENERALIZABLE_PRINCIPLE: {f.generalizable_principle}\nAPPLIES_TO: {f.applies_to or 'unknown'}\n" if f.generalizable_principle else "")
            + f"DEAD ENDS: {', '.join(f.dead_ends) or 'none yet'}\n"
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
    return {"written": written, "rejected": rejected, "count": len(written)}


# NOTE: New function, not a duplicate of write_layer. write_layer is the
# defect (vertical) writer; write_opportunity_layer is the opportunity
# (lateral) writer. Both share the VERIFIED -> WRITTEN transition, the
# safety-guard pattern, and the dict return shape.
def write_opportunity_layer(findings: list[Finding]) -> dict:
    """Lateral pipeline for FindingKind.OPPORTUNITY. No origin_file
    (opportunities aren't anchored at code), no recursive locate step.
    Safety guard: an opportunity without idea or generalization_test is
    rejected, not silently fabricated. Weak-evidence findings are demoted
    to PROMOTE_TO:reject.
    """
    written = []
    rejected = []
    for f in findings:
        if f.state != State.VERIFIED:
            continue
        if f.kind != FindingKind.OPPORTUNITY:
            continue
        if not f.idea:
            f.recursion_exhausted = True
            f.must_re_verify.append("opportunity has no idea field; transcription step did not produce a reusable pattern")
            rejected.append(f)
            continue
        if not f.generalization_test:
            f.recursion_exhausted = True
            f.must_re_verify.append("opportunity has no generalization_test; cannot promote without a way to prove the pattern generalizes")
            rejected.append(f)
            continue
        if f.evidence_strength == "weak":
            f.recursion_exhausted = True
            f.promote_to = "reject"
            f.must_re_verify.append("opportunity evidence is weak; demoted to PROMOTE_TO:reject per rejection rules")
            rejected.append(f)
            continue
        body = "TLDR: " + f.idea[:120] + "\n" + \
            "TITLE: Promote: " + f.idea[:80] + "\n" + \
            "TASK_KIND: opportunity-full\n" + \
            "SEED: " + str(f.symptom_source) + " — " + f.symptom_text[:120] + "\n" + \
            "IDEA: " + f.idea + "\n" + \
            "WHY: " + (f.origin_explanation or "expected future leverage from this pattern") + "\n" + \
            "EVIDENCE: " + (f.evidence_strength or "inferred") + "\n" + \
            "PROMOTE_TO: " + (f.promote_to or "backlog") + "\n" + \
            "GENERALIZATION_TEST: " + f.generalization_test + "\n" + \
            "ACTION: concrete next step required (e.g., 'update SKILL.md', 'add cks entry', 'create hook')\n" + \
            "VERIFIED FACTS: " + (f.verified_evidence or "<none — see MUST RE-VERIFY>") + "\n" + \
            "MUST RE-VERIFY: " + (", ".join(f.must_re_verify) or "none") + "\n" + \
            "DEAD ENDS: " + (", ".join(f.dead_ends) or "none yet") + "\n" + \
            "DISCRIMINATING TEST: run the GENERALIZATION_TEST in a second, unrelated transcript; if the pattern still applies, promote as evidenced.\n" + \
            "DEFINITION OF DONE: GENERALIZATION_TEST passes in a second context; opportunity is then either promoted to " + (f.promote_to or "backlog") + " or rejected with a one-line reason.\n" + \
            "BLOCKERS: none\n" + \
            "BLAST RADIUS: " + (f.promote_to or "backlog") + " surface; no code changes by default.\n"
        d = f.to_dict()
        d["task_body"] = body
        written.append(d)
        f.state = State.WRITTEN
    return {"written": written, "rejected": rejected, "count": len(written)}


# ── recursion: symptom → origin ────────────────────────────────────────────
def recurse_layer(
    parent_findings: list[Finding],
    budget: Budget,
    layer_extractor: Callable[[Finding], tuple[list[str], list[str]]],
    visited: Optional[set[str]] = None,
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
    visited = visited if visited is not None else set()
    budget.layers_used += 1
    children: list[Finding] = []
    for parent in parent_findings:
        if parent.state != State.LOCATED:
            continue
        if parent.finding_id in visited:
            parent.recursion_exhausted = True
            continue
        visited.add(parent.finding_id)
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
def extract_generalizable_principle(f, truth_callable):
    """For a VERIFIED defect finding, ask the LLM (via the truth_callable
    callback) whether the fix path contains a generalizable principle.

    Contract for truth_callable: it must be called as
    `truth_callable(claim=..., file_path=...)` and return a verdict dict
    with at least {status: VERIFIED|FALSE|PARTIAL|UNVERIFIED, evidence: str}.
    This function never calls the LLM itself; it relies on the same
    truth_callable that the rest of the pipeline uses. That way /truth
    is the single verification gate.

    Returns: (principle, applies_to, verdict_status) where:
    - principle: str, the extracted generalizable invariant (or "" if none)
    - applies_to: str, one of coding|research|writing|debugging|workflow|tool|unknown
    - verdict_status: str, the /truth verdict on the principle claim
    """
    if not f.origin_explanation:
        return ("", "", "SKIPPED")
    claim = "the fix for " + (f.origin_file or "this bug") + " is a generalizable principle beyond this one instance"
    if truth_callable is None:
        return ("", "", "SKIPPED")
    verdict = truth_callable(claim=claim, file_path=f.origin_file or "")
    status = verdict.get("status", "UNVERIFIED")
    if status in ("VERIFIED", "PARTIAL"):
        principle = verdict.get("evidence", "")
        applies_to = verdict.get("applies_to", "unknown")
        if not principle:
            return ("", "", status)
        return (principle[:200], applies_to, status)
    return ("", "", status)


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
    # Deferred-reminder cycle: when "deferral/defer that" repeats >1 time the
    # user is re-deferring the same pattern. Surface it as a system-integrity
    # OPPORTUNITY finding (lateral, no code origin) so the caller can write a
    # consolidate-rather-than-re-defer task. Detected here so both /debrief
    # (run()) and the SessionEnd hook (which calls the shared detector) see it
    # from one regex. Not part of the defect recursion loop.
    deferred_cycle = detect_deferred_reminder_cycle(transcript_text)
    deferred_finding: Optional[Finding] = None
    if deferred_cycle["is_cycle"]:
        dr_count = deferred_cycle["count"]
        df = Finding(
            finding_id=_stable_fid("deferred-reminder", str(dr_count)),
            state=State.DISCOVERED,
            category=Category.DESIGN,
            kind=FindingKind.OPPORTUNITY,
            symptom_text=f"{dr_count} occurrences of 'deferral/defer that' in the transcript; the user has deferred this pattern multiple times",
            symptom_source="deferred-reminder-cycle detector",
            idea="deferred-reminder pattern is repeating; consolidate rather than re-defer",
            generalization_test="count of 'deferral/defer that' in transcript > 1",
            promote_to="backlog",
            evidence_strength="repeated_pattern",
        )
        deferred_finding = df
        findings.append(df)
        classify_layer([df])

    # Layer 0: discover — accept both (text, source) tuples and structured dicts
    for item in initial_findings:
        if isinstance(item, dict):
            # Structured finding dict -> create Finding with all fields preserved
            kind = FindingKind.DEFECT
            try:
                kind = FindingKind(item.get("kind", "defect"))
            except ValueError:
                pass
            category = Category.UNKNOWN
            try:
                category = Category(item.get("category", "unknown"))
            except ValueError:
                pass
            f = Finding(
                finding_id=_stable_fid(
                    item.get("symptom_source", ""),
                    item.get("symptom_text", ""),
                ),
                symptom_text=item.get("symptom_text", ""),
                symptom_source=item.get("symptom_source", ""),
                kind=kind,
                category=category,
                idea=item.get("idea", ""),
                generalization_test=item.get("generalization_test", ""),
                promote_to=item.get("promote_to", ""),
                evidence_strength=item.get("evidence_strength", ""),
            )
            findings.append(f)
        else:
            # Tuple (text, source) — backward compatible
            text, source = item
            f = _new_finding(text, source)
            findings.append(f)
    classify_layer(findings)

    # Recurse until all findings are at WRITTEN or recursion is exhausted.
    layers_seen = 0
    visited_findings: set[str] = set()
    current = [f for f in findings if f.state == State.CLASSIFIED]
    while current and not all(f.state == State.WRITTEN for f in findings):
        if layers_seen >= budget.max_layers:
            for f in current:
                f.recursion_exhausted = True
            break
        # Opportunities bypass the locate requirement (no origin_file/line needed)
        # BEFORE locate_layer runs, since locate_layer with no resolver sets
        # recursion_exhausted on all CLASSIFIED findings.
        for f in current:
            if f.kind == FindingKind.OPPORTUNITY and f.state == State.CLASSIFIED:
                f.state = State.LOCATED
                if not f.origin_file:
                    f.origin_file = "<opportunity>"
        # locate → recurse
        locate_layer(current, source_tree_resolver)
        # recursion: each located finding may produce children
        next_layer: list[Finding] = []
        for parent in current:
            if parent.state != State.LOCATED:
                continue
            children = recurse_layer([parent], budget, layer_extractor, visited_findings)
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

    # Principle extraction: for each VERIFIED defect finding, ask the LLM
    # whether the fix path is a generalizable principle. The principle
    # rides along in the task body above the discriminating test, so the
    # next LLM sees the principle before deciding how to act.
    if truth_callable is not None:
        for f in findings:
            if f.state == State.VERIFIED and f.kind == FindingKind.DEFECT and not f.generalizable_principle:
                # Build an adapter that passes the actual principle claim and
                # source file to the verifier, NOT the original finding.
                # extract_generalizable_principle calls truth_callable(claim=, file_path=);
                # we wrap the pipeline's truth_callable(f: Finding) to match that contract.
                def _make_claim_adapter(finding, tc):
                    def _adapter(claim="", file_path=""):
                        # Build a synthetic Finding for the principle claim so the
                        # pipeline truth_callable (which expects a Finding) can evaluate it.
                        pf = Finding(
                            finding_id=f"p-{finding.finding_id}",
                            symptom_text=claim,
                            origin_file=file_path or finding.origin_file,
                        )
                        return tc(pf) or {}
                    return _adapter
                principle_truth = _make_claim_adapter(f, truth_callable)
                principle, applies_to, status = extract_generalizable_principle(f, principle_truth)
                if principle:
                    f.generalizable_principle = principle
                    f.applies_to = applies_to
    # Route verified findings: defects through write_layer, opportunities
    # through write_opportunity_layer (lateral pipeline, no origin_file needed).
    # Opportunities must still clear the idea + generalization_test guards.
    defect_findings = [f for f in findings if f.kind == FindingKind.DEFECT]
    opportunity_findings = [f for f in findings if f.kind == FindingKind.OPPORTUNITY]
    written = write_layer(defect_findings)
    if opportunity_findings:
        opp_result = write_opportunity_layer(opportunity_findings)
        written["written"] = written["written"] + opp_result["written"]
        written["rejected"] = written["rejected"] + opp_result["rejected"]
        written["count"] = written["count"] + opp_result["count"]
        written["opportunities_written"] = opp_result["count"]
    else:
        written["opportunities_written"] = 0
    written["opportunities_skipped"] = 0  # no longer skipped; see opportunities_written
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
            "opportunities_written": written.get("opportunities_written", 0),
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
    # 7th: principle extraction populates the principle field when /truth
    # verifies the fix path is a generalizable invariant. The truth mock
    # follows the (claim=, file_path=) contract the pipeline reuses; a
    # lambda avoids re-declaring a helper def.
    truth_principle = lambda claim, file_path="": {
        "status": "VERIFIED",
        "evidence": "any tool that crashes on list input needs a type guard",
        "correction": "",
        "applies_to": "coding",
    }
    fp = Finding(
        finding_id="p7", state=State.VERIFIED, kind=FindingKind.DEFECT,
        category=Category.DEFECT,
        origin_file="src/foo.py", origin_line=42,
        origin_explanation="guard the .lower() on a list",
    )
    p, a, s = extract_generalizable_principle(fp, truth_principle)
    assert p, "principle should populate when /truth verifies the fix path"
    assert p.startswith("any tool that crashes"), f"unexpected principle: {p!r}"
    assert a == "coding", f"unexpected applies_to: {a!r}"
    assert s == "VERIFIED", s
    fp.generalizable_principle = p
    fp.applies_to = a
    res7 = write_layer([fp])
    assert len(res7["written"]) == 1
    body7 = res7["written"][0]["task_body"]
    assert "GENERALIZABLE_PRINCIPLE:" in body7, f"principle not rendered:\n{body7}"
    assert "APPLIES_TO: coding" in body7, f"applies_to not rendered:\n{body7}"
    assert "type guard" in body7
    print("self-check OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    else:
        print("debrief_core — invoke run() from /debrief or /retro")
