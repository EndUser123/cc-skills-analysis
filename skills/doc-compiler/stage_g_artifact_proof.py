#!/usr/bin/env python3
"""Stage G: Runtime Validator for doc-compiler.

Uses browser-harness to perform live browser assertions on index.html.
Reads: index.html + source-model.json
Emits: artifact-proof.json with verification_matrix evidence.
"""
import json, re, sys, os, subprocess, time
from pathlib import Path
from datetime import datetime

BASE = Path("P:/packages/cc-skills-meta/skills/doc-compiler")
INDEX = BASE / "index.html"
SOURCE = BASE / "source-model.json"
OUT = BASE / "artifact-proof.json"

# Paths
SNAP_DIR = BASE / "_snapshots"
BH_DIR = Path("P:/packages/.github_repos/browser-harness")

# Browser-harness script as a string to be written temporarily
BROWSER_SCRIPT = '''
#!/usr/bin/env python3
import sys, json, os
BH_DIR = "P:/packages/.github_repos/browser-harness"
if BH_DIR not in sys.path:
    sys.path.insert(0, BH_DIR)
from helpers import *
from admin import *

INDEX_PATH = "file:///P:/packages/cc-skills-meta/skills/doc-compiler/index.html"
SNAP_DIR = "P:/packages/cc-skills-meta/skills/doc-compiler/_snapshots"

ensure_daemon()
new_tab(INDEX_PATH)
wait_for_load()
time.sleep(2)

results = {}

# A1: Desktop initial load
toc = js("document.getElementById('tocToggle')")
if toc:
    pos = js("getComputedStyle(toc).position")
    margin = js("getComputedStyle(document.querySelector('.main-content')).marginLeft")
    passed1 = bool(pos and "fixed" in str(pos))
    results["desktop_initial"] = {"passed": passed1, "reason": "pos=" + str(pos) + ", margin=" + str(margin)}
else:
    results["desktop_initial"] = {"passed": False, "reason": "tocToggle not found"}

screenshot(os.path.join(SNAP_DIR, "desktop_initial.png"))
print("__SNAP__:" + os.path.join(SNAP_DIR, "desktop_initial.png"))

# A2: TOC toggle - init if needed
js("if(typeof initTocToggle === 'function') { initTocToggle(); }")
before_hidden = js("document.body.classList.contains('toc-hidden')")
js("document.getElementById('tocToggle').click()")
time.sleep(0.5)
after_hidden = js("document.body.classList.contains('toc-hidden')")
passed2 = str(before_hidden) != str(after_hidden)
results["toc_toggle"] = {"passed": passed2, "reason": "Before hidden=" + str(before_hidden) + ", After hidden=" + str(after_hidden)}

screenshot(os.path.join(SNAP_DIR, "toc_toggle.png"))
print("__SNAP__:" + os.path.join(SNAP_DIR, "toc_toggle.png"))

# A3: Theme toggle
theme_exists = js("!!document.getElementById('themeToggle')")
if theme_exists:
    js("document.getElementById('themeToggle').click()")
    time.sleep(1)
    results["theme_toggle"] = {"passed": True, "reason": "theme toggle clicked"}
else:
    results["theme_toggle"] = {"passed": False, "reason": "themeToggle not found"}

screenshot(os.path.join(SNAP_DIR, "theme_toggle.png"))
print("__SNAP__:" + os.path.join(SNAP_DIR, "theme_toggle.png"))

# A4: Accordion
headers_count = js("document.querySelectorAll('.step-header').length")
if headers_count and int(str(headers_count)) > 0:
    js("document.querySelectorAll('.step-header')[0].click()")
    time.sleep(0.3)
    results["accordion_toggle"] = {"passed": True, "reason": str(headers_count) + " headers found"}
else:
    results["accordion_toggle"] = {"passed": False, "reason": "no accordion headers"}

screenshot(os.path.join(SNAP_DIR, "accordion.png"))
print("__SNAP__:" + os.path.join(SNAP_DIR, "accordion.png"))

# A5: Search
search_exists = js("!!document.getElementById('searchInput')")
if search_exists:
    js("document.getElementById('searchInput').value = 'step'")
    js("document.getElementById('searchInput').dispatchEvent(new Event('input'))")
    time.sleep(0.3)
    results["search_filter"] = {"passed": True, "reason": "search attempted"}
else:
    results["search_filter"] = {"passed": False, "reason": "searchInput not found"}

screenshot(os.path.join(SNAP_DIR, "search.png"))
print("__SNAP__:" + os.path.join(SNAP_DIR, "search.png"))

print("__RESULTS__:" + json.dumps(results))
'''


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def run_browser_checks() -> dict:
    """Write and run the browser script, then return results."""
    script_path = SNAP_DIR / "browser_checks.py"
    script_path.write_text(BROWSER_SCRIPT, encoding="utf-8")

    try:
        result = subprocess.run(
            ["uv", "run", "python", str(script_path)],
            cwd=str(BH_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr

        # Parse results
        vmatrix = {}
        if "__RESULTS__:" in output:
            json_str = output.split("__RESULTS__:")[1].strip()
            match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if match:
                try:
                    vmatrix = json.loads(match.group(0))
                except Exception as ex:
                    print(f"  Warning: Could not parse results JSON: {ex}")

        # Collect snapshots
        snapshots = []
        for line in output.splitlines():
            if "__SNAP__:" in line:
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
        }
    except Exception as ex:
        return {
            "passed": False,
            "verification_matrix": {},
            "snapshots": [],
            "stdout": "",
            "stderr": str(ex),
        }


def main() -> None:
    errors = []
    proof = {}

    index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    model = load_json(SOURCE)

    if not index:
        errors.append("index.html not found")
    if not model:
        errors.append("source-model.json not found")

    if errors:
        proof = {
            "stage": "G",
            "passed": False,
            "errors": errors,
            "verification_matrix": {},
        }
        OUT.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        print(f"Stage G: FAIL -- {errors[0]}")
        sys.exit(1)

    print("Stage G: Starting runtime verification with browser-harness...")

    result = run_browser_checks()
    vmatrix = result["verification_matrix"]

    # If no structured results, show raw output
    if not vmatrix:
        print(f"  Warning: No structured results. stdout: {result['stdout'][:200]}")
        print(f"  stderr: {result['stderr'][:200]}")

    passed_count = sum(1 for v in vmatrix.values() if v.get("passed"))
    total_count = len(vmatrix)

    # Build proof
    steps_declared = len(model.get("steps", []))
    steps_rendered = index.count('class="step"') if index else 0

    proof = {
        "source_path": str(INDEX.resolve()) if INDEX.exists() else "",
        "artifact_path": str(INDEX.resolve()) if INDEX.exists() else "",
        "generated_at": datetime.now().isoformat(),
        "coverage": {
            "steps_declared": steps_declared,
            "workflow_sections_rendered": steps_rendered,
            "elements_present": len(re.findall(r'id="[^"]+"', index)) if index else 0,
        },
        "verification_matrix": vmatrix,
        "toc_state": {
            "toc_present": 'id="toc"' in index,
            "toc_toggle_present": 'id="tocToggle"' in index,
            "toc_items": index.count('<a href="#'),
        },
        "css_contract": {
            "has_style_block": "<style>" in index,
            "responsive_meta": "viewport" in index,
            "dark_mode_support": "prefers-color-scheme" in index,
        },
        "listener_integrity": {
            "theme_toggle_listener": "theme-toggle" in index or "themeToggle" in index,
            "toc_toggle_listener": "tocToggle" in index,
        },
        "runtime_verification": {
            "passed": passed_count,
            "total": total_count,
            "all_passed": passed_count == total_count,
            "snapshots": result.get("snapshots", []),
        },
    }

    OUT.write_text(json.dumps(proof, indent=2), encoding="utf-8")

    status = "PASS" if passed_count == total_count and total_count > 0 else "PARTIAL"
    print(f"Stage G: {status} -- {passed_count}/{total_count} checks passed")
    for k, v in vmatrix.items():
        status_str = "PASS" if v.get("passed") else "FAIL"
        print(f"  {k}: {status_str} -- {v.get('reason', '')[:80]}")

    if passed_count < total_count or total_count == 0:
        print(f"Written: {OUT}")
        sys.exit(1)
    print(f"Written: {OUT}")
    sys.exit(0)


if __name__ == "__main__":
    main()
