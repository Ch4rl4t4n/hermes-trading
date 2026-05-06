"""
Portfolio-level analytics: Alpaca snapshot, equity curve, risk metrics, correlation.
60s in-process cache with stale fallback when the broker API errors.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetPortfolioHistoryRequest

from core.performance_tracker import TradeRecord

log = logging.getLogger("portfolio_analytics")

TRACKED_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "TSLA", "NVDA", "AMD", "GLD", "USO"]

_SECTOR_DEFS = (
    ("Crypto", {"BTC/USD", "ETH/USD", "SOL/USD"}),
    ("Tech", {"TSLA", "NVDA", "AMD"}),
    ("Commodities", {"GLD", "USO"}),
)

try:
    import numpy as np  # type: ignore

    _HAS_NP = True
except ImportError:
    _HAS_NP = False


def alpaca_position_symbol(symbol: str) -> str:
    return symbol.replace("/", "")


def position_to_agent_symbol(pos_sym: str) -> str:
    """Map Alpaca position symbol back to agent canonical form when possible."""
    if "/" in pos_sym:
        return pos_sym
    upper = pos_sym.upper()
    crypto_map = {"BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD", "SOLUSD": "SOL/USD"}
    return crypto_map.get(upper, pos_sym)


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


class PortfolioAnalytics:
    CACHE_TTL = 60.0

    def __init__(
        self,
        trading_client: Optional[TradingClient],
        *,
        stock_client: Optional[StockHistoricalDataClient] = None,
        crypto_client: Optional[CryptoHistoricalDataClient] = None,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
    ):
        self._trading = trading_client
        self._stock = stock_client or (
            StockHistoricalDataClient(api_key=api_key, secret_key=api_secret) if api_key else None
        )
        self._crypto = crypto_client or CryptoHistoricalDataClient()
        self._paper = paper
        self._snap_cache: dict[str, Any] = {"ts": 0.0, "data": None, "stale": False, "err": None}

    async def get_snapshot(self) -> dict:
        return await asyncio.to_thread(self.get_snapshot_sync)

    def get_snapshot_sync(self) -> dict:
        now = time.time()
        if self._snap_cache["data"] is not None and (now - self._snap_cache["ts"]) < self.CACHE_TTL:
            out = dict(self._snap_cache["data"])
            out["cached"] = True
            out["stale"] = bool(self._snap_cache["stale"])
            return out

        stale_flag = self._snap_cache["stale"] and self._snap_cache["data"] is not None
        err_msg = None
        try:
            fresh = self._build_snapshot_body()
            self._snap_cache = {
                "ts": now,
                "data": fresh,
                "stale": False,
                "err": None,
            }
            out = dict(fresh)
            out["cached"] = False
            out["stale"] = False
            return out
        except Exception as exc:  # noqa: BLE001
            log.warning("portfolio snapshot failed: %s", exc)
            err_msg = str(exc)
            if self._snap_cache["data"] is not None:
                out = dict(self._snap_cache["data"])
                out["cached"] = True
                out["stale"] = True
                out["error"] = err_msg
                self._snap_cache["stale"] = True
                self._snap_cache["err"] = err_msg
                return out
            self._snap_cache["stale"] = True
            self._snap_cache["err"] = err_msg
            return {
                "total_value": 0.0,
                "buying_power": 0.0,
                "cash": 0.0,
                "daily_pnl_usd": 0.0,
                "daily_pnl_pct": 0.0,
                "total_pnl_usd": 0.0,
                "positions": [],
                "allocation": {},
                "asset_exposure": {},
                "active_positions": 0,
                "symbols_tracked": TRACKED_SYMBOLS,
                "cached": False,
                "stale": stale_flag,
                "error": err_msg,
            }

    def _build_snapshot_body(self) -> dict:
        if self._trading is None:
            return {
                "total_value": 0.0,
                "buying_power": 0.0,
                "cash": 0.0,
                "equity": 0.0,
                "last_equity": 0.0,
                "daily_pnl_usd": 0.0,
                "daily_pnl_pct": 0.0,
                "total_pnl_usd": 0.0,
                "realized_pnl_usd": 0.0,
                "unrealized_pnl_usd": 0.0,
                "positions": [],
                "allocation": {},
                "asset_exposure": {},
                "active_positions": 0,
                "symbols_tracked": list(TRACKED_SYMBOLS),
                "broker_connected": False,
            }

        acct = self._trading.get_account()
        equity = _safe_float(acct.equity)
        last_eq = _safe_float(acct.last_equity)
        cash = _safe_float(acct.cash)
        bp = _safe_float(acct.buying_power)

        daily_pnl_usd = equity - last_eq if last_eq > 0 else 0.0
        daily_pnl_pct = (daily_pnl_usd / last_eq * 100.0) if last_eq > 0 else 0.0

        raw_positions = self._trading.get_all_positions()
        positions: list[dict[str, Any]] = []
        unrealized = 0.0
        for p in raw_positions:
            try:
                sym = p.symbol
                canonical = position_to_agent_symbol(sym)
                mv = _safe_float(p.market_value)
                unrealized += _safe_float(p.unrealized_pl)
                positions.append(
                    {
                        "symbol": canonical,
                        "alpaca_symbol": sym,
                        "qty": _safe_float(p.qty),
                        "avg_entry_price": _safe_float(p.avg_entry_price),
                        "current_price": _safe_float(p.current_price) if p.current_price else None,
                        "market_value": mv,
                        "unrealized_pnl_usd": _safe_float(p.unrealized_pl),
                        "unrealized_pnl_pct": float(p.unrealized_plpc or 0) * 100,
                    }
                )
            except Exception:  # noqa: BLE001
                continue

        total_value = equity if equity > 0 else cash + sum(x["market_value"] for x in positions)
        allocation: dict[str, float] = {}
        if total_value > 0:
            for pos in positions:
                s = pos["symbol"]
                allocation[s] = allocation.get(s, 0.0) + (pos["market_value"] / total_value) * 100.0

        active = 0
        for sym in TRACKED_SYMBOLS:
            clean = alpaca_position_symbol(sym)
            for p in positions:
                if abs(float(p.get("qty") or 0)) < 1e-12:
                    continue
                ps = alpaca_position_symbol(str(p.get("symbol") or ""))
                if ps == clean or p.get("symbol") == sym:
                    active += 1
                    break

        asset_exposure = self.get_sector_exposure(positions)

        from core.performance_tracker import get_performance_tracker

        realized_raw = get_performance_tracker().summary().get("total_pnl_usd", 0.0)
        try:
            realized = float(realized_raw)
        except (TypeError, ValueError):
            realized = 0.0

        return {
            "total_value": round(total_value, 2),
            "buying_power": round(bp, 2),
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "last_equity": round(last_eq, 2),
            "daily_pnl_usd": round(daily_pnl_usd, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 4),
            "total_pnl_usd": round(realized + unrealized, 2),
            "realized_pnl_usd": round(realized, 2),
            "unrealized_pnl_usd": round(unrealized, 2),
            "positions": positions,
            "allocation": {k: round(v, 2) for k, v in sorted(allocation.items())},
            "asset_exposure": asset_exposure,
            "active_positions": active,
            "symbols_tracked": list(TRACKED_SYMBOLS),
            "broker_connected": True,
        }

    async def get_equity_curve(self, days: int = 30) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.get_equity_curve_sync, days)

    def get_equity_curve_sync(self, days: int = 30) -> list[dict[str, Any]]:
        if self._trading is None:
            return []
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, min(days, 3650)))
        req = GetPortfolioHistoryRequest(
            start=start,
            end=end,
            timeframe="1D",
        )
        hist = self._trading.get_portfolio_history(req)
        out: list[dict[str, Any]] = []
        for ts, val in zip(hist.timestamp, hist.equity):
            out.append({"timestamp": int(ts) * 1000, "value": float(val)})
        return out

    def get_benchmark_curve_sync(self, days: int = 30, benchmark: str = "SPY") -> list[dict[str, Any]]:
        """Daily close series for SPY (S&P 500 proxy) aligned by date."""

        if not self._stock:
            return []
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(7, days) + 5)
        try:
            bars = self._stock.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=benchmark,
                    timeframe=TimeFrame.Day,
                    start=start,
                    end=end,
                )
            )[benchmark]
        except Exception as exc:  # noqa: BLE001
            log.debug("benchmark %s: %s", benchmark, exc)
            return []
        return [
            {"timestamp": int(bar.timestamp.timestamp() * 1000), "close": float(bar.close)}
            for bar in bars
        ]

    @staticmethod
    def calculate_metrics(trades: list[Any]) -> dict[str, Any]:
        """Risk/return metrics from closed TradeRecord dicts or TradeRecord objects."""

        closed: list[TradeRecord] = []
        for t in trades:
            if isinstance(t, TradeRecord):
                rec = t
            elif isinstance(t, dict):
                fields = {k: t.get(k) for k in TradeRecord.__dataclass_fields__}
                rec = TradeRecord(**fields)
            else:
                continue
            if rec.closed and rec.pnl_usd is not None:
                closed.append(rec)

        n = len(closed)
        if n == 0:
            return {
                "trades": 0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "max_drawdown_usd": 0.0,
                "max_drawdown_duration_days": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_winner_usd": 0.0,
                "avg_loser_usd": 0.0,
                "best_trade_usd": 0.0,
                "worst_trade_usd": 0.0,
                "avg_hold_hours": 0.0,
                "trades_per_day": 0.0,
                "expectancy_usd": 0.0,
            }

        wins = [t for t in closed if (t.pnl_usd or 0) > 0]
        losses = [t for t in closed if (t.pnl_usd or 0) <= 0]
        gross_profit = sum(t.pnl_usd or 0.0 for t in wins)
        gross_loss = sum(t.pnl_usd or 0.0 for t in losses)
        total_pnl = gross_profit + gross_loss

        profit_factor = (
            (gross_profit / abs(gross_loss)) if gross_loss < 0 else (float("inf") if gross_profit > 0 else 0.0)
        )

        by_day: dict[str, float] = {}
        for t in closed:
            try:
                day = datetime.fromisoformat(t.exit_ts or "").date().isoformat()
            except Exception:
                continue
            by_day[day] = by_day.get(day, 0.0) + (t.pnl_usd or 0.0)
        daily = sorted([(d, v) for d, v in by_day.items()])
        daily_returns = [v for _, v in daily]

        def _mean(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        def _stdev(xs: list[float]) -> float:
            m = _mean(xs)
            if len(xs) < 2:
                return 0.0
            return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

        sharpe = 0.0
        if len(daily_returns) > 1:
            m = _mean(daily_returns)
            sd = _stdev(daily_returns)
            if sd > 0:
                sharpe = (m / sd) * math.sqrt(252)

        downside = [min(0.0, r) for r in daily_returns]
        sortino = 0.0
        if len(downside) > 1:
            ds = _stdev(downside)
            if ds > 0:
                sortino = (_mean(daily_returns) / ds) * math.sqrt(252)

        sorted_closed = sorted(closed, key=lambda x: x.exit_ts or "")
        equity = 0.0
        peak = 0.0
        max_dd_usd = 0.0
        peak_time: Optional[datetime] = None
        max_dd_dur_days = 0
        in_drawdown_since: Optional[datetime] = None
        for t in sorted_closed:
            equity += t.pnl_usd or 0.0
            try:
                tdt = datetime.fromisoformat(t.exit_ts or "")
            except Exception:
                continue
            if equity > peak:
                peak = equity
                peak_time = tdt
                in_drawdown_since = None
            dd = peak - equity
            if dd > max_dd_usd:
                max_dd_usd = dd
            if equity < peak:
                if in_drawdown_since is None and peak_time is not None:
                    in_drawdown_since = tdt
            else:
                in_drawdown_since = None
            if in_drawdown_since is not None:
                dur = (tdt - in_drawdown_since).total_seconds() / 86400.0
                max_dd_dur_days = max(max_dd_dur_days, dur)

        max_dd_pct = (max_dd_usd / peak * 100.0) if peak > 0 else 0.0

        pnls = [t.pnl_usd or 0.0 for t in closed]
        best = max(pnls)
        worst = min(pnls)
        holds = [t.hold_seconds for t in closed if t.hold_seconds]
        avg_hold_h = (sum(holds) / len(holds) / 3600.0) if holds else 0.0

        days_span = 1
        if daily:
            try:
                d0 = datetime.fromisoformat(daily[0][0]).date()
                d1 = datetime.fromisoformat(daily[-1][0]).date()
                days_span = max(1, (d1 - d0).days + 1)
            except Exception:
                days_span = max(1, n)

        return {
            "trades": n,
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "max_drawdown_pct": round(max_dd_pct, 3),
            "max_drawdown_usd": round(max_dd_usd, 2),
            "max_drawdown_duration_days": round(max_dd_dur_days, 2),
            "win_rate": round(len(wins) / n, 4),
            "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else None,
            "avg_winner_usd": round(gross_profit / len(wins), 4) if wins else 0.0,
            "avg_loser_usd": round(gross_loss / len(losses), 4) if losses else 0.0,
            "best_trade_usd": round(best, 4),
            "worst_trade_usd": round(worst, 4),
            "avg_hold_hours": round(avg_hold_h, 3),
            "trades_per_day": round(n / days_span, 4),
            "expectancy_usd": round(total_pnl / n, 4),
        }

    def get_correlation_matrix(self, price_data: dict[str, list[float]]) -> dict[str, dict[str, float]]:
        """
        price_data: symbol -> ordered daily closes (same length).
        Returns symmetric matrix as nested dicts for JSON heatmap.
        """
        symbols = [s for s in TRACKED_SYMBOLS if s in price_data and len(price_data[s]) > 2]
        if len(symbols) < 2:
            return {s: {s: 1.0} for s in TRACKED_SYMBOLS}

        rets: dict[str, list[float]] = {}
        for s in symbols:
            closes = price_data[s]
            r = []
            for i in range(1, len(closes)):
                a, b = closes[i - 1], closes[i]
                if a and b and a > 0:
                    r.append((b - a) / a)
                else:
                    r.append(0.0)
            rets[s] = r

        m = len(rets[symbols[0]])
        out: dict[str, dict[str, float]] = {s: {} for s in TRACKED_SYMBOLS}

        if _HAS_NP:
            arr = np.array([rets[s] for s in symbols], dtype=float)
            corr = np.corrcoef(arr)
            for i, si in enumerate(symbols):
                for j, sj in enumerate(symbols):
                    v = float(corr[i, j]) if not math.isnan(corr[i, j]) else 0.0
                    out[si][sj] = round(v, 4)
        else:
            for i, si in enumerate(symbols):
                for j, sj in enumerate(symbols):
                    if i == j:
                        out[si][sj] = 1.0
                        continue
                    xi, xj = rets[si], rets[sj]
                    n = min(len(xi), len(xj), m)
                    if n < 2:
                        out[si][sj] = 0.0
                        continue
                    mi = sum(xi[:n]) / n
                    mj = sum(xj[:n]) / n
                    num = sum((xi[k] - mi) * (xj[k] - mj) for k in range(n))
                    den_i = math.sqrt(sum((xi[k] - mi) ** 2 for k in range(n)))
                    den_j = math.sqrt(sum((xj[k] - mj) ** 2 for k in range(n)))
                    if den_i <= 0 or den_j <= 0:
                        out[si][sj] = 0.0
                    else:
                        out[si][sj] = round(num / (den_i * den_j), 4)

        for si in TRACKED_SYMBOLS:
            out.setdefault(si, {})
            for sj in TRACKED_SYMBOLS:
                out[si].setdefault(sj, out[si].get(sj, 0.0 if si != sj else 1.0))
        return out

    def fetch_daily_closes_sync(self, days: int = 30) -> dict[str, list[float]]:
        """Pull last `days` daily closes for all tracked symbols."""
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days + 5)
        out: dict[str, list[float]] = {}
        for sym in TRACKED_SYMBOLS:
            try:
                if "/" in sym:
                    bars = self._crypto.get_crypto_bars(
                        CryptoBarsRequest(
                            symbol_or_symbols=sym,
                            timeframe=TimeFrame.Day,
                            start=start,
                            end=end,
                        )
                    )[sym]
                elif self._stock:
                    bars = self._stock.get_stock_bars(
                        StockBarsRequest(
                            symbol_or_symbols=sym,
                            timeframe=TimeFrame.Day,
                            start=start,
                            end=end,
                        )
                    )[sym]
                else:
                    continue
                closes = [float(b.close) for b in bars][-days:]
                if closes:
                    out[sym] = closes
            except Exception as exc:  # noqa: BLE001
                log.debug("bars %s: %s", sym, exc)
        return out

    def get_sector_exposure(self, positions: list[dict]) -> dict[str, Any]:
        total = sum(max(0.0, float(p.get("market_value") or 0)) for p in positions)
        result: dict[str, Any] = {}
        for sector_name, members in _SECTOR_DEFS:
            syms = []
            val = 0.0
            for p in positions:
                sym = p.get("symbol") or ""
                if sym in members or position_to_agent_symbol(str(p.get("alpaca_symbol", ""))) in members:
                    syms.append(sym)
                    val += max(0.0, float(p.get("market_value") or 0))
            pct = (val / total * 100.0) if total > 0 else 0.0
            result[sector_name] = {
                "symbols": sorted(set(syms)),
                "value": round(val, 2),
                "pct": round(pct, 2),
            }
        return result


def get_portfolio_analytics() -> PortfolioAnalytics:
    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_API_SECRET", "")
    paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
    tc = None
    try:
        if key and secret:
            tc = TradingClient(key, secret, paper=paper)
    except Exception as exc:  # noqa: BLE001
        log.warning("TradingClient init failed: %s", exc)
    return PortfolioAnalytics(
        tc,
        api_key=key,
        api_secret=secret,
        paper=paper,
    )
