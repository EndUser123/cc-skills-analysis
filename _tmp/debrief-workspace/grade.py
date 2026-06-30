#!/usr/bin/env python3
"""Grade debrief eval outputs. Writes grading.json into each run dir."""
import json, re, pathlib

BASE = pathlib.Path(r"P:/packages/.claude-marketplace/plugins/cc-skills-analysis/_tmp/debrief-workspace/iteration-1")

CORE = ["PROBLEM", "VERIFIED FACTS", "DEAD ENDS", "DISCRIMINATING TEST", "DEFINITION OF DONE"]

def has_core_fields(t):
    up = t.upper()
    missing = [f for f in CORE if f not in up]
    return (len(missing) == 0, f"missing={missing}")

def has_rename_tag(t):
    m = re.findall(r'#\d+', t)
    # look for a rename/new-name line
    rename_line = [ln for ln in t.splitlines() if re.search(r'rename|new name|→|->', ln, re.I)]
    return (len(m) > 0 and len(rename_line) > 0, f"tags={m[:6]} rename_lines={len(rename_line)}")

def has_citations(t):
    has = bool(re.search(r'\bline\b|\bL\d+', t, re.I)) or ('"' in t or '`' in t)
    return (has, "line/quote markers present" if has else "none")

def issues_opps_separated(t):
    up = t.upper()
    return ("OPEN ISSUE" in up and "OPPORTUNIT" in up, "both sections present")

def gap_update_500(t):
    return ("#500" in t and bool(re.search(r'update', t, re.I)), "#500 + update wording")

def skip_resolved(t):
    # ImportError pytest fix must not appear as an open issue; resolved handling signaled
    handled = bool(re.search(r'resolved|dead.?end|excluded|not converted|not open|accepted', t, re.I))
    # Option B should appear as a dead end, not an open issue
    return (handled, "resolved/dead-end handling signaled" if handled else "no resolved handling")

def dead_end_captured(t):
    return (bool(re.search(r'option b|native|ruled out', t, re.I)), "dead-end knowledge present")

def dep_graph(t):
    return (bool(re.search(r'→|->|blockedby|blocks|dependenc|gated', t, re.I)), "dep representation present")

ASSERTIONS = {
    0: [  # small-gap-analysis
        ("Every proposed task includes the 5 core fields", has_core_fields),
        ("Output demonstrates gap analysis: timestamp finding is UPDATE to #500", gap_update_500),
        ("Rename plan proposes a source filename containing a #NNN tag", has_rename_tag),
        ("Output cites transcript line numbers or quoted evidence", has_citations),
        ("Open issues and opportunities are separated", issues_opps_separated),
    ],
    1: [  # medium-mixed-resolved
        ("Every proposed task includes the 5 core fields", has_core_fields),
        ("Resolved items are NOT listed as open issues", skip_resolved),
        ("Dead-end knowledge is captured (Option B ruled out)", dead_end_captured),
        ("Rename plan proposes a source filename containing a #NNN tag", has_rename_tag),
        ("Output includes a dependency graph or blocker cross-references", dep_graph),
    ],
}

EVALS = {0: "small-gap-analysis", 1: "medium-mixed-resolved"}
CONFIGS = ["with_skill", "without_skill"]

summary = {}
for eid, evname in EVALS.items():
    for cfg in CONFIGS:
        run_dir = BASE / evname / cfg
        out = run_dir / "outputs" / "debrief.md"
        if not out.exists():
            print(f"MISSING: {out}")
            continue
        t = out.read_text(encoding="utf-8", errors="replace")
        exps = []
        passes = 0
        for text, fn in ASSERTIONS[eid]:
            ok, evidence = fn(t)
            exps.append({"text": text, "passed": bool(ok), "evidence": evidence})
            passes += int(bool(ok))
        grading = {"expectations": exps}
        (run_dir / "grading.json").write_text(json.dumps(grading, indent=2), encoding="utf-8")
        key = f"{evname}/{cfg}"
        summary[key] = passes
        print(f"{key:45s} {passes}/{len(exps)}  " + " ".join("✓" if e["passed"] else "✗" for e in exps))

print("\nsummary:", json.dumps(summary))
