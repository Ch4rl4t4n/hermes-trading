from agents.strategies.trending import TrendingStrategy
from agents.base_agent import AgentConfig


class AMDAgent(TrendingStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: trending, 1h. AMD: trades on share gains vs INTC, MI-series AI GPU narrative, and data-center GPU competition vs NVDA. "
            "Regime: often lags or amplifies semis/NDX; earnings gaps dominate technicals. "
            "Earnings, guidance, and China restrictions can override short-term MACD/RSI alignment."
        )
