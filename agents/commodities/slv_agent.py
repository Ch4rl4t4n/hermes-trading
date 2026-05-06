from agents.base_agent import BaseAgent, AgentConfig


class SLVAgent(BaseAgent):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)
