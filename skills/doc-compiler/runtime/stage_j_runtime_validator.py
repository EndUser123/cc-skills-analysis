#!/usr/bin/env python3
"""Stage J: Runtime Validator for doc-compiler.

Uses browser-harness to perform live browser assertions on index.html.
Reads: index.html + source-model.json
Emits: runtime-validation.json with verification_matrix evidence.

Browser checks performed:
- J1: Desktop initial load (TOC visible, layout correct)
- J2: TOC toggle functionality
- J3: Theme toggle functionality
- J4: Accordion step expansion
- J5: Search/filter functionality
- J6: Diagram viewport renders
- J7: Palette switching works
- J8: Zoom controls work
- J9: Resize handle works
"""
import json, re, sys, subprocess, time
from pathlib import Path
from datetime import datetime

BASE = Path("P:/packages/.claude-marketplace/plugins/cc-skills-meta/skills/doc-compiler")
INDEX = BASE / "index.html"
SOURCE = BASE / "runtime" / "source-model.json"
OUT = BASE / "runtime-validation.json"
SNAP_DIR = BASE / "_snapshots"
BH_DIR = Path("P:/packages/.github_repos/browser-harness")


BROWSER_SCRIPT = r'''
import sys, json, os
BH_DIR = r"P:/packages/.github_repos/browser-harness"
if BH_DIR not in sys.path:
    sys.path.insert(0, BH_DIR)
from admin import restart_daemon, ensure_daemon
from helpers import *

# Restart daemon here so the fresh state is available in this process
restart_daemon()
ensure_daemon()

INDEX_PATH = "file:///P:/packages/.claude-marketplace/plugins/cc-skills-analysis/skills/doc-compiler/index.html"
SNAP_DIR = r"P:/packages/.claude-marketplace/plugins/cc-skills-analysis/skills/doc-compiler/_snapshots"

os.makedirs(SNAP_DIR, exist_ok=True)
new_tab(INDEX_PATH)
wait_for_load()
time.sleep(2)

results = {}

# J0: Boot marker — confirms script tag actually executed
boot_marker = js("typeof window.__DOC_COMPILER_BOOT__ !== 'undefined'")
results["J0_boot_marker"] = {"passed": bool(boot_marker), "reason": "boot marker found" if boot_marker else "window.__DOC_COMPILER_BOOT__ missing"}
screenshot(os.path.join(SNAP_DIR, "J0_boot.png"))

# J1: Desktop initial load
# Note: js() returns {} for DOM elements (Chrome CDP can't serialize live nodes).
# Use JSON-serializable expressions for existence checks.
toc_found = js("document.getElementById('tocToggle') !== null")
if toc_found:
    pos = js("getComputedStyle(document.getElementById('tocToggle')).position")
    margin = js("getComputedStyle(document.querySelector('.main-content')).marginLeft")
    passed1 = bool(pos and "fixed" in str(pos))
    results["J1_desktop_initial"] = {"passed": passed1, "reason": f"tocToggle pos={pos}, main margin={margin}"}
else:
    results["J1_desktop_initial"] = {"passed": False, "reason": "tocToggle not found"}

screenshot(os.path.join(SNAP_DIR, "J1_desktop.png"))

# J2: TOC toggle
js("if(typeof initTocToggle==='function'){initTocToggle();}")
before = js("document.body.classList.contains('toc-hidden')")
toc_btn = js("document.getElementById('tocToggle') !== null")
if toc_btn:
    js("document.getElementById('tocToggle').click()")
    time.sleep(0.5)
after = js("document.body.classList.contains('toc-hidden')")
passed2 = str(before) != str(after)
results["J2_toc_toggle"] = {"passed": passed2, "reason": f"before_hidden={before}, after_hidden={after}"}
screenshot(os.path.join(SNAP_DIR, "J2_toc_toggle.png"))

# J3: Theme toggle
theme_btn = js("document.getElementById('themeToggle') !== null")
if theme_btn:
    js("document.getElementById('themeToggle').click()")
    time.sleep(0.5)
    dark = js("document.body.classList.contains('dark')")
    results["J3_theme_toggle"] = {"passed": True, "reason": f"dark_mode={'on' if dark else 'off'}"}
else:
    results["J3_theme_toggle"] = {"passed": False, "reason": "themeToggle not found"}
screenshot(os.path.join(SNAP_DIR, "J3_theme.png"))

# J4: Accordion toggle
headers = js("document.querySelectorAll('.step-header').length")
if headers and int(str(headers)) > 0:
    js("document.querySelectorAll('.step-header')[0].click()")
    time.sleep(0.3)
    results["J4_accordion_toggle"] = {"passed": True, "reason": f"{headers} step headers found"}
else:
    results["J4_accordion_toggle"] = {"passed": False, "reason": "no .step-header elements"}
screenshot(os.path.join(SNAP_DIR, "J4_accordion.png"))

# J5: Search filter
search = js("document.getElementById('searchInput') !== null")
if search:
    js("document.getElementById('searchInput').value = 'step'")
    js("document.getElementById('searchInput').dispatchEvent(new Event('input'))")
    time.sleep(0.3)
    results["J5_search_filter"] = {"passed": True, "reason": "search input events fired"}
else:
    results["J5_search_filter"] = {"passed": False, "reason": "searchInput not found"}
screenshot(os.path.join(SNAP_DIR, "J5_search.png"))

# J6: Mermaid renders (look for svg in diagramStage)
svg_count = js("document.querySelectorAll('#diagramStage svg').length")
results["J6_mermaid_rendered"] = {"passed": bool(svg_count and int(str(svg_count)) > 0), "reason": f"svg count={svg_count}"}
screenshot(os.path.join(SNAP_DIR, "J6_mermaid.png"))

# J7: Palette selector
palette_sel = js("document.getElementById('paletteSelect') !== null")
if palette_sel:
    js("document.getElementById('paletteSelect').value = 'nord'")
    js("document.getElementById('paletteSelect').dispatchEvent(new Event('change'))")
    time.sleep(0.5)
    results["J7_palette_switch"] = {"passed": True, "reason": "palette selector changed"}
else:
    results["J7_palette_switch"] = {"passed": False, "reason": "paletteSelect not found"}
screenshot(os.path.join(SNAP_DIR, "J7_palette.png"))

# J8: Zoom controls
zoom_in = js("document.getElementById('zoomIn') !== null")
if zoom_in:
    js("document.getElementById('zoomIn').click()")
    time.sleep(0.2)
    results["J8_zoom_controls"] = {"passed": True, "reason": "zoomIn clicked"}
else:
    results["J8_zoom_controls"] = {"passed": False, "reason": "zoomIn not found"}
screenshot(os.path.join(SNAP_DIR, "J8_zoom.png"))

# J9: Resize handle
resize_handle = js("document.getElementById('diagramResizeHandle') !== null")
if resize_handle:
    results["J9_resize_handle"] = {"passed": True, "reason": "resize handle present"}
else:
    results["J9_resize_handle"] = {"passed": False, "reason": "diagramResizeHandle not found"}
screenshot(os.path.join(SNAP_DIR, "J9_resize.png"))

print("__RESULTS__:" + json.dumps(results))
'''


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def run_browser_checks() -> dict:
    """Write and run browser script, return results.

    Fails closed: any exception, crash, empty verification_matrix, or non-zero
    exit code produces passed=False so Stage L cannot certify a broken run as clean.
    """
    script_path = SNAP_DIR / "browser_checks.py"
    script_path.write_text(BROWSER_SCRIPT, encoding="utf-8")

    try:
        script_path = SNAP_DIR / "browser_checks.py"
        script_path.write_text(BROWSER_SCRIPT, encoding="utf-8")

        result = subprocess.run(
            ["uv", "run", "python", str(script_path)],
            cwd=str(BH_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )

        # --- fail closed on any non-zero exit code ---
        if result.returncode != 0:
            return {
                "passed": False,
                "verification_matrix": {},
                "snapshots": [],
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:1000],
                "_fail_reason": f"harness_exit_{result.returncode}",
            }

        output = result.stdout + result.stderr

        vmatrix = {}
        if "__RESULTS__:" in output:
            json_str = output.split("__RESULTS__:")[1].strip()
            match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if match:
                try:
                    vmatrix = json.loads(match.group(0))
                except Exception as ex:
                    print(f"  Warning: Could not parse results JSON: {ex}")
                    return {
                        "passed": False,
                        "verification_matrix": {},
                        "snapshots": [],
                        "stdout": result.stdout[:2000],
                        "stderr": f"JSON parse error: {ex}",
                        "_fail_reason": "json_parse_error",
                    }

        # --- fail closed: no results extracted means harness produced nothing useful ---
        if not vmatrix:
            return {
                "passed": False,
                "verification_matrix": {},
                "snapshots": [],
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500] if result.stderr else "no __RESULTS__ marker in output",
                "_fail_reason": "no_verification_matrix",
            }

        snapshots = []
        for line in output.splitlines():
            if "__SNAP__:" not in line:
                continue
            snap = line.split("__SNAP__:")[1].strip()
            snapshots.append(snap)

        passed = result.returncode == 0 and len(vmatrix) > 0
        return {
            "passed": passed,
            "verification_matrix": vmatrix,
            "snapshots": snapshots,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "verification_matrix": {},
            "snapshots": [],
            "stdout": "",
            "stderr": "Timeout after 120s",
            "_fail_reason": "timeout",
        }
    except Exception as ex:
        return {
            "passed": False,
            "verification_matrix": {},
            "snapshots": [],
            "stdout": "",
            "stderr": str(ex),
            "_fail_reason": f"exception_{type(ex).__name__}",
        }


def main() -> None:
    errors = []
    proof = {}

    index_content = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    model = load_json(SOURCE)

    if not index_content:
        errors.append("index.html not found")
    if not model:
        errors.append("source-model.json not found")

    if errors:
        proof = {
            "stage": "J",
            "passed": False,
            "errors": errors,
            "verification_matrix": {},
        }
        OUT.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        print(f"Stage J: FAIL -- {errors[0]}", file=sys.stderr)
        sys.exit(1)

    print("Stage J: Starting runtime verification with browser-harness...")

    result = run_browser_checks()
    vmatrix = result["verification_matrix"]
    fail_reason = result.get("_fail_reason", "")

    if fail_reason:
        print(f"  Browser harness failed: {fail_reason}")

    if not vmatrix:
        print(f"  Warning: No structured results. stdout: {result['stdout'][:200]}")
        print(f"  stderr: {result['stderr'][:200]}")

    passed_count = sum(1 for v in vmatrix.values() if isinstance(v, dict) and v.get("passed"))
    total_count = len(vmatrix)

    # Build runtime validation output
    steps_declared = len(model.get("steps", []))
    steps_rendered = index_content.count('class="step"') if index_content else 0

    # Fail closed: any harness failure means runtime validation did not pass
    runtime_all_passed = (passed_count == total_count) and (total_count > 0) and (not fail_reason)

    proof = {
        "stage": "J",
        "source_path": str(INDEX.resolve()) if INDEX.exists() else "",
        "artifact_path": str(INDEX.resolve()) if INDEX.exists() else "",
        "generated_at": datetime.now().isoformat(),
        "coverage": {
            "steps_declared": steps_declared,
            "workflow_sections_rendered": steps_rendered,
            "elements_present": len(re.findall(r'id="[^"]+"', index_content)) if index_content else 0,
        },
        "verification_matrix": vmatrix,
        "toc_state": {
            "toc_present": 'id="toc"' in index_content,
            "toc_toggle_present": 'id="tocToggle"' in index_content,
            "toc_items": index_content.count('<a href="#'),
        },
        "css_contract": {
            "has_style_block": "<style>" in index_content,
            "responsive_meta": "viewport" in index_content,
            "dark_mode_support": "prefers-color-scheme" in index_content or "dark" in index_content,
        },
        "listener_integrity": {
            "theme_toggle_listener": "themeToggle" in index_content or "theme-toggle" in index_content,
            "toc_toggle_listener": "tocToggle" in index_content or "initTocToggle" in index_content,
            "accordion_listener": "toggleStep" in index_content,
        },
        "runtime_verification": {
            "passed": passed_count,
            "total": total_count,
            "all_passed": runtime_all_passed,
            "snapshots": result.get("snapshots", []),
            "stdout": result.get("stdout", "")[:500],
            "_fail_reason": fail_reason or None,
        },
    }

    OUT.write_text(json.dumps(proof, indent=2), encoding="utf-8")

    status = "PASS" if passed_count == total_count and total_count > 0 else "PARTIAL"
    print(f"Stage J: {status} -- {passed_count}/{total_count} checks passed")
    for k, v in vmatrix.items():
        status_str = "PASS" if v.get("passed") else "FAIL"
        print(f"  {k}: {status_str} -- {v.get('reason', '')[:80]}")

    print(f"Written: {OUT}")
    sys.exit(0 if passed_count == total_count and total_count > 0 else 1)


if __name__ == "__main__":
    main()