from typing import Optional, TYPE_CHECKING
from agents.base_agent import BaseAgent, AgentConfig
if TYPE_CHECKING:
    from core.data_feed import DataFeed
    from core.risk_manager import RiskManager
from agents.crypto.btc_agent import BTCAgent
from agents.crypto.eth_agent import ETHAgent
from agents.crypto.sol_agent import SOLAgent
from agents.stocks.nvda_agent import NVDAAgent
from agents.stocks.tsla_agent import TSLAAgent
from agents.stocks.amd_agent import AMDAgent
from agents.commodities.gld_agent import GLDAgent
from agents.commodities.uso_agent import USOAgent

_REGISTRY: dict[str, type[BaseAgent]] = {
    "BTC/USD": BTCAgent,
    "ETH/USD": ETHAgent,
    "SOL/USD": SOLAgent,
    "NVDA":    NVDAAgent,
    "TSLA":    TSLAAgent,
    "AMD":     AMDAgent,
    "GLD":     GLDAgent,
    "USO":     USOAgent,
}


def create_agent(
    config: AgentConfig,
    feed: Optional["DataFeed"] = None,
    risk_manager: Optional["RiskManager"] = None,
) -> BaseAgent:
    cls = _REGISTRY.get(config.symbol)
    if cls is None:
        raise ValueError(f"No agent class registered for symbol '{config.symbol}'")
    # All concrete strategy classes accept (config, feed) — they call super().__init__
    # which then forwards to BaseAgent. We attach the risk_manager after construction
    # to avoid having to update every agent class signature.
    agent = cls(config, feed=feed)
    if risk_manager is not None:
        agent.risk_manager = risk_manager
    return agent
