"""dream_state — idempotency record for /debrief's dream cycle.

The dream cycle is the self-improvement loop: /debrief reviews topics (a
session, a friction category, a tsk-XXXX) and either acts on the findings or
just surfaces them. Without this record, every session would re-review the
same topics and produce redundant findings. With it, /debrief can answer
"have I already reviewed this?" and skip / mark complete / schedule re-review
based on a time threshold.

State shape (one JSON file, atomically rewritten):
    {
      "topics": {
        "<topic>": {
          "last_reviewed":   "<iso8601 utc>",   # when last reviewed
          "last_actioned":   <bool>,            # True if user acted on findings
          "findings":        ["<summary>", ...],# findings surfaced last review
          "findings_count":  <int>,             # len(findings) at write time
          "reviews":         <int>              # how many times reviewed
        },
        ...
      }
    }

Timestamps are stored as ISO 8601 strings (datetime.now(timezone.utc).isoformat())
so the JSON stays portable; comparisons parse them back to aware datetimes.
"""
from __future__ import annotations

import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ~/.claude/.artifacts/debrief/dream-state.json — single source of truth for
# the dream cycle. Parent dir is created lazily on first write.
STATE_PATH = Path.home() / ".claude" / ".artifacts" / "debrief" / "dream-state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str) -> datetime:
    # fromisoformat handles the offset-aware form we write; fall back to UTC
    # if a legacy naive timestamp ever appears.
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_last_dream_state() -> Optional[dict]:
    """Read the dream state file. Returns None if no state exists yet."""
    if not STATE_PATH.exists():
        return None
    try:
        with STATE_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable -> treat as no state. A subsequent
        # record_dream_review will atomically replace it.
        return None


def _write_state(state: dict) -> None:
    """Persist state atomically: write to .tmp, then os.replace. A crash
    during the write leaves the previous file (or no file) intact."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    payload = json.dumps(state, indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(tmp, STATE_PATH)


def record_dream_review(topic: str, findings: list[str], actioned: bool) -> None:
    """Record that a topic was reviewed in this dream cycle.

    - topic: short string like "model-routing-efficiency" or "tsk-XXXX"
    - findings: list of finding summaries surfaced in the review
    - actioned: True if the user acted on the findings this session, False if just surfaced
    """
    state = get_last_dream_state() or {"topics": {}}
    topics = state.setdefault("topics", {})
    entry = topics.get(topic, {})
    reviews = entry.get("reviews", 0) + 1
    topics[topic] = {
        "last_reviewed": _now_iso(),
        "last_actioned": bool(actioned),
        "findings": list(findings),
        "findings_count": len(findings),
        "reviews": reviews,
    }
    _write_state(state)


def should_re_review(topic: str, threshold_days: int = 7) -> bool:
    """Returns True if the topic should be re-reviewed. Logic:
    - No state for this topic -> True (never reviewed)
    - last actioned -> False (acted on; re-review only on explicit user opt-in)
    - last reviewed, not actioned, AND now - last_reviewed > threshold_days -> True
    - last reviewed, not actioned, AND within threshold -> False (recent, don't spam)
    """
    state = get_last_dream_state()
    if not state:
        return True
    entry = state.get("topics", {}).get(topic)
    if not entry:
        return True
    if entry.get("last_actioned"):
        return False
    last = _parse_iso(entry["last_reviewed"])
    age = datetime.now(timezone.utc) - last
    return age > timedelta(days=threshold_days)


def list_topics_since(days: int) -> list[dict]:
    """Return all topics reviewed in the last N days, sorted by
    last_reviewed desc. Each entry: {topic, last_reviewed, last_actioned,
    findings_count}. Useful for /main integration: 'what has /debrief been
    reviewing lately?'"""
    state = get_last_dream_state()
    if not state:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for topic, entry in state.get("topics", {}).items():
        last = _parse_iso(entry["last_reviewed"])
        if last >= cutoff:
            out.append({
                "topic": topic,
                "last_reviewed": entry["last_reviewed"],
                "last_actioned": entry.get("last_actioned", False),
                "findings_count": entry.get("findings_count", len(entry.get("findings", []))),
            })
    out.sort(key=lambda e: e["last_reviewed"], reverse=True)
    return out


def _delete_topic(topic: str) -> None:
    """Remove a topic from state (used by the self-check for cleanup)."""
    state = get_last_dream_state()
    if not state:
        return
    topics = state.get("topics", {})
    if topic in topics:
        del topics[topic]
        _write_state(state)


# ── selfcheck ──────────────────────────────────────────────────────────────
def _selfcheck() -> None:
    # 1. no state yet for the probe topic (either no file, or topic absent)
    record_dream_review("__dream_selfcheck_probe__", [], actioned=False)
    _delete_topic("__dream_selfcheck_probe__")
    probe_after_wipe = get_last_dream_state()
    if probe_after_wipe is not None:
        assert "__dream_selfcheck_probe__" not in probe_after_wipe.get("topics", {})

    # 2. record a review
    record_dream_review("test-topic", ["finding1", "finding2"], actioned=False)

    # 3. state reflects it
    state = get_last_dream_state()
    assert state is not None, "state should exist after record_dream_review"
    entry = state["topics"]["test-topic"]
    assert entry["findings"] == ["finding1", "finding2"], entry["findings"]
    assert entry["last_actioned"] is False
    assert entry["findings_count"] == 2

    # 4. recent + not actioned -> no re-review
    assert should_re_review("test-topic") is False

    # 5. actioned -> no re-review even past threshold
    record_dream_review("test-topic", ["finding1", "finding2"], actioned=True)
    assert should_re_review("test-topic", threshold_days=0) is False

    # 6. not actioned + threshold 0 -> re-review (forces the age branch)
    record_dream_review("test-topic", ["finding1", "finding2"], actioned=False)
    assert should_re_review("test-topic", threshold_days=0) is True

    # 7. never-reviewed topic -> re-review
    assert should_re_review("brand-new-topic-xyz") is True

    # 8. list_topics_since picks it up
    recent = list_topics_since(days=1)
    assert any(t["topic"] == "test-topic" for t in recent), recent

    # 9. cleanup: delete the test entry, leave state file valid
    _delete_topic("test-topic")
    state_after = get_last_dream_state()
    assert state_after is not None, "state file should still exist after cleanup"
    assert "test-topic" not in state_after.get("topics", {})

    print("dream_state self-check OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    else:
        _selfcheck()
