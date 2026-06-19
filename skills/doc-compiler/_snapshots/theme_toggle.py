
import sys
sys.path.insert(0, r'P:\packages\.github_repos\browser-harness')
from helpers import *
from admin import *
ensure_daemon()
new_tab("file:///P:\packages\cc-skills-meta\skills\doc-compiler\index.html")
wait_for_load()
time.sleep(0.5)
btn = js("document.getElementById('themeToggle')")
if btn:
    click(200, 40)
    time.sleep(1)
    print("__ASSERT_PASS__: theme toggle clicked")
else:
    print("__ASSERT_FAIL__: themeToggle not found")
screenshot(r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\theme_toggle.png')
print("__SNAP__:" + r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\theme_toggle.png')
