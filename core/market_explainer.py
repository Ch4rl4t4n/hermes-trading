"""
AI market explainer: why did price move in the last 24h?
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("market_explainer")

# symbol -> (expires_ts, payload)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 3600.0
_MOVE_THRESHOLD_PCT = 2.0


def _fetch_24h_bars_sync(symbol: str, asset_type: str) -> list[dict[str, Any]]:
    """Return list of {t, open, high, low, close, volume} for ~24h."""
    from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=30)
    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_API_SECRET", "")
    if asset_type == "crypto":
        client = CryptoHistoricalDataClient()
        req = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Hour),
            start=start,
            end=end,
        )
        bars = client.get_crypto_bars(req)[symbol]
    else:
        client = StockHistoricalDataClient(api_key=key, secret_key=secret)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Hour),
            start=start,
            end=end,
        )
        bars = client.get_stock_bars(req)[symbol]
    out = []
    for b in bars:
        out.append(
            {
                "t": b.timestamp.isoformat() if hasattr(b.timestamp, "isoformat") else str(b.timestamp),
                "o": float(b.open),
                "h": float(b.high),
                "l": float(b.low),
                "c": float(b.close),
                "v": float(getattr(b, "volume", 0) or 0),
            }
        )
    return out


async def explain_price_move(symbol: str, asset_type: str) -> dict[str, Any]:
    """
    Analyze why symbol moved significantly in 24h. Returns English JSON-shaped dict
    from the LLM when move > threshold; otherwise a skip message.
    """
    sym = symbol.strip()
    now = time.time()
    hit = _cache.get(sym)
    if hit and hit[0] > now:
        return {"cached": True, **hit[1]}

    bars = await asyncio.to_thread(_fetch_24h_bars_sync, sym, asset_type)
    if len(bars) < 2:
        return {
            "error": "no_data",
            "message": "Insufficient historical data from Alpaca.",
            "symbol": sym,
        }

    first_c = bars[0]["c"]
    last_c = bars[-1]["c"]
    if first_c <= 0:
        pct = 0.0
    else:
        pct = (last_c - first_c) / first_c * 100.0

    price_history = json.dumps(bars[-24:], default=str)

    if abs(pct) < _MOVE_THRESHOLD_PCT:
        payload = {
            "skipped": True,
            "message": (
                f"24h change is {pct:.2f}% (below {_MOVE_THRESHOLD_PCT}% threshold). "
                "AI analysis is not triggered."
            ),
            "change_24h_pct": round(pct, 4),
            "last_price": last_c,
            "symbol": sym,
        }
        _cache[sym] = (now + 300.0, payload)
        return payload

    from core.external_data import get_alpaca_news, get_market_context
    from core.llm_insights_util import call_insights_llm_json

    news_task = get_alpaca_news(sym, limit=10)
    ctx_task = get_market_context(sym, asset_type)
    news_articles, ext = await asyncio.gather(news_task, ctx_task)

    system = (
        "You are a financial analyst. Reply ONLY with valid JSON, no markdown. "
        "All human-readable strings inside JSON must be in English."
    )
    user = f"""Explain why {sym} moved approximately {pct:.2f}% over roughly the last 24 hours.

Price data (hourly candles, JSON): {price_history}
News (JSON): {json.dumps(news_articles, ensure_ascii=False, default=str)}
Market context (JSON): {json.dumps(ext, ensure_ascii=False, default=str)}

Reply ONLY in this JSON shape:
{{
  "summary": "2-3 sentence explanation in English",
  "factors": ["factor1", "factor2", "factor3"],
  "sentiment": "bullish/bearish/neutral",
  "outlook_24h": "up/down/sideways",
  "confidence": 0.0
}}
confidence is between 0 and 1."""

    parsed = await asyncio.to_thread(
        call_insights_llm_json,
        system,
        user,
        max_tokens=2048,
        kind="explain_price_move",
    )
    if parsed.get("error"):
        return {
            "error": parsed.get("error"),
            "message": parsed.get("message", "LLM call failed"),
            "symbol": sym,
            "change_24h_pct": round(pct, 4),
        }

    payload = {
        "skipped": False,
        "symbol": sym,
        "change_24h_pct": round(pct, 4),
        "last_price": last_c,
        "summary": parsed.get("summary", ""),
        "factors": parsed.get("factors") or [],
        "sentiment": parsed.get("sentiment", "neutral"),
        "outlook_24h": parsed.get("outlook_24h", "sideways"),
        "confidence": float(parsed.get("confidence") or 0.0),
    }
    _cache[sym] = (now + _CACHE_TTL, payload)
    return payload
