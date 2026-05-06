from agents.strategies.volatile import VolatileStrategy
from agents.base_agent import AgentConfig


class USOAgent(VolatileStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: volatile, 15m. USO (oil): driven by OPEC+ supply, inventories, Middle East/marine risk, and USD. "
            "Regime: gap risk on Sunday opens and on inventory prints; ATR/short timeframes are deliberately wide. "
            "Macro shocks (sanctions, SPR, demand fears) can invalidate local mean-reversion signals."
        )
