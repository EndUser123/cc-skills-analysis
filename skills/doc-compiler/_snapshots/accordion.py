
import sys
sys.path.insert(0, r'P:\packages\.github_repos\browser-harness')
from helpers import *
from admin import *
ensure_daemon()
new_tab("file:///P:\packages\cc-skills-meta\skills\doc-compiler\index.html")
wait_for_load()
time.sleep(0.5)
headers = js("Array.from(document.querySelectorAll('.step-header')).slice(0,2)")
if headers and len(headers) > 0:
    headers[0].click()
    time.sleep(0.3)
    print("__ASSERT_PASS__: accordion interaction attempted")
else:
    print("__ASSERT_FAIL__: no accordion headers found")
screenshot(r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\accordion.png')
print("__SNAP__:" + r'P:\packages\cc-skills-meta\skills\doc-compiler\_snapshots\accordion.png')
