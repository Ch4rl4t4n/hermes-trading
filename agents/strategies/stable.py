from agents.base_agent import BaseAgent, AgentConfig, SignalResult
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.data_feed import DataFeed


class StableStrategy(BaseAgent):
    """Category 1 — stable swing (≈5–15d). Assets: **BTC/USD** (conservative trend-following), **GLD** (macro hedge).

    - 4h candles, check aligned to 4h bar cadence
    - RSI 14, oversold=30 / overbought=70
    - SL 3 %, TP 8 %, trailing after +4 %
    """

    def __init__(self, config: AgentConfig, feed: Optional["DataFeed"] = None):
        super().__init__(config, feed=feed)

    def get_signal(self) -> SignalResult:
        return self.get_rule_signal()
