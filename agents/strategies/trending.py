from agents.base_agent import BaseAgent, AgentConfig, SignalResult
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.data_feed import DataFeed


class TrendingStrategy(BaseAgent):
    """Category 2 — trending swing (≈3–10d). **ETH/USD** (balanced: mean reversion + breakouts), **NVDA**, **AMD**.

    - 1h candles; RSI 14, 35/65; SL 4 %, TP 10 %, trailing after +5 %
    - MACD histogram crossover (neg→pos / pos→neg) adds +0.15 confidence when aligned with RSI direction
    """

    def __init__(self, config: AgentConfig, feed: Optional["DataFeed"] = None):
        super().__init__(config, feed=feed)
        self._prev_macd_hist: float = 0.0

    def get_signal(self) -> SignalResult:
        return self.get_rule_signal()

    def get_rule_signal(self) -> SignalResult:
        signal = super().get_rule_signal()

        _, _, histogram = self.calculate_macd()

        crossed_bullish = self._prev_macd_hist < 0 and histogram > 0
        crossed_bearish = self._prev_macd_hist > 0 and histogram < 0
        self._prev_macd_hist = histogram

        if crossed_bullish and signal.direction == "BUY":
            return SignalResult(
                direction="BUY",
                confidence=round(min(signal.confidence + 0.15, 1.0), 3),
                reason=signal.reason + " [MACD_CROSS_BULL]",
            )
        if crossed_bearish and signal.direction == "SELL":
            return SignalResult(
                direction="SELL",
                confidence=round(min(signal.confidence + 0.15, 1.0), 3),
                reason=signal.reason + " [MACD_CROSS_BEAR]",
            )

        return signal
