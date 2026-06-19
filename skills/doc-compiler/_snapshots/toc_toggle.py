
import sys
sys.path.insert(0, r'P:\packages\.github_repos\browser-harness')
from helpers import *
from admin import *
ensure_daemon()
new_tab("file:///P:\packages\cc-skills-meta\skills\doc-compiler\index.html")
wait_for_load()
time.sleep(0.5)
before_margin = js("getComputedStyle(document.querySelector('.main-content')).marginLeft")
before_collapsed = js("document.getElementById('toc').classList.contains('collapsed')")
print(f"Before: margin={before_margin}, collapsed={before_collapsed}")
click(30, 40)
time.sleep(0.5)
after_margin = js("getComputedStyle(document.querySelector('.main-content')).marginLeft")
after_collapsed = js("document.getElementById('toc').classList.contains('collapsed')")
print(f"After: margin={after_margin}, collapsed={after_collapsed}")
if str(before_collapsed) != str(after_collapsed):
    print("__ASSERT_PASS__")
else:
    print("__ASSERT_FAIL__: toggle did not change state")
screenshot(r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\toc_toggle.png')
print("__SNAP__:" + r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\toc_toggle.png')
