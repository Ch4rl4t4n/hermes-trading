"""
core/correlation_filter.py — adjust trade signal confidence based on the
"market leader" (BTC for crypto, SPY for stocks).

Idea: most altcoins follow BTC and most stocks follow SPY on short timeframes.
Even if a coin/stock looks great on its own technicals, fighting a sharp
broader-market move usually loses. We scale the agent's confidence by a
multiplier in [0.5, 1.5] based on what BTC / SPY are doing right now.

Rules of thumb (tunable below):
  - BTC down >3% / 24h + we want to BUY altcoin → confidence × 0.5–0.7
  - BTC up >3% / 24h + we want to BUY altcoin   → confidence × 1.1–1.3
  - BTC up >3% / 24h + we want to SELL altcoin  → confidence × 0.7
  - SPY equivalent for stocks (using S&P futures / SPY change_24h)

For BTC itself or SPY itself the multiplier is 1.0 (no self-correlation).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("correlation_filter")

# Thresholds (% in last 24h)
BTC_HARD_DOWN = -3.0
BTC_HARD_UP = 3.0
SPY_HARD_DOWN = -2.0
SPY_HARD_UP = 2.0

# Multiplier extremes
MIN_MULT = 0.5
MAX_MULT = 1.5

# Treat these symbols as "market leaders" — never apply self-correlation.
_LEADERS = {"BTC/USD", "SPY"}

# Tiny TTL cache so we don't hammer SPY price API.
_LEADER_TTL = 120  # seconds
_leader_cache: dict[str, tuple[Optional[float], float]] = {}


# ── Leader change fetchers ────────────────────────────────────────────────────

def _btc_change_24h(market_context: Optional[dict]) -> Optional[float]:
    """Pull BTC 24h change from the symbol-local market_context if it's BTC,
    otherwise return None — caller will fetch globally."""
    if not market_context:
        return None
    cmc = market_context.get("cmc_quote") or {}
    if isinstance(cmc, dict) and cmc.get("change_24h") is not None:
        try:
            return float(cmc["change_24h"])
        except (TypeError, ValueError):
            pass
    cg = market_context.get("coingecko") or {}
    if isinstance(cg, dict) and cg.get("change_24h") is not None:
        try:
            return float(cg["change_24h"])
        except (TypeError, ValueError):
            pass
    return None


async def _fetch_btc_change_24h() -> Optional[float]:
    """Fetch BTC 24h change from CMC/CoinGecko (cached ~2 minutes)."""
    cached = _leader_cache.get("BTC/USD")
    now = time.time()
    if cached and (now - cached[1]) < _LEADER_TTL:
        return cached[0]

    val: Optional[float] = None
    try:
        from core.external_data import get_cmc_quote, get_coingecko_data
        cmc = await get_cmc_quote("BTC/USD")
        if isinstance(cmc, dict) and cmc.get("change_24h") is not None:
            val = float(cmc["change_24h"])
        if val is None:
            cg = await get_coingecko_data("BTC/USD")
            if isinstance(cg, dict) and cg.get("change_24h") is not None:
                val = float(cg["change_24h"])
    except Exception as exc:
        log.debug("BTC change fetch failed: %s", exc)
        val = None

    _leader_cache["BTC/USD"] = (val, now)
    return val


async def _fetch_spy_change_24h() -> Optional[float]:
    """Fetch SPY 24h change via Yahoo (cached)."""
    cached = _leader_cache.get("SPY")
    now = time.time()
    if cached and (now - cached[1]) < _LEADER_TTL:
        return cached[0]

    val: Optional[float] = None
    try:
        # yfinance is sync and a bit slow — run in default executor.
        import asyncio
        import yfinance as yf

        def _read() -> Optional[float]:
            t = yf.Ticker("SPY")
            hist = t.history(period="2d", interval="1d")
            if hist is None or len(hist) < 2:
                info = (t.info or {})
                cur = info.get("regularMarketPrice")
                prev = info.get("regularMarketPreviousClose")
                if cur and prev:
                    return (cur - prev) / prev * 100.0
                return None
            closes = hist["Close"].tolist()
            if len(closes) < 2 or closes[-2] == 0:
                return None
            return (closes[-1] - closes[-2]) / closes[-2] * 100.0

        loop = asyncio.get_event_loop()
        val = await loop.run_in_executor(None, _read)
    except Exception as exc:
        log.debug("SPY change fetch failed: %s", exc)
        val = None

    _leader_cache["SPY"] = (val, now)
    return val


# ── Public API ────────────────────────────────────────────────────────────────

async def apply_correlation_filter(
    symbol: str,
    asset_type: str,
    signal_direction: str,
    market_context: Optional[dict] = None,
) -> tuple[float, str]:
    """
    Compute a confidence multiplier in [MIN_MULT, MAX_MULT] reflecting how
    aligned the trade is with the relevant market leader (BTC/SPY).

    Returns:
        (multiplier, reason_str)

    The caller is expected to multiply its existing confidence by this
    value.  Multiplier of 1.0 is the no-op default when we can't fetch
    leader data or symbol IS the leader.
    """
    direction = (signal_direction or "HOLD").upper()
    if direction == "HOLD":
        return 1.0, "hold (no filter)"
    if symbol in _LEADERS:
        return 1.0, f"{symbol} is market leader (no self-correlation)"
    if os.getenv("HERMES_DISABLE_CORRELATION", "").lower() in ("1", "true", "yes"):
        return 1.0, "correlation filter disabled via env"

    if asset_type == "crypto":
        change = _btc_change_24h(market_context)
        if change is None:
            change = await _fetch_btc_change_24h()
        leader = "BTC"
        hard_down = BTC_HARD_DOWN
        hard_up = BTC_HARD_UP
    else:
        change = await _fetch_spy_change_24h()
        leader = "SPY"
        hard_down = SPY_HARD_DOWN
        hard_up = SPY_HARD_UP

    if change is None:
        return 1.0, f"{leader} change unavailable"

    # Scoring: linear-ish ramp around hard thresholds, clamped.
    mult = 1.0
    reason: str
    if direction == "BUY":
        if change <= hard_down:
            # Worse the dump, smaller the size.
            severity = min(1.0, abs(change - hard_down) / abs(hard_down) + 0.0)
            mult = max(MIN_MULT, 1.0 - 0.5 * (1 + severity * 0.5))
            reason = f"{leader} {change:+.2f}% (hard down) → fade BUY ×{mult:.2f}"
        elif change >= hard_up:
            severity = min(1.0, (change - hard_up) / hard_up)
            mult = min(MAX_MULT, 1.0 + 0.3 * (1 + severity * 0.5))
            reason = f"{leader} {change:+.2f}% (hard up) → boost BUY ×{mult:.2f}"
        else:
            # Mild lean: scale modestly inside [-hard_down, +hard_up].
            mult = 1.0 + 0.1 * max(min(change / max(hard_up, 0.01), 1.0), -1.0)
            reason = f"{leader} {change:+.2f}% (neutral) → BUY ×{mult:.2f}"
    else:  # SELL
        if change >= hard_up:
            severity = min(1.0, (change - hard_up) / hard_up)
            mult = max(MIN_MULT, 1.0 - 0.5 * (1 + severity * 0.5))
            reason = f"{leader} {change:+.2f}% (hard up) → fade SELL ×{mult:.2f}"
        elif change <= hard_down:
            severity = min(1.0, abs(change - hard_down) / abs(hard_down))
            mult = min(MAX_MULT, 1.0 + 0.3 * (1 + severity * 0.5))
            reason = f"{leader} {change:+.2f}% (hard down) → boost SELL ×{mult:.2f}"
        else:
            mult = 1.0 - 0.1 * max(min(change / max(hard_up, 0.01), 1.0), -1.0)
            reason = f"{leader} {change:+.2f}% (neutral) → SELL ×{mult:.2f}"

    mult = max(MIN_MULT, min(MAX_MULT, mult))
    return round(mult, 3), reason


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)

    async def _t():
        for d in ("BUY", "SELL"):
            ctx = {"cmc_quote": {"change_24h": -4.5}}
            mult, why = await apply_correlation_filter("ETH/USD", "crypto", d, ctx)
            print(f"BTC -4.5%, ETH {d}: ×{mult}  ({why})")

            ctx2 = {"cmc_quote": {"change_24h": 5.2}}
            mult2, why2 = await apply_correlation_filter("ETH/USD", "crypto", d, ctx2)
            print(f"BTC +5.2%, ETH {d}: ×{mult2}  ({why2})")

        m, r = await apply_correlation_filter("BTC/USD", "crypto", "BUY", None)
        print(f"BTC self: ×{m}  ({r})")

    asyncio.run(_t())
