import os
import asyncio
import json
import logging
import time
from collections import deque
from abc import ABC
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, date, time as dtime, timezone
from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, LimitOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, OrderType, QueryOrderStatus, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, CryptoBarsRequest,
    StockLatestQuoteRequest, CryptoLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

if TYPE_CHECKING:
    from core.data_feed import DataFeed
    from core.risk_manager import RiskManager

DRY_RUN = os.getenv("HERMES_DRY_RUN", "true").lower() == "true"
_RSI_KNIFE_BUFFER = 20.0
_MACD_SIGNAL_PERIOD = 9

_PORTFOLIO_CACHE_TTL = 300   # seconds between Alpaca account API calls

# ── Trading-mode max-hold defaults (seconds) ──────────────────────────────────
# Used by the new time-based exit logic.  Override per agent via cfg.
_MAX_HOLD_BY_MODE = {
    "scalping": 4 * 3600,         # 4 hours
    "day_trading": 8 * 3600,      # 8 hours
    "long_term": 14 * 24 * 3600,  # 14 days
    "full_ai": 24 * 3600,        # LLM-led: intraday–swing window (24h)
}

# ── Session windows (UTC) ─────────────────────────────────────────────────────
# Crypto: best during overlap of US (14:30–16:00 UTC) and Asia open (00:00–02:00 UTC)
# Stocks: only trade during regular hours (13:30–20:00 UTC), best first/last hour
_CRYPTO_PRIME_HOURS_UTC = [(14, 30, 16, 0), (0, 0, 2, 0)]
_STOCK_PRIME_HOURS_UTC = [(13, 30, 14, 30), (19, 0, 20, 0)]
_STOCK_REGULAR_UTC = (13, 30, 20, 0)

# Anti-FOMO threshold: pct move in last hour that triggers a wait-for-pullback.
_ANTI_FOMO_PCT = 3.0

# Take-profit scaling: % of position to sell at first TP target.
_TP1_SELL_FRACTION = 0.5


def _parse_duration_seconds(interval: str) -> int:
    """e.g. 4h, 30m, 3600, 1d → seconds."""
    s = str(interval).strip().lower()
    if s.isdigit():
        return int(s)
    num = "".join(c for c in s if c.isdigit() or c == ".")
    unit = "".join(c for c in s if c.isalpha())
    try:
        n = float(num) if num else 1.0
    except ValueError:
        return 3600
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit[:1] if unit else "h", 3600)
    return int(n * mult)


@dataclass
class SignalResult:
    direction: str       # "BUY" | "SELL" | "HOLD"
    confidence: float    # 0.0 – 1.0
    reason: str
    # Set by the LLM advisor when it returns a richer decision; optional so
    # rule-only signals don't have to populate them.
    position_size_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


@dataclass
class AgentConfig:
    name: str
    symbol: str
    asset_type: str      # "crypto" | "stock" | "commodity_etf"
    enabled: bool
    trade_usd: float
    timezone: str
    active_hours_start: dtime
    active_hours_end: dtime
    check_interval_seconds: int
    rsi_period: int
    rsi_buy_threshold: float
    rsi_sell_threshold: float
    macd_enabled: bool
    signal_confidence_threshold: float
    llm_enabled: bool
    llm_trigger_threshold: float
    llm_model: str
    llm_max_calls_per_hour: int
    llm_use_sonnet_above: float
    trailing_stop_pct: float
    take_profit_pct: float
    max_trades_per_day: int
    max_daily_loss_pct: float
    max_position_pct: float
    # Strategy fields (all have defaults for backwards compatibility)
    timeframe: str = "1m"               # "4h" | "1h" | "15m" | "1m"
    trailing_activate_pct: float = 0.0  # min gain% before trailing stop activates
    atr_position_sizing: bool = False   # use ATR-based qty (VolatileStrategy)
    trading_mode: str = "day_trading"   # scalping | day_trading | long_term | full_ai — LLM prompt + sizing + holds
    dca: dict = field(default_factory=dict)
    grid: dict = field(default_factory=dict)
    scheduled_orders: list = field(default_factory=list)
    take_profit_scaled: dict = field(default_factory=dict)


class BaseAgent(ABC):
    HISTORY_BARS = 50

    def __init__(
        self,
        config: AgentConfig,
        feed: Optional["DataFeed"] = None,
        risk_manager: Optional["RiskManager"] = None,
    ):
        self.cfg = config
        self.name = config.name
        self.symbol = config.symbol
        self.feed = feed
        self.risk_manager = risk_manager

        self.prices: list[float] = []
        self.entry_price: Optional[float] = None
        self.position_qty: float = 0.0
        self.entry_qty: float = 0.0          # original qty (used for TP scaling)
        self.entry_time: Optional[datetime] = None
        self.tp1_taken: bool = False
        self.tp2_taken: bool = False
        self.last_llm_decision = None         # LLMDecision | None
        self.last_regime: str = "unknown"
        self.last_regime_details: dict = {}
        self.trades_today: int = 0
        self.daily_loss_usd: float = 0.0
        self.paused_by_limit: bool = False
        self.paused_manually: bool = False
        self.llm_calls_this_hour: int = 0
        self._llm_hour: int = -1
        self._tick_count: int = 0
        self._regime_check_ts: float = 0.0
        self._cached_market_context: dict = {}
        self._market_context_ts: float = 0.0

        self._portfolio_cache: float = 0.0
        self._portfolio_ts: float = 0.0
        self._high_water_mark: float = 0.0
        self._macd_line_buffer: deque[float] = deque(maxlen=200)
        self._daily_loss_alert_sent: bool = False
        self._dca_last_ts: float = 0.0
        self._grid_last_sync: float = 0.0
        self._scheduled_fired: dict[str, bool] = {}
        self.grid_session_pnl: float = 0.0

        self._trading = TradingClient(
            os.getenv("ALPACA_API_KEY"),
            os.getenv("ALPACA_API_SECRET"),
            paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
        )
        if config.asset_type == "crypto":
            self._data: StockHistoricalDataClient | CryptoHistoricalDataClient = (
                CryptoHistoricalDataClient()
            )
        else:
            self._data = StockHistoricalDataClient(
                api_key=os.getenv("ALPACA_API_KEY"),
                secret_key=os.getenv("ALPACA_API_SECRET"),
            )

        self.log = logging.getLogger(self.name)

    # ── Advanced mode + calendar helpers ──────────────────────────────────────

    @staticmethod
    def _cfg_bool(block: dict, key: str) -> bool:
        return bool((block or {}).get(key))

    def _dca_enabled(self) -> bool:
        return self._cfg_bool(self.cfg.dca, "enabled")

    def _grid_enabled(self) -> bool:
        return self._cfg_bool(self.cfg.grid, "enabled")

    def _calendar_constraints(self) -> dict:
        try:
            from core.economic_calendar import get_trading_constraints

            return get_trading_constraints()
        except Exception as exc:
            self.log.debug("calendar constraints: %s", exc)
            return {"size_mult": 1.0, "pause_new_entries": False, "paused_symbols": []}

    def _symbol_paused_by_calendar(self) -> bool:
        cal = self._calendar_constraints()
        paused = cal.get("paused_symbols") or []
        sym = self.symbol.replace("/", "").upper()
        base = sym[:4] if len(sym) > 4 else sym
        for p in paused:
            p0 = str(p).upper().replace("/", "")
            if p0 == sym or p0 == base or p in (self.symbol,):
                return True
        return False

    # ── Market hours ───────────────────────────────────────────────────────────

    def is_market_open(self) -> bool:
        tz = ZoneInfo(self.cfg.timezone)
        now = datetime.now(tz).time()
        return self.cfg.active_hours_start <= now <= self.cfg.active_hours_end

    # ── Price data ─────────────────────────────────────────────────────────────

    def bootstrap_price_history(self) -> None:
        """Sync price history from DataFeed if available, else fetch directly."""
        if self.feed:
            history = self.feed.get_history(self.symbol)
            if history:
                self.prices = history
                self.log.info("Synced %d price bars from DataFeed for %s", len(self.prices), self.symbol)
                return
        # Fallback: fetch directly (used when no DataFeed)
        try:
            bars = self._fetch_bars(self.HISTORY_BARS)
            self.prices = [float(b.close) for b in bars]
            self.log.info("Bootstrapped %d bars (direct) for %s", len(self.prices), self.symbol)
        except Exception as exc:
            self.log.warning("Bootstrap failed for %s: %s", self.symbol, exc)

    def _fetch_bars(self, limit: int):
        tf = self._timeframe_to_alpaca()
        if self.cfg.asset_type == "crypto":
            req = CryptoBarsRequest(symbol_or_symbols=self.symbol, timeframe=tf, limit=limit)
            return self._data.get_crypto_bars(req)[self.symbol]
        else:
            req = StockBarsRequest(symbol_or_symbols=self.symbol, timeframe=tf, limit=limit)
            return self._data.get_stock_bars(req)[self.symbol]

    def _timeframe_to_alpaca(self) -> TimeFrame:
        tf = self.cfg.timeframe
        if tf == "4h":
            return TimeFrame(4, TimeFrameUnit.Hour)
        elif tf == "1h":
            return TimeFrame.Hour
        elif tf == "15m":
            return TimeFrame(15, TimeFrameUnit.Minute)
        return TimeFrame.Minute

    def _sync_prices_from_feed(self) -> None:
        if self.feed:
            history = self.feed.get_history(self.symbol)
            if history:
                self.prices = history

    def get_current_price(self) -> float:
        """Pull from DataFeed if available; otherwise fetch directly."""
        if self.feed:
            price = self.feed.get_price(self.symbol)
            if price > 0:
                return price

        # Direct fetch fallback
        try:
            if self.cfg.asset_type == "crypto":
                req = CryptoLatestQuoteRequest(symbol_or_symbols=self.symbol)
                quote = self._data.get_crypto_latest_quote(req)
                price = float(quote[self.symbol].ask_price)
            else:
                req = StockLatestQuoteRequest(symbol_or_symbols=self.symbol)
                quote = self._data.get_stock_latest_quote(req)
                price = float(quote[self.symbol].ask_price)
                if price == 0.0:
                    trade_req = StockLatestTradeRequest(symbol_or_symbols=self.symbol)
                    trade = self._data.get_stock_latest_trade(trade_req)
                    price = float(trade[self.symbol].price)

            if price > 0:
                self.prices.append(price)
                if len(self.prices) > self.HISTORY_BARS:
                    self.prices.pop(0)
            return price
        except Exception as exc:
            self.log.warning("Price fetch failed for %s: %s", self.symbol, exc)
            return self.prices[-1] if self.prices else 0.0

    # ── Technical indicators ───────────────────────────────────────────────────

    def calculate_rsi(self) -> float:
        period = self.cfg.rsi_period
        if len(self.prices) < period + 1:
            return 50.0
        closes = self.prices[-(period + 1):]
        gains  = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
        losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        # FIX: flat market (no moves) → neutral, not overbought
        if avg_gain == 0.0 and avg_loss == 0.0:
            return 50.0
        if avg_loss == 0.0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @staticmethod
    def _ema(prices: list[float], period: int) -> float:
        """Proper EMA over full price history, seeded with SMA."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        k = 2 / (period + 1)
        result = sum(prices[:period]) / period   # seed with SMA
        for p in prices[period:]:
            result = p * k + result * (1 - k)
        return result

    def calculate_macd(self) -> tuple[float, float, float]:
        """Returns (macd_line, signal_line, histogram). Signal = EMA(9) of MACD line history."""
        if len(self.prices) < 26:
            return 0.0, 0.0, 0.0
        if not hasattr(self, "_macd_line_buffer"):
            self._macd_line_buffer = deque(maxlen=200)
        last = self.prices[-1] if self.prices else 0.0
        cache_key = (len(self.prices), round(last, 8))
        if getattr(self, "_macd_cache_key", None) == cache_key and hasattr(self, "_macd_cache_val"):
            return self._macd_cache_val  # avoid double buffer append in same tick (e.g. TrendingStrategy)
        ema12 = self._ema(self.prices, 12)
        ema26 = self._ema(self.prices, 26)
        macd_line = ema12 - ema26
        self._macd_line_buffer.append(macd_line)
        buf = list(self._macd_line_buffer)
        if len(buf) < _MACD_SIGNAL_PERIOD:
            signal_line = macd_line * (2 / 10)   # early bars: same fallback as before
        else:
            signal_line = self._ema(buf, _MACD_SIGNAL_PERIOD)
        histogram = macd_line - signal_line
        out = (round(macd_line, 4), round(signal_line, 4), round(histogram, 4))
        self._macd_cache_key = cache_key
        self._macd_cache_val = out
        return out

    def calculate_vwap(self) -> float:
        if not self.prices:
            return 0.0
        return round(sum(self.prices) / len(self.prices), 4)

    def calculate_atr(self, period: int = 14) -> float:
        """Close-only ATR proxy — abs differences over `period` bars."""
        if len(self.prices) < period + 1:
            return 0.0
        closes = self.prices[-(period + 1):]
        ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        return sum(ranges) / period if ranges else 0.0

    def calculate_atr_average(self, period: int = 14, lookback: int = 50) -> float:
        """Average of rolling ATR over `lookback` windows (proxy for "normal" ATR)."""
        if len(self.prices) < period + lookback:
            return self.calculate_atr(period)
        atrs: list[float] = []
        for end in range(len(self.prices) - lookback, len(self.prices)):
            window = self.prices[max(0, end - period): end + 1]
            if len(window) >= period + 1:
                ranges = [abs(window[i] - window[i - 1]) for i in range(1, len(window))]
                atrs.append(sum(ranges) / period)
        return sum(atrs) / len(atrs) if atrs else 0.0

    def pct_change_window(self, bars: int) -> float:
        """% change over the last `bars` price points; 0 if not enough data."""
        if len(self.prices) <= bars:
            return 0.0
        old = self.prices[-(bars + 1)]
        new = self.prices[-1]
        if old <= 0:
            return 0.0
        return (new - old) / old * 100.0

    # ── Signal generation ──────────────────────────────────────────────────────

    def get_rule_signal(self) -> SignalResult:
        rsi = self.calculate_rsi()
        _, _, histogram = self.calculate_macd()
        price = self.prices[-1] if self.prices else 0.0
        vwap = self.calculate_vwap()

        if rsi < self.cfg.rsi_buy_threshold:
            rsi_dir = "BUY"
            rsi_conf = (self.cfg.rsi_buy_threshold - rsi) / self.cfg.rsi_buy_threshold
            # Risk: avoid aggressive buys in "falling knife" (very oversold)
            if rsi < _RSI_KNIFE_BUFFER and rsi > 0:
                rsi_conf *= 0.85
        elif rsi > self.cfg.rsi_sell_threshold:
            rsi_dir = "SELL"
            rsi_conf = (rsi - self.cfg.rsi_sell_threshold) / (100 - self.cfg.rsi_sell_threshold)
        else:
            rsi_dir, rsi_conf = "HOLD", 0.0

        macd_dir = "HOLD"
        macd_conf = 0.0
        if self.cfg.macd_enabled and histogram != 0.0:
            macd_dir = "BUY" if histogram > 0 else "SELL"
            denom = abs(self.prices[-1]) if self.prices else 1.0
            macd_conf = min(abs(histogram) / (denom * 0.001 + 1e-9), 1.0)

        vwap_bonus = 0.0
        if vwap > 0 and price > 0:
            if rsi_dir == "BUY" and price > vwap:
                vwap_bonus = 0.05
            elif rsi_dir == "SELL" and price < vwap:
                vwap_bonus = 0.05

        if rsi_dir == macd_dir and rsi_dir != "HOLD":
            direction = rsi_dir
            confidence = min(rsi_conf * 0.6 + macd_conf * 0.4 + vwap_bonus, 1.0)
        elif rsi_dir != "HOLD":
            direction = rsi_dir
            confidence = min(rsi_conf * 0.7 + vwap_bonus, 1.0)
        else:
            direction = "HOLD"
            confidence = 0.0

        reason = (
            f"RSI={rsi:.1f}({rsi_dir}) "
            f"MACD_hist={histogram:+.4f}({macd_dir}) "
            f"VWAP={vwap:.2f} price={price:.2f}"
        )
        return SignalResult(direction=direction, confidence=round(confidence, 3), reason=reason)

    def get_signal(self) -> SignalResult:
        """Strategic entry point for the rule engine. Most agents override via `get_rule_signal`."""
        return self.get_rule_signal()

    # ── Daily limits ───────────────────────────────────────────────────────────

    def check_daily_limits(self) -> bool:
        if self.paused_by_limit:
            return False
        if self.trades_today >= self.cfg.max_trades_per_day:
            self.log.warning("%s: daily trade limit reached (%d)", self.name, self.cfg.max_trades_per_day)
            self.paused_by_limit = True
            return False
        portfolio = self._get_portfolio_value()
        max_loss = portfolio * (self.cfg.max_daily_loss_pct / 100)
        if self.daily_loss_usd >= max_loss:
            self.log.warning("%s: daily loss limit $%.2f reached", self.name, self.daily_loss_usd)
            self.paused_by_limit = True
            return False
        return True

    def reset_daily_counters_if_new_day(self, last_reset: date) -> date:
        today = date.today()
        if today != last_reset:
            self.trades_today = 0
            self.daily_loss_usd = 0.0
            self.paused_by_limit = False
            self._daily_loss_alert_sent = False
            self.log.info("Daily counters reset for %s", today)
            return today
        return last_reset

    def _check_daily_loss_alert(self) -> None:
        """Alert once per day when drawdown vs portfolio exceeds HERMES_DAILY_LOSS_ALERT_PCT."""
        try:
            thr = float(os.getenv("HERMES_DAILY_LOSS_ALERT_PCT", "1.5"))
        except ValueError:
            return
        if thr <= 0 or self._daily_loss_alert_sent:
            return
        pv = self._get_portfolio_value()
        if pv <= 0 or self.daily_loss_usd <= 0:
            return
        pct = (self.daily_loss_usd / pv) * 100.0
        if pct < thr:
            return
        self._daily_loss_alert_sent = True
        self.log.warning(
            "%s: daily loss alert — $%.2f (%.2f%% of portfolio vs limit %.1f%%)",
            self.name, self.daily_loss_usd, pct, thr,
        )
        try:
            from notifications import telegram
            telegram.send(
                f"⚠️ <b>{self.name}</b> daily loss <b>${self.daily_loss_usd:.2f}</b> "
                f"({pct:.2f}% of portfolio, threshold {thr:.1f}%)"
            )
        except Exception as exc:
            self.log.debug("Telegram daily-loss alert: %s", exc)

    # ── Order execution ────────────────────────────────────────────────────────

    def submit_order(
        self,
        side: str,
        qty: float,
        exit_reason: str = "manual",
        *,
        accumulate: bool = False,
    ) -> bool:
        """Send a market order.  In DRY_RUN we just simulate locally.

        The `exit_reason` parameter is forwarded to the performance tracker
        when this is a SELL; ignored for BUY.

        accumulate=True blends into an existing long (DCA add-on buys).
        """
        price = self.prices[-1] if self.prices else 0.0
        is_partial_exit = side == "SELL" and qty < self.position_qty

        if DRY_RUN:
            self.log.info(
                "[DRY-RUN] %s %s qty=%.6f @ $%.4f  (not sent to Alpaca)",
                side, self.symbol, qty, price,
            )
            self._record_local_fill(side, qty, price, exit_reason, is_partial_exit, accumulate=accumulate)
            self._check_daily_loss_alert()
            return True

        tif = TimeInForce.GTC if self.cfg.asset_type == "crypto" else TimeInForce.DAY
        order = MarketOrderRequest(
            symbol=self.symbol,
            qty=qty,
            side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=tif,
        )
        try:
            response = self._trading.submit_order(order)
            self._record_local_fill(side, qty, price, exit_reason, is_partial_exit, accumulate=accumulate)
            self.log.info(
                "%s %s qty=%.6f @ $%.4f  order_id=%s",
                side, self.symbol, qty, price, response.id,
            )
            self._check_daily_loss_alert()
            return True
        except Exception as exc:
            self.log.error("Order failed: %s", exc)
            return False

    def submit_limit_order(self, side: str, qty: float, limit_price: float, client_order_id: str) -> bool:
        tif = TimeInForce.GTC if self.cfg.asset_type == "crypto" else TimeInForce.DAY
        req = LimitOrderRequest(
            symbol=self.symbol,
            qty=qty,
            limit_price=round(float(limit_price), 6 if self.cfg.asset_type == "crypto" else 2),
            side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            time_in_force=tif,
            client_order_id=client_order_id[:48],
        )
        if DRY_RUN:
            self.log.info("[DRY-RUN] LIMIT %s %s @ %.4f qty=%.6f id=%s", side, self.symbol, limit_price, qty, client_order_id)
            return True
        try:
            self._trading.submit_order(req)
            return True
        except Exception as exc:
            self.log.warning("Limit order failed: %s", exc)
            return False

    def _record_local_fill(
        self,
        side: str,
        qty: float,
        price: float,
        exit_reason: str,
        is_partial_exit: bool,
        *,
        accumulate: bool = False,
    ) -> None:
        """Update local position state + risk_manager + performance_tracker
        on a BUY/SELL fill.  Shared between DRY_RUN and live paths."""
        self.trades_today += 1
        if side == "BUY":
            if accumulate and self.position_qty > 0 and self.entry_price:
                new_qty = self.position_qty + qty
                self.entry_price = (self.entry_price * self.position_qty + price * qty) / new_qty
                self.position_qty = new_qty
                self.entry_qty = new_qty
                self.entry_time = self.entry_time or datetime.now(timezone.utc)
                self.log.debug("DCA/grid scale-in: avg entry → %.4f qty=%.6f", self.entry_price, self.position_qty)
            else:
                self.entry_price = price
                self.position_qty = qty
                self.entry_qty = qty
                self.entry_time = datetime.now(timezone.utc)
                self.tp1_taken = False
                self.tp2_taken = False
                self._high_water_mark = price
            if not self._dca_enabled() and not accumulate:
                try:
                    from core.performance_tracker import get_performance_tracker
                    conf = float(self.last_llm_decision.confidence) if self.last_llm_decision else None
                    get_performance_tracker().record_entry(
                        symbol=self.symbol,
                        side="LONG",
                        entry_price=price,
                        qty=qty,
                        mode=self.cfg.trading_mode,
                        regime=self.last_regime,
                        rsi=self.calculate_rsi(),
                        confidence=conf,
                    )
                except Exception as exc:
                    self.log.debug("performance_tracker entry failed: %s", exc)
            return

        # SELL path
        pnl = 0.0
        if self.entry_price:
            pnl = (price - self.entry_price) * qty
            if self._grid_enabled():
                self.grid_session_pnl += pnl
            if pnl < 0:
                self.daily_loss_usd += abs(pnl)

        # Update risk manager with the realised P&L on every exit.
        if self.risk_manager is not None:
            try:
                self.risk_manager.update(self._get_portfolio_value(), pnl)
            except Exception as exc:
                self.log.debug("risk_manager.update failed: %s", exc)

        if is_partial_exit:
            self.position_qty -= qty
            if exit_reason == "take_profit_2":
                self.tp2_taken = True
            elif exit_reason == "take_profit_1":
                self.tp1_taken = True
            self.log.info(
                "Partial SELL %s qty=%.6f remaining=%.6f reason=%s",
                self.symbol, qty, self.position_qty, exit_reason,
            )
            return

        if not self._dca_enabled():
            try:
                from core.performance_tracker import get_performance_tracker

                get_performance_tracker().record_exit(self.symbol, price, exit_reason)
            except Exception as exc:
                self.log.debug("performance_tracker exit failed: %s", exc)

        self.entry_price = None
        self.position_qty = 0.0
        self.entry_qty = 0.0
        self.entry_time = None
        self.tp1_taken = False
        self.tp2_taken = False
        self._high_water_mark = 0.0

    def check_exit_conditions(self) -> None:
        """Multi-stage exit logic:

        1. **Regime crash** — if market regime flips to "crash", emergency-exit.
        2. **DCA mode** — no TP / trailing / timed exit (accumulation only).
        3. **Grid mode** — optional trailing exit only (`grid.trailing_exit`).
        4. **Time-based exit** — if held longer than max_hold for the mode, exit.
        5. **Take profit** — YAML `take_profit` ladder or cfg.take_profit_pct.
        6. **TP1 scaling** — legacy half-target partial.
        7. **Trailing stop** — once gain crossed trailing_activate_pct.
        """
        if self.position_qty <= 0 or not self.entry_price:
            self._high_water_mark = 0.0
            return
        price = self.prices[-1] if self.prices else 0.0
        if price <= 0:
            return
        pct = (price - self.entry_price) / self.entry_price * 100

        if self.last_regime == "crash":
            self.log.warning("REGIME_EXIT: regime=crash → flushing position")
            self.submit_order("SELL", self.position_qty, exit_reason="regime_change")
            return

        if self._dca_enabled():
            return

        grid_cfg = self.cfg.grid or {}
        if self._grid_enabled() and not bool(grid_cfg.get("trailing_exit", False)):
            return

        if self.entry_time is not None:
            held = (datetime.now(timezone.utc) - self.entry_time).total_seconds()
            max_hold = _MAX_HOLD_BY_MODE.get(self.cfg.trading_mode, _MAX_HOLD_BY_MODE["day_trading"])
            if held >= max_hold:
                self.log.info(
                    "TIME_EXIT: held %.0fs (max %ds for %s) pnl=%+.2f%%",
                    held, max_hold, self.cfg.trading_mode, pct,
                )
                self.submit_order("SELL", self.position_qty, exit_reason="time_exit")
                return

        tp_cfg = self.cfg.take_profit_scaled or {}
        tp1 = tp_cfg.get("tp1")
        if tp1 is not None:
            dec = 6 if self.cfg.asset_type == "crypto" else 4
            tp1_thr = float(tp1) * 100.0
            tp2_val = tp_cfg.get("tp2")
            tp2_thr = float(tp2_val) * 100.0 if tp2_val is not None else None
            sell1 = float(tp_cfg.get("sell_fraction_1", 0.5))
            sell2 = float(tp_cfg.get("sell_fraction_2", 0.3))

            if pct >= tp1_thr and not self.tp1_taken:
                sell_qty = min(round(self.entry_qty * sell1, dec), self.position_qty)
                if sell_qty > 0:
                    self.log.info("TP1 ladder sell at %.2f%% gain", pct)
                    self.submit_order("SELL", sell_qty, exit_reason="take_profit_1")
                    return

            if tp2_thr is not None and pct >= tp2_thr and not self.tp2_taken:
                sell_qty = min(round(self.entry_qty * sell2, dec), self.position_qty)
                if sell_qty > 0:
                    self.log.info("TP2 ladder sell at %.2f%% gain", pct)
                    self.submit_order("SELL", sell_qty, exit_reason="take_profit_2")
                    return

        elif pct >= self.cfg.take_profit_pct:
            self.log.info("TAKE_PROFIT at %.2f%% gain", pct)
            self.submit_order("SELL", self.position_qty, exit_reason="take_profit")
            return

        if not self.cfg.take_profit_scaled or self.cfg.take_profit_scaled.get("tp1") is None:
            tp1_target = self.cfg.take_profit_pct * 0.5
            if not self.tp1_taken and tp1_target > 0 and pct >= tp1_target:
                tp1_qty = round(
                    self.entry_qty * _TP1_SELL_FRACTION,
                    6 if self.cfg.asset_type == "crypto" else 4,
                )
                tp1_qty = min(tp1_qty, self.position_qty)
                if tp1_qty > 0:
                    self.log.info(
                        "TP1 partial sell: %.2f%% gain → SELL %.6f (50%% of original %.6f)",
                        pct, tp1_qty, self.entry_qty,
                    )
                    self.submit_order("SELL", tp1_qty, exit_reason="take_profit_1")

        if self._high_water_mark == 0.0:
            self._high_water_mark = self.entry_price
        if price > self._high_water_mark:
            self._high_water_mark = price

        if self.cfg.trailing_activate_pct > 0:
            hwm_gain = (self._high_water_mark - self.entry_price) / self.entry_price * 100
            if hwm_gain < self.cfg.trailing_activate_pct:
                return

        ref = self._high_water_mark if self._high_water_mark > self.entry_price else self.entry_price
        drop = (ref - price) / ref * 100
        if drop >= self.cfg.trailing_stop_pct:
            self.log.info("TRAILING_STOP %.2f%% from peak=%.4f", drop, ref)
            self.submit_order("SELL", self.position_qty, exit_reason="trailing_stop")

    # ── Portfolio ──────────────────────────────────────────────────────────────

    def _get_portfolio_value(self) -> float:
        now = time.monotonic()
        if self._portfolio_cache > 0 and (now - self._portfolio_ts) < _PORTFOLIO_CACHE_TTL:
            return self._portfolio_cache
        try:
            value = float(self._trading.get_account().portfolio_value)
            self._portfolio_cache = value
            self._portfolio_ts = now
            return value
        except Exception:
            return self._portfolio_cache or 100_000.0

    def calculate_qty(self, price: float) -> float:
        """Volatility-adjusted position sizing.

        Base size comes from the LLM decision when available, otherwise
        `cfg.max_position_pct`.  We then scale DOWN when current ATR is
        elevated vs its rolling average ("noisy market = smaller size") and
        scale up when ATR is below normal.  Result is capped at
        `cfg.max_position_pct` and `cfg.trade_usd` to honour pre-existing
        per-agent limits.

        We also apply a session-quality multiplier (`get_session_multiplier`)
        so off-hours trades are smaller.
        """
        if price <= 0:
            return 0.0

        portfolio = self._get_portfolio_value()

        # Base size — LLM size if available, otherwise the configured cap.
        if self.last_llm_decision is not None and getattr(self.last_llm_decision, "position_size_pct", None):
            base_size_pct = float(self.last_llm_decision.position_size_pct)
        else:
            base_size_pct = float(self.cfg.max_position_pct)

        # ATR adjustment — high vol shrinks, low vol expands.
        atr = self.calculate_atr(14)
        normal_atr = self.calculate_atr_average(14, lookback=50)
        volatility_ratio = (atr / normal_atr) if normal_atr > 0 else 1.0
        adjusted_size = base_size_pct / max(volatility_ratio, 0.5)

        # Session-quality multiplier.
        session_mult = self.get_session_multiplier()
        adjusted_size *= session_mult

        # Final cap at hard config limits.
        adjusted_size = min(adjusted_size, self.cfg.max_position_pct)

        max_usd_by_pct = portfolio * adjusted_size
        max_usd_by_cfg = self.cfg.trade_usd
        max_usd = min(max_usd_by_pct, max_usd_by_cfg)

        if max_usd <= 0:
            return 0.0

        decimals = 6 if self.cfg.asset_type == "crypto" else 4
        qty = round(max_usd / price, decimals)

        sm = float(self._calendar_constraints().get("size_mult") or 1.0)
        if sm < 0.999 and sm > 0:
            qty = round(qty * sm, decimals)

        self.log.debug(
            "calculate_qty: base=%.3f atr=%.4f normal=%.4f ratio=%.2f session=%.2f → size=%.3f USD=%.2f qty=%s",
            base_size_pct, atr, normal_atr, volatility_ratio, session_mult, adjusted_size, max_usd, qty,
        )
        return qty

    # ── Session timing ─────────────────────────────────────────────────────────

    def get_session_multiplier(self) -> float:
        """Return a 0.5..1.0 multiplier reflecting session quality.

        Crypto is 24/7 but US/Asia opens are typically the highest-volume
        windows — outside those we shave size by 50%.

        Stocks are gated to regular hours; outside regular hours
        get_signal already returns nothing useful, but we still return
        0.5 just in case.  First/last hour of regular session = full size.
        """
        now = datetime.now(timezone.utc)
        h, m = now.hour, now.minute
        cur = h * 60 + m

        def _in(ranges) -> bool:
            for sh, sm, eh, em in ranges:
                start = sh * 60 + sm
                end = eh * 60 + em
                if start <= cur <= end:
                    return True
            return False

        if self.cfg.asset_type == "crypto":
            return 1.0 if _in(_CRYPTO_PRIME_HOURS_UTC) else 0.5

        # Stock-like (stock or commodity_etf)
        sh, sm, eh, em = _STOCK_REGULAR_UTC
        if not (sh * 60 + sm <= cur <= eh * 60 + em):
            return 0.5
        return 1.0 if _in(_STOCK_PRIME_HOURS_UTC) else 0.75

    def is_prime_session(self) -> bool:
        return self.get_session_multiplier() >= 1.0

    # ── Market context cache (for regime detection / correlation filter) ──────

    _MARKET_CONTEXT_TTL = 300   # seconds

    async def _get_cached_market_context(self) -> dict:
        """Fetch or reuse the last `get_market_context()` payload."""
        now = time.time()
        if self._cached_market_context and (now - self._market_context_ts) < self._MARKET_CONTEXT_TTL:
            return self._cached_market_context
        try:
            from core.external_data import get_market_context
            ext_asset_type = "crypto" if self.cfg.asset_type == "crypto" else "stock"
            ctx = await get_market_context(self.symbol, ext_asset_type)
            self._cached_market_context = ctx or {}
            self._market_context_ts = now
            return self._cached_market_context
        except Exception as exc:
            self.log.debug("market_context fetch failed: %s", exc)
            return self._cached_market_context or {}

    async def _detect_regime_for_tick(self) -> None:
        """Update self.last_regime / self.last_regime_details (cached briefly)."""
        try:
            from core.regime_detector import detect_regime
            ctx = await self._get_cached_market_context()
            res = await detect_regime(self.symbol, self.cfg.asset_type, self.prices, ctx)
            self.last_regime = res.regime
            self.last_regime_details = res.details
        except Exception as exc:
            self.log.debug("regime detection failed: %s", exc)

    async def _apply_correlation_filter(self, signal: SignalResult) -> SignalResult:
        if signal.direction == "HOLD":
            return signal
        try:
            from core.correlation_filter import apply_correlation_filter
            ctx = await self._get_cached_market_context()
            mult, reason = await apply_correlation_filter(
                self.symbol, self.cfg.asset_type, signal.direction, ctx,
            )
        except Exception as exc:
            self.log.debug("correlation filter failed: %s", exc)
            return signal

        if mult == 1.0:
            return signal
        new_conf = max(0.0, min(1.0, signal.confidence * mult))
        return SignalResult(
            direction=signal.direction,
            confidence=round(new_conf, 3),
            reason=signal.reason + f" | corr({mult:.2f}: {reason})",
            position_size_pct=signal.position_size_pct,
            stop_loss_pct=signal.stop_loss_pct,
            take_profit_pct=signal.take_profit_pct,
        )

    def _anti_fomo_block(self, signal: SignalResult) -> bool:
        """Return True if this is a BUY arriving right after a >3% 1h pump.
        We want to wait for a pullback rather than chase the move.
        """
        if signal.direction != "BUY":
            return False
        # Approximate "1h" with 60 bars on 1m feeds, or fewer on slower TFs.
        bars_for_1h = 60 if self.cfg.timeframe in ("1m",) else 4
        change_1h = self.pct_change_window(bars_for_1h)
        if change_1h >= _ANTI_FOMO_PCT:
            self.log.info(
                "ANTI_FOMO: blocked BUY (1h move %+.2f%% ≥ %.1f%% — waiting for pullback)",
                change_1h, _ANTI_FOMO_PCT,
            )
            return True
        return False

    def _llm_confidence_floor(self) -> float:
        """Higher floor outside prime trading sessions and per-mode minimums."""
        base = self.cfg.signal_confidence_threshold
        mode_floor = {
            "scalping": 0.7,
            "day_trading": 0.65,
            "long_term": 0.7,
            "full_ai": 0.55,
        }.get(self.cfg.trading_mode, 0.65)
        floor = max(base, mode_floor)
        if not self.is_prime_session():
            floor = max(floor, 0.8)
        return floor

    def _eval_scheduled_condition(self, cond: Optional[str]) -> bool:
        if not cond:
            return True
        s = str(cond).strip().lower().replace(" ", "")
        rsi = self.calculate_rsi()
        try:
            if "rsi<" in s:
                thr = float(s.split("<", 1)[1])
                return rsi < thr
            if "rsi>" in s:
                thr = float(s.split(">", 1)[1])
                return rsi > thr
        except (ValueError, IndexError):
            return False
        return True

    def _maybe_scheduled_orders(self, price: float) -> None:
        rows = self.cfg.scheduled_orders or []
        if not rows or price <= 0:
            return
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        for k in list(self._scheduled_fired.keys()):
            if not k.endswith(today):
                self._scheduled_fired.pop(k, None)
        cal = self._calendar_constraints()
        if cal.get("pause_new_entries"):
            return
        if self._symbol_paused_by_calendar():
            return
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            tstr = str(row.get("time") or "")
            try:
                parts = tstr.split(":")
                h, m = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                continue
            if now.hour != h or now.minute != m:
                continue
            key = f"{idx}-{today}"
            if self._scheduled_fired.get(key):
                continue
            if not self._eval_scheduled_condition(row.get("condition")):
                continue
            typ = str(row.get("type") or "buy").lower()
            amt = float(row.get("amount") or 0)
            self._scheduled_fired[key] = True
            if typ == "buy" and self.position_qty == 0 and amt > 0:
                qty = round(amt / price, 6 if self.cfg.asset_type == "crypto" else 4)
                if qty > 0:
                    self.log.info("Scheduled BUY ~$%.2f qty=%.6f", amt, qty)
                    self.submit_order("BUY", qty)

    def _cancel_hermes_grid_orders(self) -> None:
        if DRY_RUN:
            return
        try:
            req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[self.symbol],
                limit=50,
            )
            orders = self._trading.get_orders(filter=req)
            for o in orders:
                cid = str(getattr(o, "client_order_id", None) or "")
                if cid.startswith("hmgrid"):
                    self._trading.cancel_order_by_id(o.id)
        except Exception as exc:  # noqa: BLE001
            self.log.debug("grid cancel: %s", exc)

    def _grid_sync_limit_orders(self, price: float) -> None:
        g = self.cfg.grid or {}
        lower = float(g.get("lower_price") or 0)
        upper = float(g.get("upper_price") or 0)
        nlines = int(g.get("grid_lines") or 10)
        usd_each = float(g.get("amount_per_grid") or 0)
        if lower <= 0 or upper <= lower or usd_each <= 0 or price <= 0:
            return
        step = (upper - lower) / max(1, nlines)
        levels = [
            round(lower + i * step, 6 if self.cfg.asset_type == "crypto" else 2)
            for i in range(nlines + 1)
        ]
        buys = [lv for lv in levels if lv < price * 0.999][:6]
        sells: list[float] = []
        if self.position_qty > 0 and self.entry_price:
            sells = [lv for lv in levels if lv > max(price, float(self.entry_price)) * 1.001][:6]
        self._cancel_hermes_grid_orders()
        dec = 6 if self.cfg.asset_type == "crypto" else 4
        for i, lv in enumerate(buys):
            q = round(usd_each / lv, dec)
            if q <= 0:
                continue
            self.submit_limit_order("BUY", q, lv, f"hmgrid-b{i}-{int(lv * 1000)}")
        for j, lv in enumerate(sells):
            q = round(usd_each / lv, dec)
            if self.position_qty > 0:
                q = min(q, self.position_qty)
            if q <= 0:
                continue
            self.submit_limit_order("SELL", q, lv, f"hmgrid-s{j}-{int(lv * 1000)}")

    async def _tick_dca_mode(self, kill_event: asyncio.Event, price: float) -> None:
        if kill_event.is_set():
            return
        cal = self._calendar_constraints()
        if cal.get("pause_new_entries"):
            self.check_exit_conditions()
            return
        cfg = self.cfg.dca or {}
        interval = _parse_duration_seconds(str(cfg.get("interval") or "4h"))
        amount = float(cfg.get("amount") or 0)
        max_pos = float(cfg.get("max_position") or 0)
        now = time.time()
        pos_usd = self.position_qty * price
        self._tick_count += 1
        if self._tick_count % 5 == 1:
            self.log.info(
                "DCA status price=%.4f pos_usd=%.2f / %.2f",
                price, pos_usd, max_pos,
            )
        if now - self._dca_last_ts < interval:
            self.check_exit_conditions()
            return
        if amount <= 0 or max_pos <= 0:
            self.check_exit_conditions()
            return
        if pos_usd >= max_pos - 1e-6:
            self.check_exit_conditions()
            return
        room = max(0.0, max_pos - pos_usd)
        buy_usd = min(amount * float(cal.get("size_mult") or 1.0), room)
        dec = 6 if self.cfg.asset_type == "crypto" else 4
        qty = round(buy_usd / price, dec)
        if qty <= 0:
            self.check_exit_conditions()
            return
        self._dca_last_ts = now
        acc = self.position_qty > 0
        self.log.info("DCA buy ~$%.2f qty=%.6f (accum=%s)", buy_usd, qty, acc)
        self.submit_order("BUY", qty, accumulate=acc)
        self.check_exit_conditions()

    async def _tick_grid_mode(self, kill_event: asyncio.Event, price: float) -> None:
        if kill_event.is_set():
            return
        self._tick_count += 1
        if (time.time() - self._grid_last_sync) >= 60.0:
            self._grid_sync_limit_orders(price)
            self._grid_last_sync = time.time()
        if self._tick_count % 5 == 1:
            self.log.info(
                "GRID status price=%.4f pos=%.6f session_pnl=%.2f",
                price, self.position_qty, self.grid_session_pnl,
            )
        self.check_exit_conditions()

    # ── Main tick ──────────────────────────────────────────────────────────────

    async def tick(self, kill_event: asyncio.Event) -> None:
        if kill_event.is_set() or self.paused_manually:
            return
        if not self.is_market_open():
            return
        if not self.check_daily_limits():
            return

        # Portfolio-level kill: risk manager can veto trading entirely.
        if self.risk_manager is not None:
            try:
                pv = self._get_portfolio_value()
                if not self.risk_manager.can_trade(pv):
                    self.log.warning("Risk manager blocked trading (pv=%.2f)", pv)
                    self.check_exit_conditions()
                    return
            except Exception as exc:
                self.log.debug("risk_manager.can_trade failed: %s", exc)

        # Sync latest price history from shared DataFeed
        self._sync_prices_from_feed()
        price = self.get_current_price()
        if price <= 0:
            return

        if (time.time() - self._regime_check_ts) > 300:
            await self._detect_regime_for_tick()
            self._regime_check_ts = time.time()

        if self._dca_enabled():
            await self._tick_dca_mode(kill_event, price)
            return
        if self._grid_enabled():
            await self._tick_grid_mode(kill_event, price)
            return

        self._tick_count += 1
        self._maybe_scheduled_orders(price)

        signal = self.get_signal()

        # Log status every 5 ticks so we can see agents are alive
        if self._tick_count % 5 == 1:
            self.log.info(
                "STATUS  price=$%-10.4f  RSI=%-5.1f  signal=%-4s conf=%.2f  pos=%.6f  regime=%s  session=%.2f",
                price, self.calculate_rsi(), signal.direction, signal.confidence,
                self.position_qty, self.last_regime, self.get_session_multiplier(),
            )
        else:
            self.log.debug(
                "signal=%s conf=%.2f  %s",
                signal.direction, signal.confidence, signal.reason,
            )

        if signal.confidence < self.cfg.signal_confidence_threshold:
            self.check_exit_conditions()
            return

        # Apply correlation filter BEFORE LLM so confidence going into the LLM
        # already reflects market-leader headwind/tailwind.
        signal = await self._apply_correlation_filter(signal)

        if signal.confidence < self.cfg.signal_confidence_threshold:
            self.log.info("Correlation filter dropped confidence below threshold")
            self.check_exit_conditions()
            return

        # Hard-block trading INTO an unfavourable regime.
        if signal.direction == "BUY" and self.last_regime in ("crash", "trending_down"):
            self.log.info("REGIME_BLOCK: skipping BUY in regime=%s", self.last_regime)
            self.check_exit_conditions()
            return

        # Anti-FOMO: don't chase fresh 1h pumps.
        if self._anti_fomo_block(signal):
            self.check_exit_conditions()
            return

        final_signal = await self._apply_llm_if_enabled(signal)
        final_signal = self.custom_signal_override(final_signal)
        final_action = final_signal.direction

        # Higher confidence floor for actually opening positions.
        if final_action == "BUY" and final_signal.confidence < self._llm_confidence_floor():
            self.log.info(
                "BUY rejected: conf=%.2f < floor=%.2f (mode=%s, session=%.2f)",
                final_signal.confidence, self._llm_confidence_floor(),
                self.cfg.trading_mode, self.get_session_multiplier(),
            )
            self.check_exit_conditions()
            return

        if final_action == "BUY" and self.position_qty == 0:
            cal = self._calendar_constraints()
            if cal.get("pause_new_entries"):
                self.log.info("Calendar: pause new entries (macro window)")
                self.check_exit_conditions()
                return
            if self._symbol_paused_by_calendar():
                self.log.info("Calendar: symbol paused (earnings / event)")
                self.check_exit_conditions()
                return
            qty = self.calculate_qty(price)
            if qty > 0:
                self.log.info(
                    "DECISION BUY  %s  qty=%.6f @ $%.4f  RSI=%.1f  conf=%.2f  regime=%s",
                    self.symbol, qty, price, self.calculate_rsi(),
                    final_signal.confidence, self.last_regime,
                )
                self.submit_order("BUY", qty)
        elif final_action == "SELL" and self.position_qty > 0:
            self.log.info(
                "DECISION SELL %s  qty=%.6f @ $%.4f  RSI=%.1f  conf=%.2f",
                self.symbol, self.position_qty, price, self.calculate_rsi(), final_signal.confidence,
            )
            self.submit_order("SELL", self.position_qty, exit_reason="signal")

        self.check_exit_conditions()

    async def evaluate_once(self) -> dict:
        """Run a single tick's worth of evaluation and return a debug dict.

        Used by `python hermes.py --test-one BTC/USD` to get a full trace
        of what would happen on the next decision without actually trading.
        """
        self._sync_prices_from_feed()
        price = self.get_current_price()
        signal = self.get_signal()
        await self._detect_regime_for_tick()
        ctx = await self._get_cached_market_context()
        sig_after_corr = await self._apply_correlation_filter(signal)
        anti_fomo = self._anti_fomo_block(sig_after_corr)
        # Don't actually call the LLM unless explicitly enabled.
        return {
            "symbol": self.symbol,
            "asset_type": self.cfg.asset_type,
            "trading_mode": self.cfg.trading_mode,
            "price": price,
            "rsi": self.calculate_rsi(),
            "macd": self.calculate_macd(),
            "atr": self.calculate_atr(14),
            "atr_normal": self.calculate_atr_average(14, 50),
            "rule_signal": {
                "direction": signal.direction,
                "confidence": signal.confidence,
                "reason": signal.reason,
            },
            "post_correlation_signal": {
                "direction": sig_after_corr.direction,
                "confidence": sig_after_corr.confidence,
                "reason": sig_after_corr.reason,
            },
            "regime": self.last_regime,
            "regime_details": self.last_regime_details,
            "session_multiplier": self.get_session_multiplier(),
            "is_prime_session": self.is_prime_session(),
            "anti_fomo_block": anti_fomo,
            "qty_if_buy": self.calculate_qty(price) if price else 0.0,
            "context_keys": sorted(ctx.keys()) if ctx else [],
        }

    def _llm_rate_limit_allows(self) -> bool:
        ch = time.gmtime().tm_hour
        if ch != self._llm_hour:
            self._llm_hour = ch
            self.llm_calls_this_hour = 0
        return self.llm_calls_this_hour < self.cfg.llm_max_calls_per_hour

    def _llm_audit_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "logs" / "llm_audit.log"

    def _append_llm_audit(self, meta: dict) -> None:
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "agent": self.name, **meta}, default=str) + "\n"
        p = self._llm_audit_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as exc:
            self.log.debug("llm audit write failed: %s", exc)

    async def _apply_llm_if_enabled(self, signal: SignalResult) -> SignalResult:
        if not self.cfg.llm_enabled or signal.confidence < self.cfg.llm_trigger_threshold:
            return signal
        if not self._llm_rate_limit_allows():
            self.log.debug("%s: LLM skipped (hourly cap %d)", self.name, self.cfg.llm_max_calls_per_hour)
            return signal
        from core.llm_advisor import get_llm_advisor

        advisor = get_llm_advisor()
        if not advisor.is_configured():
            return signal
        try:
            new_sig, meta = await advisor.review_signal(self, signal)
            if not meta.get("skipped"):
                self.llm_calls_this_hour += 1
            self.log.info(
                "LLM | %s | %s → %s | model=%s | usage=%s",
                self.name,
                signal.direction,
                new_sig.direction,
                meta.get("model", "?"),
                meta.get("usage", {}),
            )
            if not meta.get("skipped") and not meta.get("error"):
                self._append_llm_audit(
                    {
                        "symbol": self.symbol,
                        "in": signal.direction,
                        "out": new_sig.direction,
                        "model": meta.get("model"),
                        "usage": meta.get("usage"),
                    }
                )
            if meta.get("error"):
                self.log.warning("LLM error (rule signal kept): %s", meta.get("error"))
            return new_sig
        except Exception as exc:
            self.log.warning("LLM review failed, using rules: %s", exc)
            return signal

    # ── Overridable ────────────────────────────────────────────────────────────

    def get_llm_context(self) -> str:
        return ""

    def custom_signal_override(self, signal: SignalResult) -> SignalResult:
        return signal

    def reload_config(self, new_cfg: AgentConfig) -> None:
        self.cfg = new_cfg
        self.log.info("Config reloaded")
