from agents.strategies.trending import TrendingStrategy
from agents.base_agent import AgentConfig


class NVDAAgent(TrendingStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: trending, 1h. NVDA: high-beta large-cap, headline-driven (AI spend, data center, guidance, Geopolitics/China export curbs on accelerators). "
            "Regime: momentum can persist beyond typical RSI 'overbought'; mean-reversion signals misfire in one-way AI cycles. "
            "Watch: hyperscaler capex, competition (AMD, custom ASICs), and broad market (QQQ) stress."
        )
