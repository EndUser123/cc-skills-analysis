#!/usr/bin/env python3
"""cc-skills-analysis router -- forwards hook events to plugin hook scripts.

Registered in settings.json as a single line per event:
    python <plugin>/__lib/router.py <EventName>

The router reads the event name from argv[1] and the hook payload from stdin,
then subprocess-runs the matching hook, forwarding stdin verbatim and exiting
with the hook's return code. The router does no work itself; the hook owns its
own timing and behavior. Currently only SessionEnd is wired.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REFLECT_HOOK = PLUGIN_ROOT / "skills" / "debrief" / "hooks" / "SessionEnd_debrief_reflect.py"


def main() -> None:
    event = sys.argv[1] if len(sys.argv) > 1 else None

    if event != "SessionEnd":
        sys.exit(0)

    input_data = sys.stdin.buffer.read()

    # ponytail: the router only forwards, so attempt-parse is contract ceremony;
    # we forward the ORIGINAL bytes regardless so the hook gets unmodified input.
    if input_data.strip():
        try:
            json.loads(input_data.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    if not REFLECT_HOOK.exists():
        sys.exit(0)

    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            [sys.executable, str(REFLECT_HOOK)],
            input=input_data,
            capture_output=True,
            creationflags=flags,
        )
        if result.stdout:
            sys.stdout.buffer.write(result.stdout)
            sys.stdout.flush()
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
            sys.stderr.flush()
        sys.exit(result.returncode)
    except Exception:
        # Never block the parent process; a hook failure is not fatal here.
        sys.exit(0)


if __name__ == "__main__":
    main()
