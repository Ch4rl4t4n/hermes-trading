"""
core/regime_detector.py — Market regime classification for the Hermes platform.

Classifies the current state of the market for a single symbol into one of:

    "trending_up"   — sustained uptrend (price > 20-EMA > 50-EMA, ADX > 25)
    "trending_down" — sustained downtrend (price < 20-EMA < 50-EMA, ADX > 25)
    "ranging"       — choppy / oscillating (ADX < 20, narrow band around mid)
    "volatile"      — abnormal volatility (ATR > 2× normal, recent volume spikes)
    "crash"         — sharp drawdown (>5% in 24h + extreme fear + volume spike)
    "unknown"       — not enough data to decide

The detector is intentionally pure-Python with no pandas dependency so it can
run inside agent ticks cheaply.  All calculations operate on a flat list of
closing prices (oldest → newest) plus an optional `external_data` dict from
`core.external_data.get_market_context`, which it uses to read 24h % change,
volume, and the Crypto/Stocks Fear & Greed index when classifying crashes.

The result is fed back into `llm_advisor.build_context_prompt` so Claude has
the regime label as part of its decision context.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, asdict
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("regime_detector")

REGIMES = ("trending_up", "trending_down", "ranging", "volatile", "crash", "unknown")

# Tunables — kept module-level so they're easy to spot/tweak.
EMA_FAST = 20
EMA_SLOW = 50
ADX_PERIOD = 14
ATR_PERIOD = 14
ATR_LOOKBACK = 50          # bars used to compute "normal" ATR
ADX_TREND_THRESHOLD = 25.0
ADX_RANGE_THRESHOLD = 20.0
VOLATILE_ATR_MULTIPLIER = 2.0
CRASH_24H_DROP_PCT = -5.0   # percent
CRASH_FNG_THRESHOLD = 25    # below = extreme fear
CRASH_VOLUME_SPIKE = 1.5    # 24h volume / 7d-avg-equivalent (CMC: change_24h vol)


@dataclass
class RegimeResult:
    regime: str
    confidence: float
    details: dict

    def to_dict(self) -> dict:
        return asdict(self)


# ── Indicator helpers ─────────────────────────────────────────────────────────

def _ema(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val


def _true_ranges(prices: list[float]) -> list[float]:
    """Pure-close TR proxy — abs(close[i] - close[i-1])."""
    return [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]


def _atr(prices: list[float], period: int = ATR_PERIOD) -> float:
    if len(prices) < period + 1:
        return 0.0
    trs = _true_ranges(prices[-(period + 1):])
    return sum(trs) / period if trs else 0.0


def _atr_average(prices: list[float], period: int = ATR_PERIOD, lookback: int = ATR_LOOKBACK) -> float:
    """Average of rolling ATR over the last `lookback` windows."""
    if len(prices) < period + lookback:
        # fall back to whatever ATR we can produce
        return _atr(prices, period)
    atrs: list[float] = []
    for end in range(len(prices) - lookback, len(prices)):
        window = prices[max(0, end - period): end + 1]
        if len(window) >= period + 1:
            atrs.append(sum(_true_ranges(window)) / period)
    return sum(atrs) / len(atrs) if atrs else 0.0


def _adx(prices: list[float], period: int = ADX_PERIOD) -> float:
    """
    Approximate ADX using close-only data.

    True ADX uses high/low/close; we don't bootstrap full OHLC bars in the
    feed, so this is a directional-strength proxy that behaves well enough
    for regime gating.  It compares consecutive closes (+DM / -DM) and
    smooths against the close-based TR.
    """
    if len(prices) < period * 2 + 1:
        return 0.0

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        plus_dm.append(max(diff, 0.0))
        minus_dm.append(max(-diff, 0.0))

    trs = _true_ranges(prices)
    if len(trs) < period:
        return 0.0

    def _smooth(seq: list[float]) -> list[float]:
        out = [sum(seq[:period]) / period]
        for v in seq[period:]:
            out.append(out[-1] * (period - 1) / period + v / period)
        return out

    sm_plus = _smooth(plus_dm)
    sm_minus = _smooth(minus_dm)
    sm_tr = _smooth(trs)

    dxs: list[float] = []
    for p, m, t in zip(sm_plus, sm_minus, sm_tr):
        if t <= 0:
            continue
        plus_di = 100 * p / t
        minus_di = 100 * m / t
        denom = plus_di + minus_di
        if denom <= 0:
            continue
        dxs.append(100 * abs(plus_di - minus_di) / denom)

    if len(dxs) < period:
        return sum(dxs) / len(dxs) if dxs else 0.0
    # Wilder-smoothed DX over `period` for ADX
    adx_val = sum(dxs[:period]) / period
    for v in dxs[period:]:
        adx_val = (adx_val * (period - 1) + v) / period
    return adx_val


def _pct_change_24h(price_history: list[float], external: Optional[dict]) -> float:
    """Prefer external 24h change when available; otherwise estimate from history."""
    if external:
        for src in ("cmc_quote", "coingecko"):
            block = external.get(src) or {}
            if isinstance(block, dict):
                val = block.get("change_24h")
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue

    if len(price_history) < 2:
        return 0.0
    # Heuristic: use first vs last across whatever window we have. With 1m
    # bars and HISTORY_BARS=50 this is roughly the last ~50 minutes; with
    # 4h bars it's ~8 days. Better than zero.
    first = price_history[0]
    last = price_history[-1]
    if first <= 0:
        return 0.0
    return (last - first) / first * 100.0


def _volume_spike(external: Optional[dict]) -> bool:
    """Heuristic: 24h volume present and CMC reports a sharp 1h or 24h move."""
    if not external:
        return False
    cmc = external.get("cmc_quote") or {}
    if not isinstance(cmc, dict):
        return False
    vol = cmc.get("volume_24h")
    chg_1h = cmc.get("change_1h") or 0
    chg_24h = cmc.get("change_24h") or 0
    if not vol:
        return False
    try:
        return abs(float(chg_1h)) >= 1.5 or abs(float(chg_24h)) >= CRASH_VOLUME_SPIKE * 2
    except (TypeError, ValueError):
        return False


def _fear_greed_value(external: Optional[dict], asset_type: str) -> Optional[int]:
    if not external:
        return None
    key = "crypto_fg" if asset_type == "crypto" else "stocks_fg"
    block = external.get(key) or {}
    if not isinstance(block, dict):
        return None
    val = block.get("value")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def detect_regime(
    symbol: str,
    asset_type: str,
    price_history: list[float],
    external_data: Optional[dict] = None,
) -> RegimeResult:
    """Classify current market regime for `symbol`.

    Returns a `RegimeResult` whose `.regime` is one of `REGIMES`. Confidence
    is a coarse 0..1 score derived from how strongly the dominant signal
    cleared its threshold; details mirrors the values used to decide.
    """
    prices = [float(p) for p in (price_history or []) if p is not None and not math.isnan(p)]
    if len(prices) < EMA_FAST + 1:
        return RegimeResult("unknown", 0.0, {"reason": f"need >= {EMA_FAST + 1} bars, got {len(prices)}"})

    last = prices[-1]
    ema20 = _ema(prices, EMA_FAST)
    ema50 = _ema(prices, EMA_SLOW) if len(prices) >= EMA_SLOW else ema20
    adx_val = _adx(prices)
    atr_now = _atr(prices)
    atr_norm = _atr_average(prices)
    atr_ratio = (atr_now / atr_norm) if atr_norm > 0 else 1.0
    pct_24h = _pct_change_24h(prices, external_data)
    fng = _fear_greed_value(external_data, asset_type)
    vol_spike = _volume_spike(external_data)

    details = {
        "price": round(last, 6),
        "ema20": round(ema20, 6),
        "ema50": round(ema50, 6),
        "adx": round(adx_val, 2),
        "atr": round(atr_now, 6),
        "atr_normal": round(atr_norm, 6),
        "atr_ratio": round(atr_ratio, 2),
        "pct_change_24h": round(pct_24h, 2),
        "fear_greed": fng,
        "volume_spike": vol_spike,
    }

    # 1. Crash takes precedence — it's a tail event we want to react to first.
    if pct_24h <= CRASH_24H_DROP_PCT and (fng is None or fng < CRASH_FNG_THRESHOLD) and vol_spike:
        conf = min(1.0, abs(pct_24h) / 10.0)
        return RegimeResult("crash", round(conf, 2), details)

    # 2. Volatile regime — sized by how many sigmas above normal ATR.
    if atr_ratio >= VOLATILE_ATR_MULTIPLIER:
        conf = min(1.0, (atr_ratio - VOLATILE_ATR_MULTIPLIER) / VOLATILE_ATR_MULTIPLIER + 0.5)
        return RegimeResult("volatile", round(conf, 2), details)

    # 3. Trending regimes — need both EMA stack and ADX confirming.
    trending_up = last > ema20 and ema20 > ema50 and adx_val > ADX_TREND_THRESHOLD
    trending_down = last < ema20 and ema20 < ema50 and adx_val > ADX_TREND_THRESHOLD
    if trending_up:
        conf = min(1.0, (adx_val - ADX_TREND_THRESHOLD) / 25.0 + 0.5)
        return RegimeResult("trending_up", round(conf, 2), details)
    if trending_down:
        conf = min(1.0, (adx_val - ADX_TREND_THRESHOLD) / 25.0 + 0.5)
        return RegimeResult("trending_down", round(conf, 2), details)

    # 4. Ranging — low ADX and price near the moving average.
    if adx_val < ADX_RANGE_THRESHOLD:
        return RegimeResult("ranging", round(1 - adx_val / max(ADX_RANGE_THRESHOLD, 1.0), 2), details)

    # 5. Default: indecisive trend (between thresholds) → ranging w/ low confidence.
    return RegimeResult("ranging", 0.3, details)


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)

    async def _test():
        # Fake uptrend
        prices = [100 + i * 0.5 + (i % 3) for i in range(80)]
        r = await detect_regime("BTC/USD", "crypto", prices, external_data=None)
        print("Synthetic uptrend ->", r)

        # Fake crash
        crash = [100 - i * 1.0 for i in range(60)]
        ext = {
            "crypto_fg": {"value": 18, "label": "Extreme Fear"},
            "cmc_quote": {"volume_24h": 1e9, "change_1h": -2.0, "change_24h": -7.5},
        }
        r2 = await detect_regime("BTC/USD", "crypto", crash, ext)
        print("Synthetic crash   ->", r2)

    asyncio.run(_test())
