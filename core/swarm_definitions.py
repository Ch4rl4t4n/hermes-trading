from __future__ import annotations

import logging

log = logging.getLogger(__name__)

DEFAULT_SWARMS = [
    {
        "swarm_name": "orchestra",
        "display_name": "Orchestra",
        "icon": "🎼",
        "description": "Master coordinator - routes tasks to other swarms",
        "color": "oklch(0.72 0.18 295)",
        "agents": [
            {
                "agent_id": "orchestra-001",
                "name": "Task Router",
                "capabilities": ["routing", "orchestration", "planning"],
                "agent_type": "orchestrator",
            },
        ],
    },
    {
        "swarm_name": "trading",
        "display_name": "Trade Execution",
        "icon": "📈",
        "description": "Executes and monitors trading strategies",
        "color": "oklch(0.78 0.16 155)",
        "agents": [
            {
                "agent_id": "trading-001",
                "name": "BTC Momentum Agent",
                "capabilities": ["trading", "momentum", "crypto"],
                "agent_type": "worker",
            },
            {
                "agent_id": "trading-002",
                "name": "Risk Manager",
                "capabilities": ["trading", "risk", "portfolio"],
                "agent_type": "lead",
            },
        ],
    },
    {
        "swarm_name": "intelligence",
        "display_name": "Intelligence Stalker",
        "icon": "🔍",
        "description": "Market research, news analysis, trend detection",
        "color": "oklch(0.78 0.14 75)",
        "agents": [
            {
                "agent_id": "intel-001",
                "name": "News Stalker",
                "capabilities": ["research", "news", "analysis"],
                "agent_type": "worker",
            },
            {
                "agent_id": "intel-002",
                "name": "Trend Detector",
                "capabilities": ["research", "trends", "social"],
                "agent_type": "worker",
            },
        ],
    },
    {
        "swarm_name": "marketing",
        "display_name": "Marketing & Growth",
        "icon": "📣",
        "description": "Social media, content creation, SEO, growth",
        "color": "oklch(0.72 0.18 15)",
        "agents": [
            {
                "agent_id": "mkt-001",
                "name": "Social Media Manager",
                "capabilities": ["marketing", "social", "content"],
                "agent_type": "lead",
            },
            {
                "agent_id": "mkt-002",
                "name": "SEO Optimizer",
                "capabilities": ["marketing", "seo", "content"],
                "agent_type": "worker",
            },
        ],
    },
    {
        "swarm_name": "maintenance",
        "display_name": "Infrastructure",
        "icon": "🔧",
        "description": "Web/app maintenance, monitoring, security",
        "color": "oklch(0.65 0.12 220)",
        "agents": [
            {
                "agent_id": "infra-001",
                "name": "Monitoring Guardian",
                "capabilities": ["maintenance", "monitoring", "alerts"],
                "agent_type": "lead",
            },
            {
                "agent_id": "infra-002",
                "name": "Security Auditor",
                "capabilities": ["maintenance", "security", "audit"],
                "agent_type": "worker",
            },
        ],
    },
]


def seed_default_swarms(queue_manager) -> int:
    total = 0
    for swarm in DEFAULT_SWARMS:
        for agent in swarm["agents"]:
            if queue_manager.get_agent(agent["agent_id"]):
                continue
            queue_manager.register_agent(
                agent_id=agent["agent_id"],
                name=agent["name"],
                swarm=swarm["swarm_name"],
                capabilities=agent["capabilities"],
                config={"agent_type": agent["agent_type"]},
            )
            total += 1
    log.info("[Registry] Seeded %s agents", total)
    return total
