"""
core/risk_manager.py — portfolio-level risk gate for the Hermes platform.

Responsibilities:
  - Track cumulative daily P&L across ALL agents.
  - Track all-time peak portfolio value (high-water mark).
  - Stop trading for the day if daily loss exceeds `max_daily_loss_pct`.
  - Activate the kill switch flag if total drawdown from peak exceeds
    `max_total_drawdown_pct`.
  - Persist state across process restarts (`logs/risk_state.json`) so a
    crash mid-day doesn't reset the loss counter.

The orchestrator instantiates a single RiskManager and shares it with every
agent.  Agents should call `risk_manager.can_trade(portfolio_value)` before
opening new positions and `risk_manager.update(portfolio_value, trade_pnl)`
after each closed trade.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("risk_manager")

_STATE_PATH = Path(os.getenv("HERMES_BASE", "/root/hermes")) / "logs" / "risk_state.json"
_RISK_LOG_PATH = Path(os.getenv("HERMES_BASE", "/root/hermes")) / "logs" / "risk_events.log"


@dataclass
class RiskState:
    today: str = field(default_factory=lambda: date.today().isoformat())
    daily_pnl: float = 0.0
    daily_start_portfolio: float = 0.0
    peak_portfolio: float = 0.0
    kill_switch_active: bool = False
    last_update: float = field(default_factory=time.time)


class RiskManager:
    """
    Portfolio-level risk manager.  Cheap to instantiate; expensive state
    (the JSON file) is loaded eagerly so we can pick up where we left off
    after a restart.
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 3.0,
        max_total_drawdown_pct: float = 10.0,
        state_path: Path | None = None,
    ):
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.max_total_drawdown_pct = float(max_total_drawdown_pct)
        self.state_path = state_path or _STATE_PATH
        self.state = RiskState()
        self._load_state()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        try:
            if self.state_path.exists():
                with open(self.state_path) as f:
                    raw = json.load(f)
                self.state = RiskState(**{k: v for k, v in raw.items() if k in RiskState.__dataclass_fields__})
                log.info(
                    "Loaded risk state: day=%s daily_pnl=%.2f peak=%.2f kill=%s",
                    self.state.today, self.state.daily_pnl,
                    self.state.peak_portfolio, self.state.kill_switch_active,
                )
        except Exception as exc:
            log.warning("Failed to load risk state (%s): starting fresh", exc)
            self.state = RiskState()

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(self.state.__dict__, f, indent=2, default=str)
        except OSError as exc:
            log.debug("risk state save failed: %s", exc)

    def _log_event(self, event: str, **kv) -> None:
        """Append a structured line to `logs/risk_events.log`."""
        try:
            _RISK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_RISK_LOG_PATH, "a") as f:
                ts = datetime.now(timezone.utc).isoformat()
                payload = {"ts": ts, "event": event, **kv}
                f.write(json.dumps(payload, default=str) + "\n")
        except OSError as exc:
            log.debug("risk event write failed: %s", exc)

    # ── Daily reset ────────────────────────────────────────────────────────────

    def _maybe_roll_day(self, portfolio_value: float) -> None:
        today_iso = date.today().isoformat()
        if today_iso != self.state.today:
            log.info(
                "Risk manager day rollover: %s → %s | prev daily_pnl=%.2f",
                self.state.today, today_iso, self.state.daily_pnl,
            )
            self._log_event(
                "day_rollover",
                from_day=self.state.today, to_day=today_iso,
                prev_daily_pnl=self.state.daily_pnl,
            )
            self.state.today = today_iso
            self.state.daily_pnl = 0.0
            self.state.daily_start_portfolio = portfolio_value
            self._save_state()

    # ── Public API ─────────────────────────────────────────────────────────────

    def can_trade(self, portfolio_value: float) -> bool:
        """Return False if any portfolio-level limit has been hit."""
        if portfolio_value <= 0:
            return True   # No portfolio data — fail open (rule engine has its own caps)

        self._maybe_roll_day(portfolio_value)

        if self.state.kill_switch_active:
            log.warning("Kill switch active — trading blocked")
            return False

        # Track peak BEFORE we test drawdown (in case state was loaded with
        # zero peak from first-run).
        if portfolio_value > self.state.peak_portfolio:
            self.state.peak_portfolio = portfolio_value
            self._save_state()

        if self.state.daily_start_portfolio <= 0:
            self.state.daily_start_portfolio = portfolio_value
            self._save_state()

        # Daily loss check — uses absolute USD pnl vs day-start portfolio.
        daily_start = self.state.daily_start_portfolio or portfolio_value
        if daily_start > 0:
            max_daily_loss_usd = daily_start * self.max_daily_loss_pct / 100.0
            if -self.state.daily_pnl >= max_daily_loss_usd:
                log.warning(
                    "DAILY LOSS LIMIT: pnl=%.2f >= %.1f%% of start $%.2f",
                    self.state.daily_pnl, self.max_daily_loss_pct, daily_start,
                )
                self._log_event(
                    "daily_loss_breach",
                    daily_pnl=self.state.daily_pnl,
                    max_pct=self.max_daily_loss_pct,
                    daily_start=daily_start,
                )
                return False

        # Total drawdown check.
        if self.state.peak_portfolio > 0:
            dd_pct = (self.state.peak_portfolio - portfolio_value) / self.state.peak_portfolio * 100.0
            if dd_pct >= self.max_total_drawdown_pct:
                log.error(
                    "MAX DRAWDOWN BREACH: %.2f%% from peak $%.2f → killing trading",
                    dd_pct, self.state.peak_portfolio,
                )
                self._log_event(
                    "max_drawdown_breach",
                    drawdown_pct=dd_pct,
                    peak=self.state.peak_portfolio,
                    portfolio=portfolio_value,
                )
                self.state.kill_switch_active = True
                self._save_state()
                return False

        return True

    def update(self, portfolio_value: float, trade_pnl: float) -> None:
        """Record a closed trade's P&L and update peak."""
        self._maybe_roll_day(portfolio_value)
        self.state.daily_pnl += float(trade_pnl)
        if portfolio_value > self.state.peak_portfolio:
            self.state.peak_portfolio = portfolio_value
        self.state.last_update = time.time()
        self._save_state()
        self._log_event(
            "trade_pnl",
            trade_pnl=trade_pnl,
            daily_pnl=self.state.daily_pnl,
            portfolio=portfolio_value,
            peak=self.state.peak_portfolio,
        )

    # ── Reporting / control ────────────────────────────────────────────────────

    def status(self) -> dict:
        peak = self.state.peak_portfolio
        return {
            "today": self.state.today,
            "daily_pnl": round(self.state.daily_pnl, 2),
            "daily_start_portfolio": round(self.state.daily_start_portfolio, 2),
            "peak_portfolio": round(peak, 2),
            "kill_switch_active": self.state.kill_switch_active,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_total_drawdown_pct": self.max_total_drawdown_pct,
        }

    def reset_kill_switch(self) -> None:
        log.warning("Manual kill-switch RESET")
        self._log_event("kill_switch_reset")
        self.state.kill_switch_active = False
        self._save_state()


# ── Module-level singleton ────────────────────────────────────────────────────

_singleton: Optional[RiskManager] = None


def get_risk_manager(
    max_daily_loss_pct: float = 3.0,
    max_total_drawdown_pct: float = 10.0,
) -> RiskManager:
    global _singleton
    if _singleton is None:
        _singleton = RiskManager(max_daily_loss_pct, max_total_drawdown_pct)
    return _singleton


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rm = RiskManager(max_daily_loss_pct=3.0, max_total_drawdown_pct=10.0,
                     state_path=Path("/tmp/risk_state_test.json"))
    print("can_trade(100k):", rm.can_trade(100_000))
    rm.update(100_000, -2_000)
    print("After -$2k:    ", rm.can_trade(98_000))
    rm.update(98_000, -2_000)
    print("After -$4k:    ", rm.can_trade(96_000))   # should False (>3%)
    print("Status:", rm.status())
