from agents.strategies.stable import StableStrategy
from agents.base_agent import AgentConfig


class BTCAgent(StableStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Category 1 stable, 4h, conservative trend-following. "
            "BTC: macro bellwether—Fed, ETF flows, halving, on-chain, NDX risk correlation."
        )
