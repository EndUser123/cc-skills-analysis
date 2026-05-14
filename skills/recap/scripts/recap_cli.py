#!/usr/bin/env python
"""CLI entry point for /recap skill."""

import sys
from pathlib import Path

# Add skills/ dir to path so 'recap' module (at skills/recap/__init__.py) is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from recap import main

if __name__ == "__main__":
    sys.exit(main())
