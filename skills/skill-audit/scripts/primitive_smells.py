#!/usr/bin/env python3
"""primitive_smells.py - flag skills that may have chosen the wrong primitive.

A "primitive smell" is a skill whose structure suggests a different Claude Code
primitive would fit better. This script emits the mechanically-checkable signal:

  single-tool-wrapper — the skill's required_first_command_patterns + bash blocks
    revolve around ONE external CLI. If an MCP server already exposes that tool's
    capability, the MCP connector ("hands") may fit better than a skill ("habit").

The fuzzier "deterministic body -> should be a hook/CLI" judgment is left to the
LLM via references/determinism-partition-rubric.md; this script does not guess at
it (no measured_tp_on_corpus yet -> advisory only, never blocks).

Output: JSON on stdout. Emits nothing until invoked -> no context bloat (this is
the answer to the #7 "MCP-pref note bloats context" concern).

Usage:
  python primitive_smells.py <skill-dir|skill.md|all>
  python primitive_smells.py selfcheck
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from typing import Any

REPO = Path("P:/packages/.claude-marketplace/plugins")
MCP_CONFIG = Path(os.path.expanduser("~/.claude.json"))

# Leading command words that are language runtimes, not the wrapped tool.
_RUNTIME_TOKENS = {"python", "python3", "py", "node", "npx", "npm", "ruby",
                   "bash", "sh", "pwsh", "powershell", "go", "cargo", "uvx",
                   "uv", "pip", "dotnet"}
# ≥3 chars so regex metachars (\s) and short flags (-m) don't register as tools.
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _external_tool(pattern: str) -> str | None:
    """First non-runtime command token in a required_first_command pattern.

    `^nlm\\s+login\\s+--check` -> nlm ; `^python\\s+.*crv_run` -> crv_run.
    """
    for m in _TOKEN.finditer(pattern):
        tok = m.group(0).lower()
        if tok not in _RUNTIME_TOKENS:
            return tok
    return None


def _mcp_servers() -> dict[str, str]:
    """Configured MCP server name -> command string, from ~/.claude.json (all scopes)."""
    out: dict[str, str] = {}
    try:
        cfg = json.loads(MCP_CONFIG.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return out

    def collect(obj: Any) -> None:
        if isinstance(obj, dict):
            servers = obj.get("mcpServers")
            if isinstance(servers, dict):
                for name, spec in servers.items():
                    cmd = ""
                    if isinstance(spec, dict):
                        cmd = f"{spec.get('command', '')} {' '.join(spec.get('args', []) or [])}".strip()
                    out[name] = cmd
            for v in obj.values():
                collect(v)
    collect(cfg)
    return out


def _skill_paths(target: str) -> list[Path]:
    if target in ("all", "."):
        return list(REPO.glob("*/skills/*/SKILL.md"))
    p = Path(target)
    if p.is_dir():
        return list(p.rglob("SKILL.md"))
    return [p] if p.name.lower() == "skill.md" else []


def _tools_in_skill(text: str) -> set[str]:
    """Tools declared via required_first_command_patterns only.

    Bash blocks are intentionally NOT scanned — free-form shell prose (flags,
    subcommands, paths) produces too many false "tools" (measured: -m, --project-root,
    subcommand names). required_first_command_patterns is the authoritative, precise
    declaration of the tool a skill is bound to.
    """
    tools: set[str] = set()
    for m in re.finditer(r"^required_first_command_patterns:\s*\n((?:\s+-\s.*(?:\n|$))+)",
                         text, re.M):
        for line in m.group(1).splitlines():
            pat = line.strip().lstrip("-").strip().strip("'\"")
            if (t := _external_tool(pat)):
                tools.add(t)
    return tools


def analyze(skill_md: Path) -> dict[str, Any] | None:
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tools = _tools_in_skill(text)
    if not tools:
        return {"skill": skill_md.parent.name, "tools": [], "is_wrapper": False}
    return {
        "skill": skill_md.parent.name,
        "path": str(skill_md).replace("\\", "/"),
        "tools": sorted(tools),
        "is_wrapper": len(tools) == 1,
        "primary_tool": sorted(tools)[0] if len(tools) == 1 else None,
    }


def run(target: str) -> dict[str, Any]:
    servers = _mcp_servers()
    findings: list[dict[str, Any]] = []
    for sk in _skill_paths(target):
        a = analyze(sk)
        if not a or not a.get("is_wrapper"):
            continue
        tool = a["primary_tool"]
        mcp = [n for n, cmd in servers.items()
               if tool and (tool in n.lower() or tool in cmd.lower())]
        findings.append({
            "skill": a["skill"],
            "path": a["path"],
            "primary_tool": tool,
            "smell": "single-tool-wrapper",
            "mcp_candidates": mcp,
            "note": ("MCP equivalent may fit (hands over habit) — confirm the skill "
                     "adds judgment an MCP wouldn't" if mcp
                     else "wraps one CLI; confirm the skill adds judgment over a bare CLI/permission"),
        })
    return {"target": target, "mcp_servers_loaded": len(servers), "findings": findings}


def _selfcheck() -> None:
    import tempfile
    d = Path(tempfile.mkdtemp())
    sk = d / "wrap" / "SKILL.md"
    sk.parent.mkdir(parents=True)
    sk.write_text(
        "---\nname: wrap\nrequired_first_command_patterns:\n  - '^nlm\\s+login'\n---\n"
        "# wrap\n```bash\nnlm source list\n```\n",
        encoding="utf-8",
    )
    res = run(str(sk.parent))
    assert res["findings"], f"wrapper not detected: {res}"
    f0 = res["findings"][0]
    assert f0["primary_tool"] == "nlm", f0
    assert f0["smell"] == "single-tool-wrapper", f0
    # A two-tool skill must NOT be flagged as a wrapper.
    sk2 = d / "multi" / "SKILL.md"
    sk2.parent.mkdir(parents=True)
    sk2.write_text(
        "---\nname: multi\nrequired_first_command_patterns:\n  - '^nlm\\s+login'\n  - '^mmx\\s'\n---\n# multi\n",
        encoding="utf-8",
    )
    res2 = run(str(d))
    names = {f["skill"] for f in res2["findings"]}
    assert "wrap" in names and "multi" not in names, res2
    print("selfcheck OK: wrap flagged, multi not")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    if args[0] == "selfcheck":
        _selfcheck(); sys.exit(0)
    print(json.dumps(run(args[0]), indent=2))
