"""
Hermes QueueManager — production-grade task & registry façade.

Backward compatible
-------------------
This module preserves the public API consumed by `dashboard/app.py`:

    queue_manager.health_check()
    queue_manager.push_task(task_type, payload, priority=, required_capabilities=, task_id=)
    queue_manager.pop_task(agent_capabilities=)
    queue_manager.register_agent(agent_id, name, swarm, capabilities, config)
    queue_manager.update_agent_status(agent_id, status)
    queue_manager.heartbeat(agent_id)
    queue_manager.is_agent_alive(agent_id)
    queue_manager.get_all_agents()
    queue_manager.get_queue_stats()
    queue_manager.get_swarm_agents(swarm_name)
    queue_manager.get_agent(agent_id)

What's new
----------
1. **Dual-write** — every task is persisted to Postgres `task_queue`
   AND the Redis priority queue. Workers pop from Redis, mark in DB.
2. **Capability-aware pop** — pops only tasks the calling agent can run.
3. **Dead-letter handling** — tasks exceeding `max_retries` end up in
   `task_queue.status = 'dead'` with `dead_lettered_at = NOW()`.
4. **Delegation** — `register_agent` / `heartbeat` route through
   `core.swarm_registry.SwarmRegistry` so Postgres is canonical.

Designed for 150+ agents on 8 GB Hetzner.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import redis
from redis import RedisError
from sqlalchemy import text

try:
    from core.swarm_registry import (
        HEARTBEAT_PREFIX,
        REGISTRY_PREFIX,
        SWARM_PREFIX,
        SwarmRegistry,
        get_engine,
        get_redis,
        swarm_registry,
    )
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from hermes.core.swarm_registry import (
        HEARTBEAT_PREFIX,
        REGISTRY_PREFIX,
        SWARM_PREFIX,
        SwarmRegistry,
        get_engine,
        get_redis,
        swarm_registry,
    )

log = logging.getLogger(__name__)

# Legacy module-level client (some imports rely on `queue_manager.r`)
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
r = get_redis()

QUEUE_PRIORITY = "hermes:queue:priority"      # Redis ZSET, score = priority
QUEUE_PENDING = "hermes:queue:pending"        # Reserved for legacy callers


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── QueueManager ──────────────────────────────────────────────────────────
class QueueManager:
    """
    Façade combining the priority queue (Redis) with durable task
    persistence (Postgres) and the SwarmRegistry.
    """

    def __init__(self, redis_client: redis.Redis | None = None,
                 registry: SwarmRegistry | None = None) -> None:
        self.r = redis_client or get_redis()
        self.registry = registry or swarm_registry

    # ── Health ────────────────────────────────────────────────────────────
    def health_check(self) -> bool:
        try:
            return bool(self.r.ping())
        except RedisError:
            return False

    # ── Task lifecycle ────────────────────────────────────────────────────
    def push_task(
        self,
        task_type: str,
        payload: dict[str, Any] | None,
        priority: int = 5,
        required_capabilities: list[str] | None = None,
        task_id: str | None = None,
        swarm_name: str | None = None,
        enqueue_redis: bool = True,
    ) -> str:
        safe_payload: dict[str, Any]
        if payload is None:
            safe_payload = {}
        elif isinstance(payload, dict):
            try:
                json.dumps(payload)
                safe_payload = payload
            except (TypeError, ValueError):
                safe_payload = {"_raw_payload": str(payload)}
        else:
            safe_payload = {"_raw_payload": str(payload)}

        priority = max(1, min(int(priority or 5), 10))
        tid = str(task_id or uuid.uuid4())
        required = list(required_capabilities or [])

        task = {
            "task_id": tid,
            "task_type": str(task_type or "generic")[:50],
            "payload": safe_payload,
            "priority": priority,
            "required_capabilities": required,
            "swarm_name": swarm_name,
            "created_at": _iso_now(),
            "status": "pending",
        }

        # Postgres (durable)
        eng = get_engine()
        if eng is not None:
            try:
                with eng.begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO task_queue
                                (task_id, task_type, payload, status, priority,
                                 required_capabilities, swarm_name)
                            VALUES (:tid, :ttype, CAST(:payload AS JSONB), 'pending',
                                    :priority, CAST(:caps AS JSONB), :swarm)
                            ON CONFLICT (task_id) DO NOTHING
                            """
                        ),
                        {
                            "tid": tid,
                            "ttype": task["task_type"],
                            "payload": json.dumps(safe_payload),
                            "priority": priority,
                            "caps": json.dumps(required),
                            "swarm": swarm_name,
                        },
                    )
            except Exception:  # noqa: BLE001
                log.warning("[Queue] DB persist failed for %s", tid, exc_info=True)

        # Redis (hot)
        if enqueue_redis:
            try:
                self.r.zadd(QUEUE_PRIORITY, {json.dumps(task): priority})
            except RedisError:
                log.warning("[Queue] redis push failed for %s", tid, exc_info=True)

        return tid

    def pop_task(
        self,
        agent_capabilities: list[str] | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Capability-aware pop.

        Walks the priority queue (highest first); takes the first task whose
        `required_capabilities` ⊆ agent_capabilities. If none matches,
        returns None.
        """
        try:
            items = self.r.zrevrange(QUEUE_PRIORITY, 0, 19, withscores=True)
        except RedisError:
            return None
        if not items:
            return None

        caps = list(agent_capabilities or [])
        for task_json, _score in items:
            try:
                task = json.loads(task_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                try:
                    self.r.zrem(QUEUE_PRIORITY, task_json)
                except RedisError:
                    pass
                continue
            required = list(task.get("required_capabilities") or [])
            if required and not all(cap in caps for cap in required):
                continue
            try:
                removed = self.r.zrem(QUEUE_PRIORITY, task_json)
            except RedisError:
                continue
            if not removed:
                continue
            task["status"] = "assigned"
            task["assigned_at"] = _iso_now()
            if agent_id:
                task["assigned_to"] = agent_id
                self._mark_assigned(task["task_id"], agent_id)
            return task
        return None

    def mark_completed(
        self,
        task_id: str,
        result: dict[str, Any] | None = None,
        execution_time_ms: int | None = None,
    ) -> None:
        eng = get_engine()
        if eng is None:
            return
        with eng.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE task_queue SET
                        status = 'completed',
                        result = CAST(:r AS JSONB),
                        completed_at = NOW(),
                        execution_time_ms = COALESCE(:ms, execution_time_ms)
                    WHERE task_id = :tid
                    """
                ),
                {"tid": task_id, "r": json.dumps(result or {}), "ms": execution_time_ms},
            )

    def mark_failed(self, task_id: str, error: str, retry: bool = True) -> None:
        eng = get_engine()
        if eng is None:
            return
        with eng.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT retry_count, max_retries FROM task_queue WHERE task_id = :tid"
                ),
                {"tid": task_id},
            ).first()
            if row is None:
                return
            retry_count, max_retries = int(row[0] or 0), int(row[1] or 3)
            if retry and retry_count < max_retries:
                conn.execute(
                    text(
                        "UPDATE task_queue SET retry_count = retry_count + 1, "
                        "error_message = :e, status = 'pending' "
                        "WHERE task_id = :tid"
                    ),
                    {"tid": task_id, "e": error[:1000]},
                )
            else:
                conn.execute(
                    text(
                        "UPDATE task_queue SET status = 'dead', "
                        "error_message = :e, dead_lettered_at = NOW(), "
                        "completed_at = NOW() "
                        "WHERE task_id = :tid"
                    ),
                    {"tid": task_id, "e": error[:1000]},
                )

    def _mark_assigned(self, task_id: str, agent_id: str) -> None:
        eng = get_engine()
        if eng is None:
            return
        try:
            with eng.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE task_queue SET assigned_to = :aid, "
                        "status = 'assigned', started_at = NOW() "
                        "WHERE task_id = :tid"
                    ),
                    {"tid": task_id, "aid": agent_id},
                )
        except Exception:  # noqa: BLE001
            log.debug("[Queue] _mark_assigned failed", exc_info=True)

    # ── Registry pass-through (legacy callers) ────────────────────────────
    def register_agent(
        self,
        agent_id: str,
        name: str,
        swarm: str,
        capabilities: list[str],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.registry.register_agent(
            agent_id=agent_id,
            name=name,
            swarm=swarm,
            capabilities=capabilities,
            config=config or {},
            agent_type=str((config or {}).get("agent_type", "worker")),
        )

    def update_agent_status(self, agent_id: str, status: str) -> None:
        try:
            self.registry.mark_status(agent_id, status)
        except ValueError:
            log.warning("[Queue] invalid status: %s", status)

    def heartbeat(self, agent_id: str) -> None:
        self.registry.heartbeat(agent_id)

    def is_agent_alive(self, agent_id: str) -> bool:
        return self.registry.is_alive(agent_id)

    def get_all_agents(self) -> list[dict[str, Any]]:
        return self.registry.list_agents()

    def get_swarm_agents(self, swarm_name: str) -> list[dict[str, Any]]:
        return self.registry.list_agents(swarm=swarm_name)

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self.registry.get_agent(agent_id)

    # ── Stats ─────────────────────────────────────────────────────────────
    def get_queue_stats(self) -> dict[str, Any]:
        try:
            redis_pending = int(self.r.zcard(QUEUE_PRIORITY))
            agents_total = int(len(self.r.keys(f"{REGISTRY_PREFIX}*")))
            agents_alive = int(len(self.r.keys(f"{HEARTBEAT_PREFIX}*")))
        except RedisError:
            redis_pending, agents_total, agents_alive = 0, 0, 0

        eng = get_engine()
        db_stats: dict[str, int] = {}
        if eng is not None:
            try:
                with eng.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT status, COUNT(*)::int AS c "
                            "FROM task_queue GROUP BY status"
                        )
                    ).all()
                db_stats = {str(s): int(c) for s, c in rows}
            except Exception:  # noqa: BLE001
                pass

        return {
            "pending": redis_pending,
            "agents_total": agents_total,
            "agents_alive": agents_alive,
            "db_queue": db_stats,
        }


# Singleton instance — keep public symbol for legacy imports
queue_manager = QueueManager()
