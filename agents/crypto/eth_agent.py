from agents.strategies.trending import TrendingStrategy
from agents.base_agent import AgentConfig


class ETHAgent(TrendingStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: trending 1h (balanced swing: mean reversion + breakouts). ETH: beta to BTC, L1/DeFi/staking, network upgrades. "
            "Key drivers: L2/rollup flow, app TVL, institutional products."
        )
