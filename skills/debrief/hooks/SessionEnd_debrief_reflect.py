#!/usr/bin/env python
# SessionEnd hook for the /debrief reflect pass (v1.0.38).
# Mines the just-finished session transcript for defects + opportunities,
# writes a candidate JSON file for HUMAN review. Never auto-edits anything.
# All string literals are single physical lines; multi-line text is built by
# concatenation. Exit 0 always; never block the parent process.
import sys
import os
import re
import json
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error
from pathlib import Path

# dream_state lives in the sibling __lib dir; insert absolute path so the
# import resolves regardless of the hook's launch cwd.
sys.path.insert(0, "P:/packages/.claude-marketplace/plugins/cc-skills-analysis/skills/debrief/__lib")
try:
    from dream_state import should_re_review, record_dream_review, get_last_dream_state
    _DREAM_AVAILABLE = True
except Exception as _e:
    _DREAM_AVAILABLE = False
    _DREAM_IMPORT_ERR = repr(_e)
try:
    from debrief_core import detect_deferred_reminder_cycle
    _DEFERRED_AVAILABLE = True
except Exception as _e:
    _DEFERRED_AVAILABLE = False
    _DEFERRED_IMPORT_ERR = repr(_e)

LOCAL_URL = "http://127.0.0.1:1234/v1/chat/completions"
LOCAL_MODEL = "ornith-1.0-9b@q4_k_m"
HOSTED_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_SEC = 30
MAX_TOKENS = 1500
MIN_LINES = 100
TAIL_LINES = 3000
CANDIDATES_DIR = Path.home() / ".claude" / ".artifacts" / "debrief"


def log(msg):
    # Terse one-line stderr events; never stdout.
    sys.stderr.write("[debrief-reflect] " + str(msg) + "\n")
    sys.stderr.flush()


def build_opportunity_schema():
    # 8-field opportunity schema, all required, strict.
    fields = ["seed_quote", "idea", "why_it_matters", "applies_to", "evidence_strength", "generalization_test", "promotion_target", "action"]
    props = {}
    props["seed_quote"] = {"type": "string"}
    props["idea"] = {"type": "string"}
    props["why_it_matters"] = {"type": "string"}
    props["applies_to"] = {"type": "array", "items": {"type": "string"}}
    props["evidence_strength"] = {"type": "string", "enum": ["explicit_user_ask", "user_correction", "repeated_pattern", "inferred", "weak"]}
    props["generalization_test"] = {"type": "string"}
    props["promotion_target"] = {"type": "string", "enum": ["skill", "hook", "memory", "docs", "backlog", "reject"]}
    props["action"] = {"type": "string"}
    schema = {"type": "object", "properties": props, "required": fields, "additionalProperties": False}
    return schema


def build_prompt(transcript_text):
    # Every literal below is a single physical line; newlines are explicit \n.
    p = "You are analyzing a transcript to improve future agent behavior.\n\n"
    p = p + "Return two arrays: defects[] and opportunities[].\n\n"
    p = p + "A defect is something that went wrong, caused user friction, rework, lower quality, or false completion, and should be fixed, prevented, tested, or documented.\n\n"
    p = p + "An opportunity is a reusable idea, correction, challenge, or workflow pattern surfaced by the transcript, that could improve future quality, usefulness, or rigor if preserved.\n\n"
    p = p + "For every opportunity, fill:\n"
    p = p + "- seed_quote (exact transcript excerpt)\n"
    p = p + "- idea (reusable improvement discovered)\n"
    p = p + "- why_it_matters (expected future benefit)\n"
    p = p + '- applies_to (array of strings; e.g. ["coding", "writing", "tool"])\n'
    p = p + "- evidence_strength (one of: explicit_user_ask | user_correction | repeated_pattern | inferred | weak)\n"
    p = p + "- generalization_test (how to prove this works beyond this one chat)\n"
    p = p + "- promotion_target (one of: skill | hook | memory | docs | backlog | reject)\n"
    p = p + "- action (concrete next step)\n\n"
    p = p + "Rules: prefer exact transcript evidence over inference. Ignore vague praise with no reusable lesson. Distinguish one-off instructions from durable rules. Mark duplicates against existing tasks/memory/skills when likely. If a candidate is plausible but weak, keep it as uncertain rather than promoting it.\n\n"
    p = p + "Return strict JSON only.\n\n"
    p = p + "Transcript:\n"
    p = p + transcript_text
    return p


def strip_fences(content):
    # Defensive markdown-strip for ``` or ```json fences.
    return re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content, flags=re.M)


def parse_reflect(content):
    # Returns dict with defects[] + opportunities[] or None on failure.
    if not content:
        return None
    text = strip_fences(content).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    defects = data.get("defects") if isinstance(data, dict) else None
    opportunities = data.get("opportunities") if isinstance(data, dict) else None
    if not isinstance(defects, list):
        defects = []
    if not isinstance(opportunities, list):
        opportunities = []
    return {"defects": defects, "opportunities": opportunities}


def read_tail_lines(path, n):
    # Read the last n lines without loading the whole file.
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return []
    if len(lines) > n:
        lines = lines[-n:]
    return lines


def count_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def call_local(prompt, schema):
    # LM Studio local 9B with response_format json_schema (verified accepted).
    body = {
        "model": LOCAL_MODEL,
        "temperature": 0.0,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "debrief_reflect", "schema": schema, "strict": True}},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(LOCAL_URL, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log("local call failed: " + repr(e))
        return None
    try:
        obj = json.loads(raw)
        return obj.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        log("local parse failed: " + repr(e))
        return None


def call_hosted(prompt):
    # Same prompt + schema via Anthropic messages; tool-use for structured output.
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log("hosted skip: no ANTHROPIC_AUTH_TOKEN/ANTHROPIC_API_KEY")
        return None
    schema = build_opportunity_schema()
    body = {
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{
            "name": "record_reflect",
            "description": "Record defects and opportunities from the transcript.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "defects": {"type": "array", "items": {"type": "string"}},
                    "opportunities": {"type": "array", "items": schema},
                },
                "required": ["defects", "opportunities"],
                "additionalProperties": False,
            },
        }],
        "tool_choice": {"type": "tool", "name": "record_reflect"},
    }
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["ANTHROPIC_AUTH_TOKEN"]
    else:
        headers["x-api-key"] = os.environ["ANTHROPIC_API_KEY"]
    req = urllib.request.Request(HOSTED_URL, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log("hosted tool call failed: " + repr(e))
        return call_hosted_plain(prompt, key)
    try:
        obj = json.loads(raw)
        for block in obj.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "record_reflect":
                return json.dumps(block.get("input", {}))
        # No tool_use block; fall back to any text block.
        for block in obj.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                return block.get("text")
        return None
    except Exception as e:
        log("hosted tool parse failed: " + repr(e))
        return call_hosted_plain(prompt, key)


def call_hosted_plain(prompt, key):
    # Fallback: plain completion if tool-use shape is unsupported.
    log("hosted fallback: plain completion")
    body = {
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["ANTHROPIC_AUTH_TOKEN"]
    else:
        headers["x-api-key"] = key
    req = urllib.request.Request(HOSTED_URL, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log("hosted plain call failed: " + repr(e))
        return None
    try:
        obj = json.loads(raw)
        for block in obj.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                return block.get("text")
        return None
    except Exception as e:
        log("hosted plain parse failed: " + repr(e))
        return None


def main():
    start_ts = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start_ts))
    log("start " + start_iso)
    try:
        payload_raw = sys.stdin.read()
    except Exception as e:
        log("stdin read failed: " + repr(e))
        sys.exit(0)
    try:
        payload = json.loads(payload_raw) if payload_raw.strip() else {}
    except Exception as e:
        log("payload parse failed: " + repr(e))
        sys.exit(0)
    if not isinstance(payload, dict):
        payload = {}
    session_id = payload.get("session_id")
    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        log("no transcript_path; exit 0")
        sys.exit(0)
    # Idempotency check.
    if session_id:
        done_file = CANDIDATES_DIR / (str(session_id) + ".done")
        if done_file.exists():
            log("already done for session " + str(session_id) + "; exit 0")
            sys.exit(0)
    # Length gate.
    line_count = count_lines(transcript_path)
    log("transcript lines: " + str(line_count))
    # Deferred-reminder cycle detection runs BEFORE the MIN_LINES gate: a
    # short transcript can still show re-deferral, and the detector is a cheap
    # regex count (no LLM, no API key). Reads the tail so the same text feeds
    # the LLM reflect path below. Single regex source: debrief_core.
    tail = read_tail_lines(transcript_path, TAIL_LINES)
    transcript_text = "".join(tail)
    try:
        if _DEFERRED_AVAILABLE:
            cycle = detect_deferred_reminder_cycle(transcript_text)
            if cycle["is_cycle"]:
                out_dir_pre = CANDIDATES_DIR / str(session_id) if session_id else CANDIDATES_DIR / "unknown"
                out_dir_pre.mkdir(parents=True, exist_ok=True)
                sf_pre = out_dir_pre / "system_findings.json"
                sf_payload = {
                    "session_id": session_id,
                    "produced_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                    "topic": "deferred-reminder-cycle",
                    "kind": "system-integrity",
                    "category": "design",
                    "finding_id": "deferred-reminder-cycle",
                    "count": cycle["count"],
                    "symptom_text": str(cycle["count"]) + " occurrences of 'deferral/defer that' in the transcript; the user has deferred this pattern multiple times",
                    "idea": "deferred-reminder pattern is repeating; consolidate rather than re-defer",
                    "generalization_test": "count of 'deferral/defer that' in transcript > 1",
                    "promotion_target": "backlog",
                    "evidence_strength": "repeated_pattern",
                    "findings": ["deferred-reminder pattern is repeating; consolidate rather than re-defer"],
                }
                with open(sf_pre, "w", encoding="utf-8") as f:
                    json.dump(sf_payload, f, indent=2)
                log("deferred-reminder: wrote system_findings.json (count=" + str(cycle["count"]) + ")")
        else:
            log("deferred-reminder: detector unavailable (" + str(_DEFERRED_IMPORT_ERR) + "); skipping")
    except Exception as e:
        log("deferred-reminder detection failed: " + type(e).__name__ + ": " + str(e))
    if line_count < MIN_LINES:
        log("transcript < " + str(MIN_LINES) + " lines; exit 0 (no candidates)")
        if session_id:
            mark_done(session_id)
        sys.exit(0)
    prompt = build_prompt(transcript_text)
    schema = build_opportunity_schema()
    # Tiered: local 9B first.
    model_used = None
    fallback_used = False
    reflect = None
    local_content = call_local(prompt, schema)
    if local_content:
        reflect = parse_reflect(local_content)
    if reflect is None:
        log("local produced no parseable output; trying hosted")
        fallback_used = True
        hosted_content = call_hosted(prompt)
        if hosted_content:
            reflect = parse_reflect(hosted_content)
            if reflect is not None:
                model_used = "claude-hosted"
    else:
        model_used = LOCAL_MODEL
    if reflect is None:
        # Both tiers failed or produced nothing usable; still record an empty
        # candidate file so a human can see the attempt happened.
        reflect = {"defects": [], "opportunities": []}
        if model_used is None:
            model_used = "none"
        log("no model produced output; writing empty candidates")
    # Write candidate file.
    try:
        out_dir = CANDIDATES_DIR / str(session_id) if session_id else CANDIDATES_DIR / "unknown"
        os.makedirs(out_dir, exist_ok=True)
        out_path = out_dir / "candidates.json"
        record = {
            "session_id": session_id,
            "transcript_path": transcript_path,
            "produced_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "model_used": model_used,
            "fallback_used": fallback_used,
            "candidates": reflect,
        }
        out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        log("wrote " + str(out_path))
    except Exception as e:
        log("write failed: " + repr(e) + "; exit 0")
        sys.exit(0)
    if session_id:
        mark_done(session_id)
    # === Dream-cycle integration ===
    # Surface a system_efficiency review if the last one is >7 days old.
    # This is an ADDITION to the reflect pass, not a replacement: candidates.json
    # above is unchanged. Wrapped in try/except so a dream-state failure never
    # breaks the reflect pass. See skills/debrief/__lib/dream_state.py.
    try:
        if _DREAM_AVAILABLE:
            now_iso = datetime.now(timezone.utc).isoformat()
            prev_state = get_last_dream_state()
            prev_entry = (prev_state or {}).get("topics", {}).get("system_efficiency") if isinstance(prev_state, dict) else None
            last_reviewed_iso = prev_entry.get("last_reviewed") if isinstance(prev_entry, dict) else None
            if should_re_review("system_efficiency", threshold_days=7):
                sf_dir = out_dir
                system_findings_path = sf_dir / "system_findings.json"
                dream_payload = {
                    "session_id": session_id,
                    "produced_at": now_iso,
                    "topic": "system_efficiency",
                    "kind": "dream-cycle review due",
                    "findings": ["model-routing review due (7+ days since last)"],
                    "last_reviewed": last_reviewed_iso,
                    "review_threshold_days": 7,
                    "promotion_target": "main",
                }
                system_findings_path.parent.mkdir(parents=True, exist_ok=True)
                # Merge, don't clobber: if a deferred-reminder finding was
                # written earlier, preserve it as a second entry rather than
                # overwriting with the dream payload.
                merged = [dream_payload]
                try:
                    if system_findings_path.exists():
                        existing = json.loads(system_findings_path.read_text(encoding="utf-8"))
                        if isinstance(existing, list):
                            merged = existing + [dream_payload]
                        elif isinstance(existing, dict) and existing.get("topic") != "system_efficiency":
                            merged = [existing, dream_payload]
                        else:
                            merged = [dream_payload]
                except Exception as me:
                    log("dream-cycle merge-read failed: " + repr(me) + "; overwriting")
                    merged = [dream_payload]
                with open(system_findings_path, "w", encoding="utf-8") as f:
                    json.dump(merged if len(merged) > 1 else dream_payload, f, indent=2)
                record_dream_review(topic="system_efficiency", findings=dream_payload["findings"], actioned=False)
                log("dream-cycle: wrote system_findings.json (system_efficiency review due)")
            else:
                log("dream-cycle: system_efficiency within threshold; skipping")
        else:
            log("dream-cycle: module unavailable (" + str(_DREAM_IMPORT_ERR) + "); skipping")
    except Exception as e:
        log("dream-cycle integration failed: " + type(e).__name__ + ": " + str(e))
    end_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    log("model=" + str(model_used) + " fallback=" + ("Y" if fallback_used else "N") + " opps=" + str(len(reflect.get("opportunities", []))))
    log("exit " + end_iso)
    sys.exit(0)


def mark_done(session_id):
    try:
        os.makedirs(CANDIDATES_DIR, exist_ok=True)
        done_file = CANDIDATES_DIR / (str(session_id) + ".done")
        with open(done_file, "w", encoding="utf-8"):
            os.chmod(done_file, 0o644)
    except Exception as e:
        log("mark_done failed: " + repr(e))


if __name__ == "__main__":
    main()
