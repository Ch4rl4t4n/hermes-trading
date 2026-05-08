"""
Hermes Task Router — capability + load + swarm-preference scoring.

Score model (higher = better):
    base                         = 10
    capability_match (per cap)   = +10
    swarm_preference_match       = +5
    agent_idle                   = +3
    orchestrator_for_routing     = +20
    priority_bonus (1-10)        = +priority
    load_penalty                 = -2 * active_tasks
    type_bonus_for_orchestrator  = +20  (when task_type == 'routing')

Records every decision into Postgres `routing_decisions` (audit trail).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

try:
    from core.queue_manager import queue_manager
    from core.swarm_registry import get_engine, swarm_registry
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from hermes.core.queue_manager import queue_manager
    from hermes.core.swarm_registry import get_engine, swarm_registry

log = logging.getLogger(__name__)

ROUTING_LOG_KEY = "hermes:routing:log"
ROUTING_LOG_LIMIT = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRouter:
    """Intelligent dispatcher for the Orchestra swarm."""

    # ── Public API ────────────────────────────────────────────────────────
    def find_best_agent(
        self,
        required_capabilities: list[str] | None = None,
        preferred_swarm: str | None = None,
        task_type: str | None = None,
        priority: int = 5,
    ) -> dict[str, Any] | None:
        agents = swarm_registry.list_agents(alive_only=False)
        candidates: list[tuple[int, dict[str, Any]]] = []
        required = list(required_capabilities or [])

        for agent in agents:
            if not agent.get("alive"):
                continue
            if agent.get("status") not in ("idle", "running"):
                continue

            caps = agent.get("capabilities") or []
            if isinstance(caps, str):
                try:
                    caps = json.loads(caps)
                except (TypeError, ValueError, json.JSONDecodeError):
                    caps = []
            if not isinstance(caps, list):
                caps = []

            score = 10  # base
            if required:
                matched = sum(1 for cap in required if cap in caps)
                if matched == 0:
                    continue
                score += matched * 10

            if preferred_swarm and agent.get("swarm") == preferred_swarm:
                score += 5

            if agent.get("status") == "idle":
                score += 3

            agent_type = (agent.get("config") or {}).get("agent_type") if isinstance(agent.get("config"), dict) else None
            if agent_type is None:
                agent_type = agent.get("agent_type")
            if task_type == "routing" and agent_type == "orchestrator":
                score += 20

            score += int(priority or 5)

            active = int(agent.get("active_tasks") or 0)
            score -= 2 * active

            candidates.append((score, agent))

        if not candidates:
            return None

        candidates.sort(key=lambda pair: (pair[0], -int(pair[1].get("active_tasks") or 0)), reverse=True)
        return candidates[0][1]

    def route_task(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 5,
        required_capabilities: list[str] | None = None,
        preferred_swarm: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        required = list(required_capabilities or [])
        agent = self.find_best_agent(
            required_capabilities=required,
            preferred_swarm=preferred_swarm,
            task_type=task_type,
            priority=int(priority or 5),
        )

        tid = queue_manager.push_task(
            task_type=task_type,
            payload={
                **(payload or {}),
                "routed_to": agent.get("agent_id") if agent else None,
                "routed_at": _now_iso(),
            },
            priority=int(priority or 5),
            required_capabilities=required,
            task_id=task_id,
            swarm_name=agent.get("swarm") if agent else preferred_swarm,
        )

        decision = {
            "task_id": tid,
            "task_type": task_type,
            "assigned_agent": agent.get("agent_id") if agent else None,
            "assigned_agent_name": agent.get("name") if agent else None,
            "assigned_swarm": agent.get("swarm") if agent else None,
            "status": "assigned" if agent else "queued_unassigned",
            "routing_reason": self._explain_routing(agent, required),
            "score": self._compute_score(agent, required, preferred_swarm, task_type, int(priority or 5)) if agent else 0,
            "timestamp": _now_iso(),
        }

        if agent:
            try:
                swarm_registry.mark_status(str(agent["agent_id"]), "running")
                swarm_registry.update_load(str(agent["agent_id"]), +1)
            except Exception:  # noqa: BLE001
                log.debug("[Router] mark/load update failed", exc_info=True)

        # Redis audit log (rolling, fast)
        try:
            queue_manager.r.lpush(ROUTING_LOG_KEY, json.dumps(decision))
            queue_manager.r.ltrim(ROUTING_LOG_KEY, 0, ROUTING_LOG_LIMIT - 1)
        except Exception:  # noqa: BLE001
            pass

        # Postgres audit log (durable, queryable)
        eng = get_engine()
        if eng is not None:
            try:
                with eng.begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO routing_decisions
                                (task_id, task_type, assigned_agent, assigned_swarm,
                                 score, reason, required_capabilities)
                            VALUES (:tid, :ttype, :ag, :sw, :score, :reason, CAST(:caps AS JSONB))
                            """
                        ),
                        {
                            "tid": decision["task_id"],
                            "ttype": decision["task_type"],
                            "ag": decision["assigned_agent"],
                            "sw": decision["assigned_swarm"],
                            "score": int(decision["score"]),
                            "reason": decision["routing_reason"],
                            "caps": json.dumps(required),
                        },
                    )
            except Exception:  # noqa: BLE001
                log.debug("[Router] DB audit failed", exc_info=True)

        return decision

    def simulate_route(
        self,
        task_type: str,
        required_capabilities: list[str] | None = None,
        preferred_swarm: str | None = None,
        priority: int = 5,
    ) -> dict[str, Any]:
        agent = self.find_best_agent(
            required_capabilities=required_capabilities,
            preferred_swarm=preferred_swarm,
            task_type=task_type,
            priority=int(priority or 5),
        )
        return {
            "would_assign_to": agent.get("agent_id") if agent else None,
            "agent_name": agent.get("name") if agent else None,
            "swarm": agent.get("swarm") if agent else None,
            "score": self._compute_score(agent, required_capabilities or [], preferred_swarm, task_type, int(priority or 5)) if agent else 0,
            "reason": self._explain_routing(agent, required_capabilities),
        }

    def get_routing_log(self, limit: int = 20) -> list[dict[str, Any]]:
        safe = max(1, min(int(limit or 20), ROUTING_LOG_LIMIT))
        try:
            items = queue_manager.r.lrange(ROUTING_LOG_KEY, 0, safe - 1)
        except Exception:  # noqa: BLE001
            return []
        out: list[dict[str, Any]] = []
        for item in items:
            try:
                out.append(json.loads(item))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return out

    # ── Internals ─────────────────────────────────────────────────────────
    def _explain_routing(self, agent: dict[str, Any] | None, required_caps: list[str] | None) -> str:
        if not agent:
            return "No suitable agent found — task queued"
        reasons: list[str] = []
        required = list(required_caps or [])
        if required:
            reasons.append(f"matched capabilities: {', '.join(required)}")
        if agent.get("status") == "idle":
            reasons.append("agent was idle")
        if agent.get("active_tasks") is not None:
            reasons.append(f"load={int(agent.get('active_tasks') or 0)}")
        return "; ".join(reasons) if reasons else "best available agent"

    def _compute_score(
        self,
        agent: dict[str, Any],
        required: list[str],
        preferred_swarm: str | None,
        task_type: str | None,
        priority: int,
    ) -> int:
        score = 10
        caps = agent.get("capabilities") or []
        if isinstance(caps, list) and required:
            score += sum(10 for cap in required if cap in caps)
        if preferred_swarm and agent.get("swarm") == preferred_swarm:
            score += 5
        if agent.get("status") == "idle":
            score += 3
        if task_type == "routing":
            atype = (agent.get("config") or {}).get("agent_type") if isinstance(agent.get("config"), dict) else agent.get("agent_type")
            if atype == "orchestrator":
                score += 20
        score += int(priority or 5)
        score -= 2 * int(agent.get("active_tasks") or 0)
        return score


task_router = TaskRouter()
