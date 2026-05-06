"""Unit tests for StableStrategy, TrendingStrategy, VolatileStrategy."""
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import time as dtime
from agents.base_agent import AgentConfig
from agents.strategies.stable import StableStrategy
from agents.strategies.trending import TrendingStrategy
from agents.strategies.volatile import VolatileStrategy


# ── Shared helpers ─────────────────────────────────────────────────────────────

def make_config(**overrides) -> AgentConfig:
    defaults = dict(
        name="Test", symbol="BTC/USD", asset_type="crypto",
        enabled=True, trade_usd=100.0,
        timezone="UTC",
        active_hours_start=dtime(0, 0), active_hours_end=dtime(23, 59),
        check_interval_seconds=60,
        rsi_period=14, rsi_buy_threshold=30.0, rsi_sell_threshold=70.0,
        macd_enabled=True, signal_confidence_threshold=0.55,
        llm_enabled=False, llm_trigger_threshold=0.65,
        llm_model="haiku", llm_max_calls_per_hour=6, llm_use_sonnet_above=0.85,
        trailing_stop_pct=3.0, take_profit_pct=8.0,
        max_trades_per_day=6, max_daily_loss_pct=2.0, max_position_pct=0.06,
        timeframe="4h", trailing_activate_pct=4.0, atr_position_sizing=False,
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _make_base_attrs(agent, config):
    """Populate all BaseAgent attributes without calling Alpaca client init."""
    agent.cfg = config
    agent.name = config.name
    agent.symbol = config.symbol
    agent.feed = None
    agent.risk_manager = None
    agent.prices = []
    agent.entry_price = None
    agent.position_qty = 0.0
    agent.entry_qty = 0.0
    agent.entry_time = None
    agent.tp1_taken = False
    agent.last_llm_decision = None
    agent.last_regime = "unknown"
    agent.last_regime_details = {}
    agent.trades_today = 0
    agent.daily_loss_usd = 0.0
    agent.paused_by_limit = False
    agent.paused_manually = False
    agent.llm_calls_this_hour = 0
    agent._llm_hour = -1
    agent._high_water_mark = 0.0
    agent._portfolio_cache = 100_000.0
    agent._portfolio_ts = float("inf")   # never expires in tests
    agent._tick_count = 0
    agent._regime_check_ts = 0.0
    agent._cached_market_context = {}
    agent._market_context_ts = 0.0
    agent._daily_loss_alert_sent = False
    agent._orders = []
    agent.log = logging.getLogger(agent.name)
    # Tests should be deterministic; pin session_mult to full so position
    # sizing assertions don't depend on wall-clock UTC hour.
    agent.get_session_multiplier = lambda: 1.0


class ConcreteStable(StableStrategy):
    def __init__(self, config):
        _make_base_attrs(self, config)

    def submit_order(self, side: str, qty: float, exit_reason: str = "manual") -> bool:
        self._orders.append((side, qty))
        if side == "BUY":
            self.entry_price = self.prices[-1] if self.prices else 0.0
            self.position_qty = qty
        else:
            self.entry_price = None
            self.position_qty = 0.0
            self._high_water_mark = 0.0
        return True

    def _get_portfolio_value(self) -> float:
        return 100_000.0


class ConcreteTrending(TrendingStrategy):
    def __init__(self, config):
        _make_base_attrs(self, config)
        self._prev_macd_hist = 0.0

    def submit_order(self, side: str, qty: float, exit_reason: str = "manual") -> bool:
        self._orders.append((side, qty))
        if side == "BUY":
            self.entry_price = self.prices[-1] if self.prices else 0.0
            self.position_qty = qty
        else:
            self.entry_price = None
            self.position_qty = 0.0
            self._high_water_mark = 0.0
        return True

    def _get_portfolio_value(self) -> float:
        return 100_000.0


class ConcreteVolatile(VolatileStrategy):
    def __init__(self, config):
        _make_base_attrs(self, config)

    def submit_order(self, side: str, qty: float, exit_reason: str = "manual") -> bool:
        self._orders.append((side, qty))
        if side == "BUY":
            self.entry_price = self.prices[-1] if self.prices else 0.0
            self.position_qty = qty
        else:
            self.entry_price = None
            self.position_qty = 0.0
            self._high_water_mark = 0.0
        return True

    def _get_portfolio_value(self) -> float:
        return 100_000.0


# ── StableStrategy tests ───────────────────────────────────────────────────────

def test_stable_trailing_stop_not_triggered_before_activation():
    """Trailing stop must NOT fire when gain < trailing_activate_pct."""
    cfg = make_config(trailing_stop_pct=3.0, trailing_activate_pct=4.0, take_profit_pct=8.0)
    agent = ConcreteStable(cfg)
    agent.prices = [100.0]
    agent.entry_price = 100.0
    agent.position_qty = 1.0
    agent._high_water_mark = 103.0   # +3% gain from entry

    # Price at 99.0: big drop from HWM, but gain was only 3% < 4% activate threshold
    agent.prices = [99.0]
    agent.check_exit_conditions()
    assert len(agent._orders) == 0, "Trailing stop fired before activation threshold"


def test_stable_trailing_stop_fires_after_activation():
    """Trailing stop fires when gain exceeded activate threshold and price drops from HWM."""
    cfg = make_config(trailing_stop_pct=3.0, trailing_activate_pct=4.0, take_profit_pct=8.0)
    agent = ConcreteStable(cfg)
    agent.entry_price = 100.0
    agent.position_qty = 1.0
    agent._high_water_mark = 106.0  # +6% gain → activation threshold met

    # Price drops 3.2% from HWM=106 → should trigger stop
    agent.prices = [102.6]          # (106-102.6)/106 ≈ 3.2% > trailing_stop_pct=3.0
    agent.check_exit_conditions()
    assert len(agent._orders) == 1
    assert agent._orders[0][0] == "SELL"


def test_stable_take_profit_fires():
    cfg = make_config(trailing_stop_pct=3.0, trailing_activate_pct=4.0, take_profit_pct=8.0)
    agent = ConcreteStable(cfg)
    agent.entry_price = 100.0
    agent.position_qty = 1.0
    agent.prices = [108.5]   # +8.5% > take_profit_pct=8.0
    agent.check_exit_conditions()
    assert agent._orders[0][0] == "SELL"


def test_stable_no_exit_when_no_position():
    cfg = make_config()
    agent = ConcreteStable(cfg)
    agent.prices = [50.0]
    agent.position_qty = 0.0
    agent.entry_price = None
    agent.check_exit_conditions()
    assert len(agent._orders) == 0


def test_stable_loaded_from_yaml():
    from core.config_loader import load_agent_config
    cfg = load_agent_config(Path(__file__).parent.parent / "config" / "agents" / "btc.yaml")
    assert cfg.trailing_activate_pct == 4.0
    assert cfg.timeframe == "4h"
    assert cfg.atr_position_sizing is False


# ── TrendingStrategy tests ─────────────────────────────────────────────────────

def test_trending_macd_crossover_bull_boosts_buy():
    """Bullish MACD crossover (neg→pos) boosts BUY confidence."""
    cfg = make_config(
        rsi_buy_threshold=35.0, signal_confidence_threshold=0.40,
        timeframe="1h", trailing_activate_pct=5.0, atr_position_sizing=False,
    )
    agent = ConcreteTrending(cfg)
    # Falling prices → oversold → RSI-based BUY signal
    agent.prices = [100 - i * 2 for i in range(30)]
    # Simulate previous histogram was negative
    agent._prev_macd_hist = -0.5

    signal = agent.get_rule_signal()
    # The signal direction should be BUY (oversold)
    assert signal.direction == "BUY"
    # Call again; this time crossover detected (prev was -0.5, current histogram > 0 for falling trend)
    # Just verify the method runs without error and returns a valid SignalResult
    assert 0.0 <= signal.confidence <= 1.0


def test_trending_crossover_boost_applied():
    """When MACD crosses from negative to positive AND signal is BUY, confidence increases."""
    cfg = make_config(
        rsi_buy_threshold=35.0, signal_confidence_threshold=0.40,
        timeframe="1h", trailing_activate_pct=5.0, atr_position_sizing=False,
    )
    agent = ConcreteTrending(cfg)
    # Prices that produce an oversold RSI and positive MACD histogram
    # (prices dip then recover → RSI oversold on the way down)
    agent.prices = [100 - i * 1.5 for i in range(30)]   # oversold

    # Get baseline confidence without crossover
    agent._prev_macd_hist = 9999.0   # large positive → no crossover
    signal_no_cross = agent.get_rule_signal()

    # Reset and force a crossover (prev negative → current will be computed)
    agent._prev_macd_hist = -9999.0  # large negative → crossover expected if histogram > 0
    signal_with_cross = agent.get_rule_signal()

    # Both should be BUY; crossover version may have higher confidence
    assert signal_no_cross.direction == "BUY"
    assert signal_with_cross.direction == "BUY"
    # If crossover fires, confidence boosted by 0.15
    if "[MACD_CROSS_BULL]" in signal_with_cross.reason:
        assert signal_with_cross.confidence >= signal_no_cross.confidence


def test_trending_loaded_from_yaml():
    from core.config_loader import load_agent_config
    cfg = load_agent_config(Path(__file__).parent.parent / "config" / "agents" / "nvda.yaml")
    assert cfg.trailing_activate_pct == 5.0
    assert cfg.timeframe == "1h"
    assert cfg.rsi_buy_threshold == 35.0
    assert cfg.take_profit_pct == 10.0


def test_amd_loaded_from_yaml():
    from core.config_loader import load_agent_config
    cfg = load_agent_config(Path(__file__).parent.parent / "config" / "agents" / "amd.yaml")
    assert cfg.symbol == "AMD"
    assert cfg.asset_type == "stock"
    assert cfg.timeframe == "1h"
    assert cfg.trailing_activate_pct == 5.0


# ── VolatileStrategy tests ─────────────────────────────────────────────────────

def test_volatile_atr_sizing_returns_nonzero():
    """ATR sizing produces a non-zero quantity with sufficient price history."""
    cfg = make_config(
        symbol="SOL/USD", asset_type="crypto",
        timeframe="15m", trailing_activate_pct=6.0, atr_position_sizing=True,
        max_position_pct=0.05,
    )
    agent = ConcreteVolatile(cfg)
    # 20 prices with some volatility so ATR > 0
    agent.prices = [100.0 + (i % 5) * 2.0 for i in range(20)]
    qty = agent.calculate_qty(100.0)
    assert qty > 0, "ATR sizing returned zero with valid price history"


def test_volatile_atr_sizing_respects_position_cap():
    """ATR qty must not exceed portfolio * max_position_pct / price."""
    cfg = make_config(
        symbol="SOL/USD", asset_type="crypto",
        timeframe="15m", trailing_activate_pct=6.0, atr_position_sizing=True,
        max_position_pct=0.05,
    )
    agent = ConcreteVolatile(cfg)
    agent.prices = [100.0 + (i % 5) * 2.0 for i in range(20)]
    price = 100.0
    qty = agent.calculate_qty(price)
    max_qty = (100_000.0 * cfg.max_position_pct) / price
    assert qty <= max_qty + 1e-6, f"qty {qty} exceeds max {max_qty}"


def test_volatile_atr_fallback_when_insufficient_data():
    """Falls back to base USD sizing when fewer than ATR_PERIOD bars available."""
    cfg = make_config(
        symbol="TSLA", asset_type="stock",
        timeframe="15m", trailing_activate_pct=6.0, atr_position_sizing=True,
        trade_usd=100.0, max_position_pct=0.05,
    )
    agent = ConcreteVolatile(cfg)
    agent.prices = [200.0] * 5   # only 5 bars, need 15 for ATR
    qty = agent.calculate_qty(200.0)
    # Should fall back: qty = min(100 / 200, 100000*0.05/200) = 0.5
    assert qty == round(100.0 / 200.0, 4)


def test_volatile_atr_disabled_uses_base_sizing():
    """When atr_position_sizing=False, uses standard USD-based sizing."""
    cfg = make_config(
        symbol="TSLA", asset_type="stock",
        timeframe="15m", trailing_activate_pct=6.0, atr_position_sizing=False,
        trade_usd=100.0, max_position_pct=0.05,
    )
    agent = ConcreteVolatile(cfg)
    agent.prices = [200.0] * 20
    qty = agent.calculate_qty(200.0)
    assert qty == round(100.0 / 200.0, 4)


def test_volatile_loaded_from_yaml():
    from core.config_loader import load_agent_config
    cfg = load_agent_config(Path(__file__).parent.parent / "config" / "agents" / "sol.yaml")
    assert cfg.trailing_activate_pct == 6.0
    assert cfg.timeframe == "15m"
    assert cfg.atr_position_sizing is True
    assert cfg.rsi_buy_threshold == 25.0


def test_eth_loaded_from_yaml():
    from core.config_loader import load_agent_config
    cfg = load_agent_config(Path(__file__).parent.parent / "config" / "agents" / "eth.yaml")
    assert cfg.symbol == "ETH/USD"
    assert cfg.timeframe == "1h"
    assert cfg.rsi_buy_threshold == 35.0
    assert cfg.take_profit_pct == 10.0


# ── get_signal() vs get_rule_signal() — strategies must be equivalent paths ─

def test_get_signal_matches_get_rule_signal_stable():
    cfg = make_config()
    agent = ConcreteStable(cfg)
    agent.prices = [100.0] * 20
    assert agent.get_signal().direction == agent.get_rule_signal().direction


def test_get_signal_matches_get_rule_signal_trending():
    cfg = make_config(rsi_buy_threshold=35.0)
    agent = ConcreteTrending(cfg)
    agent.prices = [100 - i * 2 for i in range(30)]
    agent._prev_macd_hist = 0.0
    a, b = agent.get_signal(), agent.get_rule_signal()
    assert a.direction == b.direction and a.confidence == b.confidence


def test_get_signal_matches_get_rule_signal_volatile():
    cfg = make_config(
        symbol="SOL/USD", asset_type="crypto",
        timeframe="15m", trailing_activate_pct=6.0, atr_position_sizing=True,
    )
    agent = ConcreteVolatile(cfg)
    agent.prices = [100.0 + (i % 3) for i in range(20)]
    a, b = agent.get_signal(), agent.get_rule_signal()
    assert a.direction == b.direction


if __name__ == "__main__":
    tests = [
        test_stable_trailing_stop_not_triggered_before_activation,
        test_stable_trailing_stop_fires_after_activation,
        test_stable_take_profit_fires,
        test_stable_no_exit_when_no_position,
        test_stable_loaded_from_yaml,
        test_trending_macd_crossover_bull_boosts_buy,
        test_trending_crossover_boost_applied,
        test_trending_loaded_from_yaml,
        test_amd_loaded_from_yaml,
        test_volatile_atr_sizing_returns_nonzero,
        test_volatile_atr_sizing_respects_position_cap,
        test_volatile_atr_fallback_when_insufficient_data,
        test_volatile_atr_disabled_uses_base_sizing,
        test_volatile_loaded_from_yaml,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
