#!/usr/bin/env python
"""Configure pytest to import the recap package from the skills directory."""

from __future__ import annotations

import sys
from pathlib import Path

# Add skills/ parent to path so 'recap' package (at skills/recap/__init__.py) is importable
_skills_root = Path(__file__).resolve().parent.parent.parent
if str(_skills_root) not in sys.path:
    sys.path.insert(0, str(_skills_root))
