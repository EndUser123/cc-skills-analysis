#!/usr/bin/env python3
import sys, json, os
BH_DIR = "P:/packages/.github_repos/browser-harness"
if BH_DIR not in sys.path: sys.path.insert(0, BH_DIR)
from helpers import *
from admin import *
INDEX_PATH = "file:///P:/packages/cc-skills-meta/skills/doc-compiler/index.html"
SNAP_DIR = "P:/packages/cc-skills-meta/skills/doc-compiler/_snapshots"
os.makedirs(SNAP_DIR, exist_ok=True)
ensure_daemon()
new_tab(INDEX_PATH)
wait_for_load()
time.sleep(2)
results = {}
# A1: Desktop initial load
toc = js("document.getElementById('tocToggle')")
if toc:
    pos = js("getComputedStyle(toc).position")
    margin = js("getComputedStyle(document.querySelector('main-content')).marginLeft")
    passed1 = "fixed" in str(pos)
    results["desktop_initial"] = {"passed": passed1, "reason": f"pos={pos}, margin={margin}"}
else:
    results["desktop_initial"] = {"passed": False, "reason": "tocToggle not found"}
screenshot(os.path.join(SNAP_DIR, "desktop_initial.png"))
print("__SNAP__:" + os.path.join(SNAP_DIR, "desktop_initial.png"))
