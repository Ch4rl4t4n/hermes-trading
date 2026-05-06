from agents.base_agent import BaseAgent, AgentConfig


class AVAXAgent(BaseAgent):
    def __init__(self, config: AgentConfig, feed=None):
        super().__init__(config, feed=feed)
