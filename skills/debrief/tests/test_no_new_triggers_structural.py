"""Structural no-new-triggers test (replaces 4-token regex blacklists).

Authority: a forbidden-token list only catches commands whose names we
predicted. A new command with a new token slips through silently. This test
inverts the logic: enumerate every `triggers:` entry across all SKILL.md /
command files and assert each is in an explicit ALLOWLIST. A new command
(regardless of name) fails the test until the developer adds it to
ALLOWED_TRIGGERS.

How to use when adding a legitimate new command:
1. Add the command (SKILL.md / command file with `triggers:` block).
2. Run this test — it will fail with the new trigger name.
3. Add the name to ALLOWED_TRIGGERS below.
4. Re-run — test passes.

This makes "no new commands" PROVEN (structural diff), not PARTIAL (token
regex), per the CEC's `command_surface_changed` claim_type.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _find_packages_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "packages").is_dir():
            return parent
    raise RuntimeError(f"could not find packages/ from {cur}")


REPO_ROOT = _find_packages_root(Path(__file__))
PLUGIN_ROOT = REPO_ROOT / "packages/.claude-marketplace/plugins"


# Allowlist: every trigger that existed as of the CEC/XSTC/routing work.
# A new command is a deliberate surface change — add it here when shipped.
ALLOWED_TRIGGERS = frozenset({
    "/adv-review",
    "/all",
    "/ask",
    "/av",
    "/behave",
    "/bf",
    "/bifrost",
    "/bifrost-models",
    "/cks",
    "/claude-audit",
    "/constraints",
    "/csf-nip-integration",
    "/data-safety-vcs",
    "/debrief",
    "/dne",
    "/doc-compiler",
    "/dream",
    "/epistemic-check",
    "/friction",
    "/garden",
    "/genius",
    "/git",
    "/gitbatch",
    "/gitready",
    "/gto",
    "/id",
    "/init",
    "/learn",
    "/lmc",
    "/main",
    "/main-checkup",
    "/main-hooks",
    "/main-review",
    "/main-verify",
    "/mlc",
    "/mm-quota",
    "/nlm",
    "/nlm-to-wiki",
    "/nlm2wiki",
    "/notebooklm",
    "/pace",
    "/pre-mortem",
    "/probe",
    "/probe_quantile",
    "/prompt_refiner",
    "/prospect",
    "/ralph",
    "/reason",
    "/reason_grok",
    "/reason_openai",
    "/reason_ppx",
    "/recap",
    "/retro",
    "/review",
    "/rns",
    "/s",
    "/similarity",
    "/simplify",
    "/skill-similarity",
    "/skill-to-page",
    "/skeptic",
    "/slc",
    "/snapshot",
    "/think",
    "/top-problems",
    "/tot",
    "/trace",
    "/ut",
    "/why",
    "/{SKILL_NAME}",  # template placeholder (originally from skill-creator, now absorbed into skill-write) — not a real command
})


def _enumerate_triggers(root: Path) -> dict[str, list[str]]:
    """Return {trigger_name: [file paths where it appears as a trigger:]}."""
    found: dict[str, list[str]] = {}
    for path in root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(
            r"^triggers:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)",
            text,
            re.MULTILINE,
        )
        if not m:
            continue
        for line in m.group(1).splitlines():
            stripped = line.strip()
            if not stripped.startswith("-"):
                continue
            value = stripped[1:].strip().strip('"').strip("'").strip()
            if not value:
                continue
            # Take the first token (handle "- /foo bar" → "/foo")
            token = value.split()[0]
            if token.startswith("/"):
                found.setdefault(token, []).append(str(path))
    return found


def test_no_new_triggers_structural():
    """Every trigger: entry across plugins must be in ALLOWED_TRIGGERS.

    A failure means either:
    (a) a new command was added without updating the allowlist — add it; or
    (b) an unwanted new command was accidentally introduced — remove it.
    """
    found = _enumerate_triggers(PLUGIN_ROOT)
    unknown = {
        t: locs for t, locs in found.items() if t not in ALLOWED_TRIGGERS
    }
    if unknown:
        lines = ["Unknown triggers found (not in ALLOWED_TRIGGERS):"]
        for trigger, locs in sorted(unknown.items()):
            lines.append(f"  {trigger}")
            for loc in locs[:3]:
                lines.append(f"    in: {loc}")
        lines.append("")
        lines.append(
            "If this is a deliberate new command, add it to ALLOWED_TRIGGERS "
            "in test_no_new_triggers_structural.py."
        )
        pytest.fail("\n".join(lines))


def test_no_wiki_ingest_trigger():
    """/wiki-ingest must never appear as a trigger — it was explicitly
    rejected as a new command across multiple turns.

    This is a named check (not just 'not in allowlist') because the
    prohibition is policy, not just enumeration.
    """
    found = _enumerate_triggers(PLUGIN_ROOT)
    assert "/wiki-ingest" not in found, (
        f"/wiki-ingest appears as a trigger in: {found.get('/wiki-ingest', [])}"
    )


def test_no_cec_xstc_routing_triggers():
    """The CEC, XSTC, and routing-by-affordances work must NOT have introduced
    new commands. Named check so the policy is visible in the test name."""
    found = _enumerate_triggers(PLUGIN_ROOT)
    forbidden_by_this_work = (
        "/cec",
        "/completion-evidence",
        "/ledger",
        "/verify-claim",
        "/xstc",
        "/transfer-check",
        "/cross-skill",
        "/generalize-check",
    )
    for trigger in forbidden_by_this_work:
        assert trigger not in found, (
            f"{trigger} was introduced as a trigger — "
            f"CEC/XSTC/routing work must not add new commands"
        )