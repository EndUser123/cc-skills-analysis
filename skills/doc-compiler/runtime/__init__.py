"""doc-compiler runtime package."""
import sys
from pathlib import Path

# Ensure the parent (skills/) directory is on sys.path so `doc_compiler`
# can be imported as a package when running the orchestrator directly
# via `python runtime/orchestrator.py` or `python -m doc_compiler.runtime.orchestrator`
_runtimedir = Path(__file__).resolve().parent  # .../skills/doc-compiler/runtime
_parent = _runtimedir.parent  # .../skills/
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))