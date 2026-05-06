from agents.strategies.volatile import VolatileStrategy
from agents.base_agent import AgentConfig


class SOLAgent(VolatileStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: volatile, 15m. SOL: high beta vs BTC, sensitive to L1 stability, DePIN/NFT/validator narratives, and outage incidents. "
            "Regime: whipsaw risk—RSI can oscillate fast; false breakouts around network stress or concentrated unlocks. "
            "Favor discipline: wide bands exist because noise is high; respect stops and liquidity crunches."
        )
