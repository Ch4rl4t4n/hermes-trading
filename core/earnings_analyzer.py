"""
Earnings / events analysis for selected equities (TSLA, NVDA, AMD).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("earnings_analyzer")

ALLOWED = frozenset({"TSLA", "NVDA", "AMD"})
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_TTL = 3600.0


async def analyze_earnings(symbol: str) -> dict[str, Any]:
    sym = symbol.strip().upper()
    if sym not in ALLOWED:
        return {
            "error": "unsupported",
            "message": "Earnings analysis is only available for TSLA, NVDA, and AMD.",
        }

    now = time.time()
    hit = _cache.get(sym)
    if hit and hit[0] > now:
        return {"cached": True, **hit[1]}

    from core.external_data import get_alpaca_news, get_yahoo_data
    from core.llm_insights_util import call_insights_llm_json

    news_task = get_alpaca_news(sym, limit=10)
    yahoo_task = get_yahoo_data(sym)
    articles, yahoo = await asyncio.gather(news_task, yahoo_task)

    # Extra yfinance fundamentals
    extra: dict[str, Any] = {}
    try:
        import yfinance as yf

        t = yf.Ticker(sym)
        info = t.info or {}
        extra = {
            "trailingEps": info.get("trailingEps"),
            "forwardEps": info.get("forwardEps"),
            "earningsQuarterlyGrowth": info.get("earningsQuarterlyGrowth"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsDate": info.get("earningsDate"),
            "longName": info.get("longName"),
        }
    except Exception as exc:
        extra = {"error": str(exc)}

    system = (
        "You are an equity analyst. Reply ONLY with valid JSON, no markdown. "
        "All human-readable strings in JSON must be English."
    )
    user = f"""Analyze recent earnings / expectations for {sym}.

Yahoo / yfinance (JSON): {json.dumps(yahoo, ensure_ascii=False, default=str)}
Additional fields (JSON): {json.dumps(extra, ensure_ascii=False, default=str)}
News (JSON): {json.dumps(articles, ensure_ascii=False, default=str)}

Reply in JSON:
{{
  "earnings_summary": "2-4 sentences in English",
  "beat_or_miss": "beat/miss/unknown/neutral",
  "impact_on_price": "bullish/bearish/neutral",
  "recommendation": "hold / cautious / avoid — short note in English",
  "confidence": 0.0
}}"""

    parsed = await asyncio.to_thread(
        call_insights_llm_json,
        system,
        user,
        max_tokens=2048,
        kind="earnings_analyze",
    )
    if parsed.get("error"):
        return {
            "symbol": sym,
            "error": parsed.get("error"),
            "message": parsed.get("message", "Zlyhanie LLM"),
        }

    payload = {
        "symbol": sym,
        "earnings_summary": parsed.get("earnings_summary", ""),
        "beat_or_miss": parsed.get("beat_or_miss", "unknown"),
        "impact_on_price": parsed.get("impact_on_price", "neutral"),
        "recommendation": parsed.get("recommendation", ""),
        "confidence": float(parsed.get("confidence") or 0.0),
        "yahoo_snapshot": yahoo,
    }
    _cache[sym] = (now + _TTL, payload)
    return payload
