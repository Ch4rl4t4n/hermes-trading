"""
core/performance_tracker.py — per-trade performance log + aggregated stats.

Records every closed (entry → exit) round-trip, then derives:
    win rate, avg profit, avg loss, profit factor, expectancy,
    Sharpe ratio (daily), max drawdown, total P&L.

State is persisted to logs/performance.json so stats survive restarts.

Usage from agents:
    tracker = get_performance_tracker()
    tracker.record_entry(symbol, side, entry_price, qty, mode, regime, ...)
    ...
    tracker.record_exit(symbol, exit_price, exit_reason)

The tracker keeps a single in-flight trade per symbol; calling
`record_entry` while one is open emits a warning and replaces it.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("performance_tracker")

_PERF_PATH = Path(os.getenv("HERMES_BASE", "/root/hermes")) / "logs" / "performance.json"


@dataclass
class TradeRecord:
    symbol: str
    side: str                       # "LONG" (we're long-only for now)
    entry_ts: str                   # ISO UTC
    entry_price: float
    qty: float
    mode: str                       # scalping/day_trading/long_term/full_ai
    regime: str                     # trending_up / ranging / volatile / ...
    rsi_at_entry: Optional[float] = None
    confidence: Optional[float] = None
    exit_ts: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None    # take_profit, trailing_stop, regime_change, time_exit, manual
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    hold_seconds: Optional[float] = None

    @property
    def closed(self) -> bool:
        return self.exit_ts is not None


class PerformanceTracker:
    def __init__(self, path: Path | None = None):
        self.path = path or _PERF_PATH
        self.trades: list[TradeRecord] = []
        # symbol -> open trade index (in self.trades)
        self._open: dict[str, int] = {}
        self._load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self.path.exists():
                with open(self.path) as f:
                    raw = json.load(f)
                for d in raw.get("trades", []):
                    fields = {k: d.get(k) for k in TradeRecord.__dataclass_fields__}
                    rec = TradeRecord(**fields)
                    self.trades.append(rec)
                    if not rec.closed:
                        self._open[rec.symbol] = len(self.trades) - 1
                log.info("Loaded %d trade records (%d open)", len(self.trades), len(self._open))
        except Exception as exc:
            log.warning("Failed to load performance log (%s): starting fresh", exc)
            self.trades = []
            self._open = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "summary": self.summary(),
                "trades": [asdict(t) for t in self.trades],
            }
            tmp = self.path.with_suffix(".json.tmp")
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.debug("performance save failed: %s", exc)

    # ── Recording ──────────────────────────────────────────────────────────────

    def record_entry(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        mode: str = "day_trading",
        regime: str = "unknown",
        rsi: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """Open a new trade record for `symbol`. Replaces any existing open trade."""
        if symbol in self._open:
            log.warning("record_entry while %s already open — replacing", symbol)
        rec = TradeRecord(
            symbol=symbol,
            side=side,
            entry_ts=datetime.now(timezone.utc).isoformat(),
            entry_price=float(entry_price),
            qty=float(qty),
            mode=mode,
            regime=regime,
            rsi_at_entry=rsi,
            confidence=confidence,
        )
        self.trades.append(rec)
        self._open[symbol] = len(self.trades) - 1
        self._save()
        log.info("ENTRY  %s @ %.4f qty=%.6f mode=%s regime=%s", symbol, entry_price, qty, mode, regime)

    def record_exit(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str = "manual",
    ) -> Optional[TradeRecord]:
        """Close the open trade for `symbol` and compute its P&L."""
        idx = self._open.get(symbol)
        if idx is None:
            log.debug("record_exit %s: no open trade", symbol)
            return None
        rec = self.trades[idx]
        rec.exit_ts = datetime.now(timezone.utc).isoformat()
        rec.exit_price = float(exit_price)
        rec.exit_reason = exit_reason
        rec.pnl_usd = round((rec.exit_price - rec.entry_price) * rec.qty, 4)
        rec.pnl_pct = round((rec.exit_price - rec.entry_price) / rec.entry_price * 100.0, 4) if rec.entry_price else 0.0
        try:
            entry_dt = datetime.fromisoformat(rec.entry_ts)
            exit_dt = datetime.fromisoformat(rec.exit_ts)
            rec.hold_seconds = (exit_dt - entry_dt).total_seconds()
        except Exception:
            rec.hold_seconds = None
        self._open.pop(symbol, None)
        self._save()
        log.info(
            "EXIT   %s @ %.4f pnl=%+.4f (%+.2f%%) reason=%s hold=%.0fs",
            symbol, exit_price, rec.pnl_usd, rec.pnl_pct, exit_reason, rec.hold_seconds or 0,
        )
        return rec

    # ── Aggregations ───────────────────────────────────────────────────────────

    @staticmethod
    def _stdev(xs: list[float]) -> float:
        n = len(xs)
        if n < 2:
            return 0.0
        m = sum(xs) / n
        var = sum((x - m) ** 2 for x in xs) / (n - 1)
        return math.sqrt(var)

    def summary(self) -> dict:
        closed = [t for t in self.trades if t.closed and t.pnl_usd is not None]
        n = len(closed)
        if n == 0:
            return {
                "trades": 0,
                "win_rate": 0.0,
                "avg_profit_usd": 0.0,
                "avg_loss_usd": 0.0,
                "avg_profit_pct": 0.0,
                "avg_loss_pct": 0.0,
                "profit_factor": 0.0,
                "expectancy_usd": 0.0,
                "sharpe_daily": 0.0,
                "max_drawdown_usd": 0.0,
                "total_pnl_usd": 0.0,
                "open_trades": len(self._open),
            }

        wins = [t for t in closed if (t.pnl_usd or 0) > 0]
        losses = [t for t in closed if (t.pnl_usd or 0) <= 0]
        gross_profit = sum(t.pnl_usd or 0.0 for t in wins)
        gross_loss = sum(t.pnl_usd or 0.0 for t in losses)
        total_pnl = gross_profit + gross_loss

        avg_p = gross_profit / len(wins) if wins else 0.0
        avg_l = gross_loss / len(losses) if losses else 0.0
        avg_p_pct = sum(t.pnl_pct or 0 for t in wins) / len(wins) if wins else 0.0
        avg_l_pct = sum(t.pnl_pct or 0 for t in losses) / len(losses) if losses else 0.0

        profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else (float("inf") if gross_profit > 0 else 0.0)
        expectancy = total_pnl / n
        win_rate = len(wins) / n

        # Daily returns sequence for Sharpe; cluster by exit_ts day.
        by_day: dict[str, float] = {}
        for t in closed:
            try:
                day = datetime.fromisoformat(t.exit_ts or "").date().isoformat()
            except Exception:
                continue
            by_day[day] = by_day.get(day, 0.0) + (t.pnl_usd or 0.0)
        daily = list(by_day.values())
        sharpe = 0.0
        if len(daily) > 1:
            mean = sum(daily) / len(daily)
            sd = self._stdev(daily)
            if sd > 0:
                sharpe = (mean / sd) * math.sqrt(252)   # annualise

        # Equity curve / max drawdown (in USD over closed P&L sequence).
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(closed, key=lambda x: x.exit_ts or ""):
            equity += t.pnl_usd or 0.0
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        return {
            "trades": n,
            "win_rate": round(win_rate, 4),
            "avg_profit_usd": round(avg_p, 4),
            "avg_loss_usd": round(avg_l, 4),
            "avg_profit_pct": round(avg_p_pct, 4),
            "avg_loss_pct": round(avg_l_pct, 4),
            "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
            "expectancy_usd": round(expectancy, 4),
            "sharpe_daily": round(sharpe, 3),
            "max_drawdown_usd": round(max_dd, 4),
            "total_pnl_usd": round(total_pnl, 4),
            "open_trades": len(self._open),
        }

    def by_symbol(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for sym in {t.symbol for t in self.trades}:
            sub = [t for t in self.trades if t.symbol == sym and t.closed and t.pnl_usd is not None]
            if not sub:
                continue
            wins = sum(1 for t in sub if (t.pnl_usd or 0) > 0)
            out[sym] = {
                "trades": len(sub),
                "win_rate": round(wins / len(sub), 4) if sub else 0.0,
                "total_pnl_usd": round(sum(t.pnl_usd or 0 for t in sub), 4),
                "avg_pnl_pct": round(sum(t.pnl_pct or 0 for t in sub) / len(sub), 4) if sub else 0.0,
            }
        return out

    def recent(self, n: int = 20) -> list[dict]:
        return [asdict(t) for t in self.trades[-n:]]

    def all_trades(self) -> list[dict]:
        """All trade records newest-first (includes open trades)."""
        return [asdict(t) for t in reversed(self.trades)]


# ── Singleton ─────────────────────────────────────────────────────────────────

_singleton: Optional[PerformanceTracker] = None


def get_performance_tracker() -> PerformanceTracker:
    global _singleton
    if _singleton is None:
        _singleton = PerformanceTracker()
    return _singleton


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pt = PerformanceTracker(path=Path("/tmp/perf_test.json"))
    pt.record_entry("BTC/USD", "LONG", 60_000.0, 0.01, mode="day_trading", regime="trending_up", rsi=32.0, confidence=0.78)
    time.sleep(0.1)
    pt.record_exit("BTC/USD", 61_200.0, exit_reason="take_profit")

    pt.record_entry("ETH/USD", "LONG", 3_000.0, 0.5, mode="scalping", regime="ranging")
    pt.record_exit("ETH/USD", 2_950.0, exit_reason="trailing_stop")

    print(json.dumps(pt.summary(), indent=2))
    print("By symbol:", pt.by_symbol())
