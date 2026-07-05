# Determinism Partition Rubric

For each *component* of a skill (each script, workflow step, agent dispatch, gate,
matcher, or output-formatter), decide which of four execution homes is optimal.
The goal is the **smallest error surface**: push work into deterministic code
where there is one correct answer, reserve the LLM for where there isn't, and use
graph orchestration only when the workflow is genuinely a non-trivial state
machine.

## The four homes

| Home | Use when | Don't use when |
|------|----------|----------------|
| **Deterministic Python** | There is ONE correct answer and it is reachable with stdlib + AST/regex/path/file I/O. Parsing, extraction, resolution, validation, counting, path math, gating. | The answer depends on judgment, semantics, or ranking. |
| **Deterministic TypeScript** | Same as Python, BUT the component runs in a JS/Node/bundler context (CLAUDE-plugin TS hooks, web frontends, Edge runtimes) and reusing the surrounding TS is cheaper than a Python sidecar. | The repo is Python-native and a TS file would be a one-off alien. Match the surrounding runtime, don't introduce a second language for one function. |
| **LangGraph (graph orchestration)** | The component is a **stateful multi-step workflow**: branching on intermediate results, loops with termination conditions, retries/fallbacks, parallel fan-out + join, or shared mutable state across >3 heterogeneous tool nodes. The graph *is* the value — encoding it explicitly beats ad-hoc Python control flow. | Linear pipelines (a→b→c), single-shot scripts, or anything with <3 nodes. A graph wrapper around a straight line is ceremony, not structure. Also overkill if Python `if/for` already expresses it in 10 lines. |
| **LLM** | The answer is genuinely non-deterministic: judgment, summarization, ranking, fuzzy semantic match, prose generation, "is this good?", code review, design choice between comparable options. | Anything with a single correct answer — sending it to the LLM adds cost, latency, and an error surface for zero gain. |

## Decision procedure (per component)

Run this ladder top-down; stop at the first match.

1. **Is there exactly one correct output for every input?**
   - YES → code (Python or TS, per the runtime-matching rule below). **Stop.**
   - NO → continue.
2. **Is it a stateful multi-step workflow with branching/loops/retries/fan-out over ≥3 heterogeneous nodes?**
   - YES → **LangGraph** (or whatever graph framework the repo already standardizes on). **Stop.**
   - NO → continue.
3. **Does it require judgment, semantics, ranking, or prose?**
   - YES → **LLM** (behind a deterministic harness that fixes the I/O contract — schema, input gathering, output validation). **Stop.**
4. **None of the above cleanly** → default to deterministic Python with the LLM as a fallback hint, and flag the component for human review. Don't silently park ambiguity in the LLM.

### Runtime-matching rule (Python vs TypeScript)
When the decision is "code," pick the language the surrounding code already uses:
- Python-native repo / stdlib need (AST, pathlib, subprocess to python tools) → **Python**.
- JS runtime / Node / browser / Edge / existing TS hooks → **TypeScript**.
- Cross-language: prefer the one that avoids spawning a second runtime per call.
A second language is justified only when the component's ecosystem advantage is real
(e.g. a TS-only SDK, a browser DOM) — not for novelty.

## Partition smells (deduct in the audit)

| Smell | What it signals | Fix direction |
|-------|-----------------|---------------|
| LLM doing extraction/counting/path-resolution the model hand-runs | Deterministic work parked in the wrong layer | Move to code (Python/TS) — the canonical gitpack `--skill` fix |
| Python `if/elif` chain encoding a 6-node state machine with retries | Graph-shaped problem in imperative clothing | Evaluate LangGraph (or the repo's graph framework) |
| LangGraph (or any graph framework) wrapping a linear a→b→c pipeline | Ceremony | Collapse to straight-line Python |
| TS file in a Python-only plugin (or vice versa) for one helper | Language mismatch | Inline in the dominant language |
| Gate/heuristic with magic thresholds and no `measured_tp_on_corpus` | Unverified discrimination | Code is fine; the *threshold* must be calibrated on a real corpus before it can block (advisory until then) |
| LLM called for a step that has a deterministic equivalent already in the repo | Reinvention | Reuse the existing code path |

## LangGraph specifically — when it earns its keep

LangGraph (and graph-based orchestration generally) is the right answer when the
**edges** carry as much meaning as the nodes. Concretely, prefer it when ≥2 of:
- Conditional edges (next node chosen from intermediate state, not a fixed order).
- Cycles (retry loops, refinement-until-stable, self-correction).
- Parallel fan-out + aggregation/join (scatter-gather over independent subtasks).
- Long-lived mutable state shared across many tool calls (checkpointing matters).
- Human-in-the-loop interrupts at defined graph points.

If only one applies, plain Python with functions usually wins (less ceremony,
easier to test). LangGraph's cost is a graph definition + state schema + node
contracts — pay it only when the graph is doing real work.

## Output format for the partition step

One row per component audited:

```
Component: <file:line | workflow step | agent | gate>
Current home: <Python | TS | LangGraph | LLM | mixed/unclear>
Recommended:  <Python | TS | LangGraph | LLM>
Basis:        <one-line reason citing the decision procedure step that fired>
Confidence:   high | medium | low   (low = needs human review; do not auto-edit)
```

Then a summary count: `N components → Python: a, TS: b, LangGraph: c, LLM: d,
review: e`. Recommendations of `Confidence: low` are surfaced as hypotheses, never
auto-applied — partition changes are architectural and hard to reverse.
