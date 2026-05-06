from agents.base_agent import BaseAgent, AgentConfig, SignalResult
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.data_feed import DataFeed

_ATR_PERIOD = 14
_ATR_RISK_PCT = 0.01    # risk 1% of portfolio per trade
_ATR_MULTIPLIER = 2.0   # stop distance = 2 × ATR


class VolatileStrategy(BaseAgent):
    """Category 3 — volatile swing (≈1–7d). **SOL/USD** (momentum + breakouts), **TSLA** (earnings / gaps), **USO** (geopolitics).

    - 15m candles; RSI 14, 25/75; SL 5 %, TP 12 %, trailing after +6 %
    - Optional ATR-based sizing when `atr_position_sizing: true` (smaller size when ATR is high)
    """

    def __init__(self, config: AgentConfig, feed: Optional["DataFeed"] = None):
        super().__init__(config, feed=feed)

    def get_signal(self) -> SignalResult:
        return self.get_rule_signal()

    def _calculate_atr(self) -> float:
        if len(self.prices) < _ATR_PERIOD + 1:
            return 0.0
        closes = self.prices[-(_ATR_PERIOD + 1):]
        ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        return sum(ranges) / len(ranges)

    def calculate_qty(self, price: float) -> float:
        if not self.cfg.atr_position_sizing:
            return super().calculate_qty(price)

        atr = self._calculate_atr()
        if atr <= 0 or price <= 0:
            return super().calculate_qty(price)

        portfolio = self._get_portfolio_value()
        risk_usd = portfolio * _ATR_RISK_PCT
        qty_by_atr = risk_usd / (atr * _ATR_MULTIPLIER)

        max_qty_by_cap = (portfolio * self.cfg.max_position_pct) / price
        qty = min(qty_by_atr, max_qty_by_cap)

        decimals = 6 if self.cfg.asset_type == "crypto" else 4
        return round(qty, decimals)
