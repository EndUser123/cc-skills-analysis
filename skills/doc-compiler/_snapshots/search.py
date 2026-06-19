
import sys
sys.path.insert(0, r'P:\packages\.github_repos\browser-harness')
from helpers import *
from admin import *
ensure_daemon()
new_tab("file:///P:\packages\cc-skills-meta\skills\doc-compiler\index.html")
wait_for_load()
time.sleep(0.5)
inp = js("document.getElementById('searchInput')")
if inp:
    inp.value = "step"
    inp.dispatchEvent(new Event('input', {bubbles: true}))
    time.sleep(0.3)
    print("__ASSERT_PASS__: search attempted")
else:
    print("__ASSERT_FAIL__: searchInput not found")
screenshot(r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\search.png')
print("__SNAP__:" + r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\search.png')
