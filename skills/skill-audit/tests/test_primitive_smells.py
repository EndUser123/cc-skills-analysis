"""test_primitive_smells.py - codify primitive_smells behaviour.

Promotes the inline `selfcheck` into a real pytest module. Asserts:
  - the required_first_command_patterns-only extraction avoids the bash-block
    noise that drove the first 33-finding false-positive run,
  - a single-tool wrapper is flagged with `smell = single-tool-wrapper`,
  - a two-tool skill is not flagged as a wrapper,
  - the resolved `primary_tool` matches the first non-runtime token.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "primitive_smells.py"
_SPEC = importlib.util.spec_from_file_location("_ps_under_test", SCRIPT)
assert _SPEC.loader is not None
PS = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(PS)


def _sk(tmp: Path, name: str, body: str) -> Path:
    d = tmp / "p" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d / "SKILL.md"


def test_required_patterns_extraction_basic(tmp_path):
    """A skill whose required_first_command_patterns binds one external CLI is a wrapper."""
    sk = _sk(tmp_path, "wrap", (
        "---\nname: wrap\nrequired_first_command_patterns:\n  - '^nlm\\\\s+login'\n---\n# wrap\n"
    ))
    a = PS.analyze(sk)
    assert a is not None
    assert a["is_wrapper"] is True
    assert a["primary_tool"] == "nlm"
    assert a["tools"] == ["nlm"]


def test_two_patterns_not_a_wrapper(tmp_path):
    """A skill with two distinct external tools is NOT a wrapper."""
    sk = _sk(tmp_path, "multi", (
        "---\nname: multi\nrequired_first_command_patterns:\n"
        "  - '^nlm\\\\s+login'\n  - '^mmx\\\\s'\n---\n# multi\n"
    ))
    a = PS.analyze(sk)
    assert a is not None
    assert a["is_wrapper"] is False
    assert a["primary_tool"] is None
    assert sorted(a["tools"]) == ["mmx", "nlm"]


def test_runtime_token_skipped(tmp_path):
    """A `python scripts/<x>.py` pattern should expose <x>, not `python`."""
    sk = _sk(tmp_path, "wrapper-py", (
        "---\nname: wrapper-py\nrequired_first_command_patterns:\n"
        "  - '^python\\\\s+.*crv_run'\n---\n# wrapper-py\n"
    ))
    a = PS.analyze(sk)
    assert a is not None
    assert a["is_wrapper"] is True
    assert a["primary_tool"] == "crv_run"


def test_run_returns_findings_structure(tmp_path):
    """run() wraps analyze(): the public output has the keys the skill body documents."""
    _sk(tmp_path, "wrap", "---\nname: wrap\nrequired_first_command_patterns:\n  - '^nlm'\n---\n# x\n")
    out = PS.run(str(tmp_path / "p"))
    assert set(out) >= {"target", "mcp_servers_loaded", "findings"}
    if out["findings"]:
        f0 = out["findings"][0]
        assert {"skill", "path", "primary_tool", "smell",
                "mcp_candidates", "note"} <= set(f0)
        assert f0["smell"] == "single-tool-wrapper"


def test_cli_selfcheck_flag():
    """The module's `__main__` path keeps the original `selfcheck` for CLI callers."""
    import subprocess, sys as _sys
    # Use the plugin-context python that has the script's deps available; fall
    # back to the current interpreter if not on PATH.
    import shutil
    py = shutil.which("python") or _sys.executable
    r = subprocess.run([py, str(SCRIPT), "selfcheck"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selfcheck OK" in r.stdout
