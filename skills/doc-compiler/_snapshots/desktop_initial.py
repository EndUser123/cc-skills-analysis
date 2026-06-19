
import sys
sys.path.insert(0, r'P:\packages\.github_repos\browser-harness')
from helpers import *
from admin import *
ensure_daemon()
new_tab("file:///P:\packages\cc-skills-meta\skills\doc-compiler\index.html")
wait_for_load()
time.sleep(0.5)
pos = js("getComputedStyle(document.getElementById('tocToggle')).position")
margin = js("getComputedStyle(document.querySelector('.main-content')).marginLeft")
print("__ASSERT_PASS__" if "fixed" in str(pos) else "__ASSERT_FAIL__")
print(f"tocToggle.position={pos}, main-content.marginLeft={margin}")
screenshot(r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\desktop_initial.png')
print("__SNAP__:" + r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\desktop_initial.png')
