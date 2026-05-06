from agents.strategies.stable import StableStrategy
from agents.base_agent import AgentConfig


class GLDAgent(StableStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: stable, 4h. GLD (gold) proxy: real yields and DXY often dominate over intraday oscillators. "
            "Regime: bid on systemic fear/flight to quality; headwind when USD and yields rise together. "
            "Respect that RSI can stay stretched in long trends—avoid fading strong macro trends without confirmation."
        )
