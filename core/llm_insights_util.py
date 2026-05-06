"""
Shared helpers for Block 7 insight modules: Anthropic JSON calls, rate limits, logging.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("llm_insights")

INSIGHTS_MODEL = os.getenv("HERMES_LLM_INSIGHTS_MODEL", "claude-opus-4-7")
_MAX_PER_HOUR = int(os.getenv("HERMES_INSIGHTS_LLM_MAX_PER_HOUR", "20"))
_WINDOW_SEC = 3600.0

_BASE = Path(__file__).resolve().parent.parent
_LOG_FILE = _BASE / "logs" / "llm_insights.log"

_times: list[float] = []
_times_lock = threading.Lock()


def _ensure_log() -> None:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_insight_event(kind: str, payload: dict[str, Any]) -> None:
    """Append one JSON line per LLM / insight event."""
    _ensure_log()
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        **payload,
    }
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        log.warning("llm_insights.log write failed: %s", exc)


def insights_rate_limit_ok() -> tuple[bool, str]:
    """True if another LLM call is allowed this rolling hour."""
    with _times_lock:
        now = time.time()
        global _times
        _times = [t for t in _times if now - t < _WINDOW_SEC]
        if len(_times) >= _MAX_PER_HOUR:
            return False, (
                f"LLM call limit reached ({_MAX_PER_HOUR}/hour). Try again later."
            )
        return True, ""


def insights_record_successful_call() -> None:
    with _times_lock:
        _times.append(time.time())


def call_insights_llm_json(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 4096,
    kind: str = "generic",
) -> dict[str, Any]:
    """
    Synchronous Anthropic Messages call; returns parsed JSON dict or
    {"error": "...", ...} on failure.
    """
    from core.llm_advisor import parse_llm_response

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {"error": "no_api_key", "message": "ANTHROPIC_API_KEY is not set."}

    ok, err = insights_rate_limit_ok()
    if not ok:
        return {"error": "rate_limit", "message": err}

    import anthropic

    t0 = time.time()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=INSIGHTS_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        insights_record_successful_call()
        raw = response.content[0].text if response.content else ""
        elapsed = time.time() - t0
        parsed = parse_llm_response(raw)
        log_insight_event(
            kind,
            {
                "model": INSIGHTS_MODEL,
                "elapsed_s": round(elapsed, 2),
                "ok": bool(parsed),
                "preview": (raw[:400] + "…") if len(raw) > 400 else raw,
            },
        )
        if not parsed:
            return {
                "error": "parse_error",
                "message": "Could not parse JSON from model response.",
                "raw_preview": raw[:800],
            }
        return parsed
    except Exception as exc:
        log.warning("insights LLM error (%s): %s", kind, exc)
        log_insight_event(kind, {"error": str(exc), "ok": False})
        return {"error": "llm_error", "message": str(exc)}
