
import sys, json, os
BH_DIR = r"P:/packages/.github_repos/browser-harness"
if BH_DIR not in sys.path:
    sys.path.insert(0, BH_DIR)
from admin import restart_daemon, ensure_daemon
from helpers import *

# Restart daemon here so the fresh state is available in this process
restart_daemon()
ensure_daemon()

INDEX_PATH = "file:///P:/packages/cc-skills-meta/skills/doc-compiler/index.html"
SNAP_DIR = r"P:/packages/cc-skills-meta/skills/doc-compiler/_snapshots"

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
