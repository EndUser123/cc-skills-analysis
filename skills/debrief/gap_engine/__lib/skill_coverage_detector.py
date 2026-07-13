"""Best-effort skill-coverage telemetry shared by analysis utilities.

Coverage is ancillary to detection, so filesystem failures remain non-fatal,
but successful calls still preserve the historical JSONL event contract.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _coverage_path(target_key: str) -> Path:
    safe_key = re.sub(r"[^\w\-.]", "_", target_key)[:200]
    return Path.home() / ".evidence" / "skill_coverage" / f"{safe_key}.jsonl"


def _append_skill_coverage(
    target_key: str,
    skill: str,
    terminal_id: str,
    git_sha: str | None = None,
    gap_ids_targeted: list[str] | None = None,
) -> bool:
    """Append one coverage event; telemetry failure never breaks callers."""

    path = _coverage_path(target_key)
    entry: dict[str, Any] = {
        "skill": skill,
        "target": target_key,
        "terminal_id": terminal_id,
        "timestamp": datetime.now().isoformat(),
        "git_sha": git_sha,
        "gap_ids_targeted": gap_ids_targeted or [],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
        return True
    except OSError:
        return False
