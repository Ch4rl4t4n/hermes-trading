from agents.strategies.volatile import VolatileStrategy
from agents.base_agent import AgentConfig


class TSLAAgent(VolatileStrategy):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)

    def get_llm_context(self) -> str:
        return (
            "Strategy: volatile, 15m. TSLA: idiosyncratic and headline-heavy (deliveries, FSD, China, margins, key-person risk). "
            "Regime: can ignore broad market RSI; gap risk around prints and social/news catalysts. "
            "15m technicals are noisy—treat fast reversals and halt-like gaps as first-class risk."
        )
