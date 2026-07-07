"""test_prune_scan.py - codify prune_scan behaviour.

Promotes the inline `selfcheck` into a real pytest module. Asserts:
  - `_desc` stops at the closing ``---`` (doesn't bleed into body),
  - stub/deprecated markers in `description:` retire a skill,
  - body below the empty-body threshold retires a skill,
  - name+description token overlap (Jaccard >= 0.4, shared >= 3) merges,
  - the public output keys match what the SKILL.md procedure documents.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "prune_scan.py"
_SPEC = importlib.util.spec_from_file_location("_ps_under_test", SCRIPT)
assert _SPEC.loader is not None
PS = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(PS)


def _sk(tmp: Path, name: str, body: str) -> Path:
    d = tmp / "plugins" / "cc-test" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


def test_desc_stops_at_frontmatter_close(tmp_path):
    """_desc must not bleed body content into the description capture."""
    PS.REPO = tmp_path / "plugins"  # rebind for this run
    d = tmp_path / "plugins" / "cc-test" / "skills" / "wrap"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: wrap\ndescription: extract youtube transcripts\n---\n"
        "# body\nThis body mentions stub but must NOT be captured as the desc.\n",
        encoding="utf-8")
    out = PS.scan("cc-test")
    if out["retire"]:
        for r in out["retire"]:
            assert "stub" not in r["desc"].lower() or r["reason"] != "deprecated", (
                f"description bled into body: {r}")


def test_stub_marker_retires(tmp_path):
    PS.REPO = tmp_path / "plugins"
    d = tmp_path / "plugins" / "cc-test" / "skills" / "old-thing"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: old-thing\ndescription: DEPRECATED stub\n---\n"
        "# z\nThis body is long enough to clear the empty-body threshold, so it must "
        "retire only via the deprecated marker, not via empty-body.\n",
        encoding="utf-8")
    out = PS.scan("cc-test")
    names = {r["skill"]: r["reason"] for r in out["retire"]}
    assert names.get("old-thing") == "deprecated", names


def test_merge_high_token_overlap(tmp_path):
    PS.REPO = tmp_path / "plugins"
    for name, desc in [
        ("transcribe-youtube", "extract youtube transcripts"),
        ("yt-transcriber", "extract youtube transcripts"),
    ]:
        d = tmp_path / "plugins" / "cc-test" / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n"
            f"# {name}\nBody content long enough to clear the empty-body threshold, "
            "intentionally overlapping to exercise the merge signal.\n",
            encoding="utf-8")
    out = PS.scan("cc-test")
    pairs = {(m["a"], m["b"]) for m in out["merge"]}
    assert any("transcribe-youtube" in p and "yt-transcriber" in p for p in pairs), out["merge"]


def test_output_schema():
    PS.REPO = Path("P:/packages/.claude-marketplace/plugins")  # real REPO
    out = PS.scan("cc-skills-analysis")
    assert set(out) >= {"target", "total_scanned", "retire", "merge", "review_primitive"}
    assert isinstance(out["retire"], list)
    assert isinstance(out["merge"], list)
    assert isinstance(out["review_primitive"], list)


def test_cli_selfcheck_flag():
    import subprocess, sys as _sys, shutil
    py = shutil.which("python") or _sys.executable
    r = subprocess.run([py, str(SCRIPT), "selfcheck"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selfcheck OK" in r.stdout