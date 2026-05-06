"""Backtesting: Binance OHLCV cache + lightweight strategy simulation."""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from core import database as db
from core.tier_access import (
    TIER_ADMIN,
    TIER_BASIC,
    TIER_ELITE,
    TIER_MEDIUM,
    TIER_PRO,
    normalize_tier,
)

log = logging.getLogger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

BACKTEST_LIMITS: dict[str, int] = {
    TIER_BASIC: 30,
    TIER_MEDIUM: 90,
    TIER_PRO: 365,
    TIER_ELITE: 1095,
    TIER_ADMIN: 1095,
}

BACKTEST_TIMEFRAMES: dict[str, list[str]] = {
    TIER_BASIC: ["1d"],
    TIER_MEDIUM: ["4h", "1d"],
    TIER_PRO: ["1h", "4h", "1d"],
    TIER_ELITE: ["1h", "4h", "1d"],
    TIER_ADMIN: ["1h", "4h", "1d"],
}

INITIAL_CAPITAL_USD = 10_000.0

_STRATEGY_ALIASES = {
    "swing": "trend_following",
    "scalp": "scalping",
    "sentiment": "momentum",
    "hedge": "mean_reversion",
    "seasonal": "mean_reversion",
}


class BinanceFetchError(Exception):
    """Public Binance API failed or returned an error."""


def backtest_max_days_for_tier(tier: str) -> int:
    t = normalize_tier(tier)
    return BACKTEST_LIMITS.get(t, BACKTEST_LIMITS[TIER_BASIC])


def backtest_allowed_timeframes(tier: str) -> list[str]:
    t = normalize_tier(tier)
    return list(BACKTEST_TIMEFRAMES.get(t, BACKTEST_TIMEFRAMES[TIER_BASIC]))


def backtest_limits_payload(tier: str) -> dict[str, Any]:
    t = normalize_tier(tier)
    return {
        "tier": t,
        "max_period_days": backtest_max_days_for_tier(t),
        "timeframes": backtest_allowed_timeframes(t),
        "period_presets": [30, 90, 180, 365, 1095],
    }


def normalize_strategy(raw: str | None) -> str:
    s = (raw or "momentum").strip().lower().replace("-", "_")
    if s in _STRATEGY_ALIASES:
        s = _STRATEGY_ALIASES[s]
    allowed = {
        "momentum",
        "mean_reversion",
        "breakout",
        "trend_following",
        "scalping",
        "grid",
        "dca",
    }
    return s if s in allowed else "momentum"


def hermes_symbol_to_binance(hermes_symbol: str) -> str:
    """BTC/USD, BTC, PEPE/USD → BTCUSDT-style pair for Binance spot."""
    s = (hermes_symbol or "").strip().upper()
    if "/" in s:
        base = s.split("/")[0].strip()
    else:
        base = s
        for suf in ("USDT", "USD"):
            if base.endswith(suf) and len(base) > len(suf):
                base = base[: -len(suf)]
                break
    base = base.replace("-", "")
    if not base:
        raise ValueError("empty symbol")
    return f"{base}USDT"


def _timeframe_ms(tf: str) -> int:
    if tf == "1h":
        return 3600_000
    if tf == "4h":
        return 4 * 3600_000
    if tf == "1d":
        return 86400_000
    raise ValueError(f"unsupported timeframe {tf}")


def _bars_needed(timeframe: str, days: int) -> int:
    if timeframe == "1h":
        return max(1, days * 24)
    if timeframe == "4h":
        return max(1, days * 6)
    if timeframe == "1d":
        return max(1, days)
    raise ValueError(f"unsupported timeframe {timeframe}")


def _http_get_klines(params: dict[str, Any]) -> list[list[Any]]:
    q = urllib.parse.urlencode(params)
    url = f"{BINANCE_KLINES}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "HermesBacktest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()
        except Exception:  # noqa: BLE001
            detail = str(e)
        raise BinanceFetchError(f"Binance HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise BinanceFetchError(f"Binance unreachable: {e}") from e
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise BinanceFetchError("Invalid JSON from Binance") from e
    if not isinstance(data, list):
        raise BinanceFetchError("Unexpected Binance response")
    return data


def _klines_to_rows(
    symbol_binance: str, timeframe: str, klines: list[list[Any]]
) -> list[tuple]:
    rows: list[tuple] = []
    for k in klines:
        if not k or len(k) < 6:
            continue
        ts = int(k[0])
        o, h, low, c, vol = k[1], k[2], k[3], k[4], k[5]
        rows.append(
            (symbol_binance, timeframe, ts, Decimal(str(o)), Decimal(str(h)), Decimal(str(low)), Decimal(str(c)), Decimal(str(vol)))
        )
    return rows


def _insert_candles(conn: Any, rows: list[tuple]) -> None:
    if not rows:
        return
    conn.execute(
        text("""
            INSERT INTO historical_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (:symbol, :tf, :ts, :o, :h, :low, :c, :vol)
            ON CONFLICT ON CONSTRAINT uq_historical_candles_sym_tf_ts DO NOTHING
        """),
        [
            {
                "symbol": r[0],
                "tf": r[1],
                "ts": r[2],
                "o": r[3],
                "h": r[4],
                "low": r[5],
                "c": r[6],
                "vol": r[7],
            }
            for r in rows
        ],
    )


def _load_range_from_db(
    conn: Any, symbol_binance: str, timeframe: str, start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    q = text("""
        SELECT timestamp, open, high, low, close, volume
        FROM historical_candles
        WHERE symbol = :s AND timeframe = :tf
          AND timestamp >= :t0 AND timestamp <= :t1
        ORDER BY timestamp ASC
    """)
    rows = conn.execute(q, {"s": symbol_binance, "tf": timeframe, "t0": start_ms, "t1": end_ms}).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "timestamp": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
        )
    return out


def _db_range_stats(
    conn: Any, symbol_binance: str, timeframe: str, start_ms: int, end_ms: int
) -> tuple[int, int | None]:
    row = conn.execute(
        text("""
            SELECT COUNT(*), MAX(timestamp) FROM historical_candles
            WHERE symbol = :s AND timeframe = :tf
              AND timestamp >= :t0 AND timestamp <= :t1
        """),
        {"s": symbol_binance, "tf": timeframe, "t0": start_ms, "t1": end_ms},
    ).fetchone()
    if not row:
        return 0, None
    cnt = int(row[0] or 0)
    mx = row[1]
    return cnt, int(mx) if mx is not None else None


def _is_stale(max_ts: int | None, timeframe: str, end_ms: int, need_bars: int, have_bars: int) -> bool:
    if max_ts is None or have_bars < max(20, need_bars * 8 // 10):
        return True
    now_ms = int(time.time() * 1000)
    tf_ms = _timeframe_ms(timeframe)
    grace = max(3600_000, tf_ms * 2)
    if now_ms - int(max_ts) > grace:
        return True
    if int(max_ts) < end_ms - tf_ms:
        return True
    return False


def _download_gap(
    symbol_binance: str, interval: str, start_ms: int, end_ms: int
) -> list[tuple]:
    """Fetch [start_ms, end_ms] in chunks of 1000 klines (forward in time)."""
    all_rows: list[tuple] = []
    cur = int(start_ms)
    end_ms = int(end_ms)
    while cur < end_ms:
        batch = _http_get_klines(
            {
                "symbol": symbol_binance,
                "interval": interval,
                "startTime": cur,
                "endTime": end_ms,
                "limit": 1000,
            }
        )
        if not batch:
            break
        rows = _klines_to_rows(symbol_binance, interval, batch)
        all_rows.extend(rows)
        last_close = int(batch[-1][6])
        nxt = last_close + 1
        if nxt <= cur:
            break
        cur = nxt
        if len(batch) < 1000:
            break
    return all_rows


def fetch_candles(hermes_symbol: str, timeframe: str, days: int) -> list[dict[str, Any]]:
    """
    Cache-first OHLCV from historical_candles; refill from Binance public klines API.
    Returns [{timestamp, open, high, low, close, volume}] oldest→newest (ms timestamps).
    """
    if timeframe not in ("1h", "4h", "1d"):
        raise ValueError("timeframe must be 1h, 4h, or 1d")
    try:
        bsym = hermes_symbol_to_binance(hermes_symbol)
    except ValueError as e:
        raise ValueError(str(e)) from e

    need_bars = _bars_needed(timeframe, days)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(days * 86400 * 1000 * 1.05)

    eng = db.get_engine()
    if eng is None:
        rows = _download_gap(bsym, timeframe, start_ms, end_ms)
        by_ts: dict[int, tuple] = {}
        for t in rows:
            by_ts[int(t[2])] = t
        candles = [
            {
                "timestamp": int(t[2]),
                "open": float(t[3]),
                "high": float(t[4]),
                "low": float(t[5]),
                "close": float(t[6]),
                "volume": float(t[7]),
            }
            for t in sorted(by_ts.values(), key=lambda x: x[2])
        ]
        return [c for c in candles if start_ms <= c["timestamp"] <= end_ms][-need_bars:]

    with eng.begin() as conn:
        cnt, mx = _db_range_stats(conn, bsym, timeframe, start_ms, end_ms)
        if _is_stale(mx, timeframe, end_ms, need_bars, cnt):
            try:
                dl = _download_gap(bsym, timeframe, start_ms, end_ms)
                _insert_candles(conn, dl)
            except BinanceFetchError:
                if cnt == 0:
                    raise
                log.warning("Binance partial failure; using DB cache only", exc_info=True)
        return _load_range_from_db(conn, bsym, timeframe, start_ms, end_ms)[-need_bars:]


def refresh_historical_candles_daily() -> None:
    """Watcher: warm 7d of 1h for each major base symbol."""
    from core.agent_builder import ALLOWED_SYMBOLS

    eng = db.get_engine()
    if eng is None:
        return
    for base in ALLOWED_SYMBOLS:
        sym_pair = f"{base}/USD"
        try:
            fetch_candles(sym_pair, "1h", 7)
        except Exception as exc:  # noqa: BLE001
            log.warning("Daily candle refresh failed for %s: %s", base, exc)


def refresh_historical_candles() -> None:
    """Alias for watcher cycle (spec name)."""
    refresh_historical_candles_daily()


def _sma(closes: list[float], i: int, period: int) -> float | None:
    if i + 1 < period:
        return None
    sl = closes[i - period + 1 : i + 1]
    return sum(sl) / period


def _max_high(highs: list[float], i: int, period: int) -> float | None:
    if i < period:
        return None
    window = highs[i - period : i]
    return max(window)


def run_backtest(config: dict[str, Any], candles: list[dict[str, Any]], timeframe: str = "1d") -> dict[str, Any]:
    """
    Simulate long-only spot-style strategy on closes.
    config: strategy_type, stop_loss_pct, position_size_pct, max_daily_trades
    """
    strategy = normalize_strategy(config.get("strategy_type"))
    stop_loss_pct = float(config.get("stop_loss_pct") or 5.0)
    position_size_pct = float(config.get("position_size_pct") or 10.0)
    max_daily_trades = int(config.get("max_daily_trades") or 10)

    if timeframe not in ("1h", "4h", "1d"):
        timeframe = "1d"

    if not candles or len(candles) < 25:
        return _empty_result("Insufficient candle data")

    ts_list = [int(c["timestamp"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]

    cash = INITIAL_CAPITAL_USD
    qty = 0.0
    entry = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    daily_trade_count: dict[str, int] = {}

    def _day_key(ms: int) -> str:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")

    def _equity(i: int) -> float:
        return cash + qty * closes[i]

    equity_curve.append({"timestamp": ts_list[0], "equity": INITIAL_CAPITAL_USD, "pnl": 0.0})

    def _can_trade(ms: int) -> bool:
        dk = _day_key(ms)
        return daily_trade_count.get(dk, 0) < max_daily_trades

    def _bump_trade_day(ms: int) -> None:
        dk = _day_key(ms)
        daily_trade_count[dk] = daily_trade_count.get(dk, 0) + 1

    def _buy(i: int, sl_mult: float = 1.0) -> None:
        nonlocal cash, qty, entry
        if qty > 0 or not _can_trade(ts_list[i]):
            return
        eq = _equity(i)
        usd = eq * (position_size_pct / 100.0)
        if usd <= 0 or cash < usd * 0.999:
            usd = cash * 0.995
        if usd <= 1.0:
            return
        price = closes[i]
        q = usd / price
        cash -= usd
        qty = q
        entry = price
        _bump_trade_day(ts_list[i])
        trades.append(
            {
                "timestamp": ts_list[i],
                "action": "BUY",
                "price": price,
                "quantity": q,
                "pnl": 0.0,
                "stop_loss_pct": stop_loss_pct * sl_mult,
            }
        )

    def _sell(i: int, reason: str = "signal") -> None:
        nonlocal cash, qty, entry
        if qty <= 0:
            return
        price = closes[i]
        gross = qty * price
        pnl = gross - qty * entry
        cash += gross
        trades.append(
            {
                "timestamp": ts_list[i],
                "action": "SELL",
                "price": price,
                "quantity": qty,
                "pnl": pnl,
                "reason": reason,
            }
        )
        eq = cash
        equity_curve.append({"timestamp": ts_list[i], "equity": eq, "pnl": pnl})
        qty = 0.0
        entry = 0.0
        _bump_trade_day(ts_list[i])

    scalp_sl = stop_loss_pct * 0.5
    lo_win = min(lows[: min(60, len(lows))])
    hi_win = max(highs[: min(60, len(highs))])
    if hi_win <= lo_win:
        hi_win = lo_win * 1.01
    grid_levels = [lo_win + (hi_win - lo_win) * j / 4.0 for j in range(5)]
    dca_n = max(5, len(candles) // 15)
    dca_cost_sum = 0.0
    dca_qty_sum = 0.0

    for i in range(len(candles)):
        c = closes[i]
        if qty > 0:
            thr = stop_loss_pct if strategy != "scalping" else scalp_sl
            if c <= entry * (1.0 - thr / 100.0):
                _sell(i, "stop_loss")

        sma20 = _sma(closes, i, 20)
        sma10 = _sma(closes, i, 10)
        prev_close = closes[i - 1] if i > 0 else c

        if strategy == "momentum" and sma20 is not None:
            if qty > 0 and c < sma20:
                _sell(i, "signal")
            elif qty == 0 and c > sma20 and c > prev_close * 1.002:
                _buy(i)
        elif strategy == "mean_reversion" and sma20 is not None:
            if qty > 0 and c > sma20 * 1.02:
                _sell(i, "signal")
            elif qty == 0 and c < sma20 * 0.98:
                _buy(i)
        elif strategy == "breakout":
            mh = _max_high(highs, i, 20)
            if mh is not None:
                if qty > 0 and c < mh * 0.97:
                    _sell(i, "signal")
                elif qty == 0 and c > mh:
                    _buy(i)
        elif strategy == "trend_following" and sma10 is not None and sma20 is not None:
            if qty > 0 and sma10 < sma20:
                _sell(i, "signal")
            elif qty == 0 and sma10 > sma20:
                _buy(i)
        elif strategy == "scalping":
            if i > 0 and i % 5 == 0:
                if qty > 0:
                    _sell(i, "scalp_rotate")
                if qty == 0:
                    _buy(i, sl_mult=0.5)
        elif strategy == "grid":
            for b in range(4):
                lo, hi = grid_levels[b], grid_levels[b + 1]
                if qty == 0 and c <= lo * 1.002:
                    _buy(i)
                    break
                if qty > 0 and c >= hi * 0.998:
                    _sell(i, "grid")
                    break
        elif strategy == "dca":
            if i % dca_n == 0 and _can_trade(ts_list[i]):
                price = c
                eq = _equity(i)
                usd = min(eq * (position_size_pct / 100.0), cash * 0.995)
                if usd > 1.0 and cash >= usd * 0.5:
                    q = usd / price
                    cash -= usd
                    dca_cost_sum += usd
                    dca_qty_sum += q
                    qty = dca_qty_sum
                    entry = dca_cost_sum / dca_qty_sum
                    _bump_trade_day(ts_list[i])
                    trades.append(
                        {"timestamp": ts_list[i], "action": "BUY", "price": price, "quantity": q, "pnl": 0.0}
                    )
            if qty > 0 and dca_qty_sum > 0:
                avg = dca_cost_sum / dca_qty_sum
                if c >= avg * 1.05:
                    gross = qty * c
                    pnl = gross - dca_cost_sum
                    cash += gross
                    trades.append(
                        {
                            "timestamp": ts_list[i],
                            "action": "SELL",
                            "price": c,
                            "quantity": qty,
                            "pnl": pnl,
                            "reason": "dca_take",
                        }
                    )
                    equity_curve.append({"timestamp": ts_list[i], "equity": cash, "pnl": pnl})
                    qty = 0.0
                    entry = 0.0
                    dca_cost_sum = 0.0
                    dca_qty_sum = 0.0
                    _bump_trade_day(ts_list[i])

    # Close position at end
    if qty > 0:
        price = closes[-1]
        gross = qty * price
        if strategy == "dca" and dca_qty_sum > 0:
            pnl = gross - dca_cost_sum
        else:
            pnl = gross - qty * entry
        cash += gross
        trades.append(
            {
                "timestamp": ts_list[-1],
                "action": "SELL",
                "price": price,
                "quantity": qty,
                "pnl": pnl,
                "reason": "eof",
            }
        )
        equity_curve.append({"timestamp": ts_list[-1], "equity": cash, "pnl": pnl})
        qty = 0.0

    if len(equity_curve) == 1 and trades:
        # Only initial point; add final equity
        equity_curve.append({"timestamp": ts_list[-1], "equity": cash, "pnl": 0.0})

    sell_pnls = [float(t["pnl"]) for t in trades if t["action"] == "SELL" and "pnl" in t]
    total_pnl_usd = cash - INITIAL_CAPITAL_USD
    total_pnl_pct = (total_pnl_usd / INITIAL_CAPITAL_USD) * 100.0 if INITIAL_CAPITAL_USD else 0.0

    wins = [p for p in sell_pnls if p > 0]
    losses = [p for p in sell_pnls if p < 0]
    winning_trades = len(wins)
    losing_trades = len(losses)
    n_sells = len(sell_pnls)
    win_rate = (winning_trades / n_sells * 100.0) if n_sells else 0.0

    sum_w = sum(wins) if wins else 0.0
    sum_l = sum(losses) if losses else 0.0
    if sum_l == 0:
        profit_factor = float("inf") if sum_w > 0 else 0.0
    else:
        profit_factor = sum_w / abs(sum_l)

    eq_vals = [p["equity"] for p in equity_curve]
    peak = eq_vals[0]
    max_dd = 0.0
    for v in eq_vals:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (1.0 - v / peak) * 100.0)

    rets: list[float] = []
    for j in range(1, len(eq_vals)):
        a, b = eq_vals[j - 1], eq_vals[j]
        if a > 0:
            rets.append((b - a) / a)
    if len(rets) > 1 and statistics.stdev(rets) > 1e-12:
        ann = math.sqrt(252.0)
        if timeframe == "1h":
            ann = math.sqrt(252.0 * 24.0)
        elif timeframe == "4h":
            ann = math.sqrt(252.0 * 6.0)
        sharpe = (statistics.mean(rets) / statistics.stdev(rets)) * ann
    else:
        sharpe = 0.0

    avg_trade = statistics.mean(sell_pnls) if sell_pnls else 0.0
    best = max(sell_pnls) if sell_pnls else 0.0
    worst = min(sell_pnls) if sell_pnls else 0.0

    streak_w = streak_l = 0
    cur_w = cur_l = 0
    for p in sell_pnls:
        if p > 0:
            cur_w += 1
            cur_l = 0
            streak_w = max(streak_w, cur_w)
        elif p < 0:
            cur_l += 1
            cur_w = 0
            streak_l = max(streak_l, cur_l)

    if math.isinf(profit_factor):
        profit_factor_out = 999.99
    else:
        profit_factor_out = round(profit_factor, 4)

    return {
        "total_pnl_usd": round(total_pnl_usd, 2),
        "total_pnl_pct": round(total_pnl_pct, 4),
        "win_rate": round(win_rate, 2),
        "total_trades": n_sells,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "max_drawdown_pct": round(max_dd, 4),
        "profit_factor": profit_factor_out,
        "sharpe_ratio": round(float(sharpe), 4),
        "avg_trade_pnl": round(avg_trade, 4),
        "best_trade_pnl": round(best, 4),
        "worst_trade_pnl": round(worst, 4),
        "longest_win_streak": streak_w,
        "longest_lose_streak": streak_l,
        "equity_curve": equity_curve,
        "trades": trades[:100],
    }


def _empty_result(note: str) -> dict[str, Any]:
    z = {
        "total_pnl_usd": 0.0,
        "total_pnl_pct": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "max_drawdown_pct": 0.0,
        "profit_factor": 0.0,
        "sharpe_ratio": 0.0,
        "avg_trade_pnl": 0.0,
        "best_trade_pnl": 0.0,
        "worst_trade_pnl": 0.0,
        "longest_win_streak": 0,
        "longest_lose_streak": 0,
        "equity_curve": [{"timestamp": 0, "equity": INITIAL_CAPITAL_USD, "pnl": 0.0}],
        "trades": [],
        "error": note,
    }
    return z


def agent_config_from_row_user(
    strategy_type: str, config_json: dict[str, Any] | None
) -> dict[str, Any]:
    cj = config_json if isinstance(config_json, dict) else {}
    return {
        "strategy_type": normalize_strategy(strategy_type),
        "stop_loss_pct": float(cj.get("stop_loss_pct") or 5.0),
        "position_size_pct": float(cj.get("position_size_pct") or 10.0),
        "max_daily_trades": int(cj.get("max_daily_trades") or 10),
    }


def agent_config_from_row_system(strategy: str | None) -> dict[str, Any]:
    return {
        "strategy_type": normalize_strategy(strategy),
        "stop_loss_pct": 5.0,
        "position_size_pct": 10.0,
        "max_daily_trades": 10,
    }
