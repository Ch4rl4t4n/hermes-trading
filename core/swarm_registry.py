"""
Hermes Swarm Registry (Postgres canonical + Redis hot cache).

Public API
----------
SwarmRegistry().register_agent(...)
SwarmRegistry().heartbeat(agent_id)
SwarmRegistry().mark_status(agent_id, status)
SwarmRegistry().list_agents(swarm=None, alive_only=False)
SwarmRegistry().get_agent(agent_id)
SwarmRegistry().reap_dead(ttl_seconds=60)
SwarmRegistry().rebalance_load()

The registry is dual-write:
  - Postgres `agent_registry` is the durable source of truth.
  - Redis `hermes:agent:<id>` HASH + `hermes:swarm:<swarm>` SET act as
    the hot cache used by the Task Router (sub-millisecond lookups).

Designed for 150+ agents on a single 8 GB box.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import redis
from redis import RedisError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
HEARTBEAT_TTL = int(os.getenv("HERMES_SWARM_HEARTBEAT_TTL", "60"))
STOPPED_CLEANUP_SECONDS = int(os.getenv("HERMES_SWARM_STOPPED_TO_PAUSED_SECONDS", "1800"))
AUTO_RESUME_SWARMS = {
    item.strip().lower()
    for item in os.getenv("HERMES_SWARM_AUTO_RESUME_SWARMS", "maintenance,orchestra").split(",")
    if item.strip()
}

REGISTRY_PREFIX = "hermes:agent:"
SWARM_PREFIX = "hermes:swarm:"
HEARTBEAT_PREFIX = "hermes:heartbeat:"
LOAD_PREFIX = "hermes:load:"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Engine + Redis singletons ─────────────────────────────────────────────
_engine: Engine | None = None
_redis: redis.Redis | None = None
_missing_db_warned = False


def get_engine() -> Engine | None:
    """Lazy SQLAlchemy engine for sync code paths (Flask, Dramatiq workers)."""
    global _engine, _missing_db_warned
    if _engine is not None:
        return _engine
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        if not _missing_db_warned:
            log.warning("DATABASE_URL missing — registry running in Redis-only mode")
            _missing_db_warned = True
        return None
    _engine = create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _engine


def get_redis() -> redis.Redis:
    global _redis
    if _redis is not None:
        return _redis
    _redis = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2.0)
    return _redis


@contextmanager
def _db_conn():
    eng = get_engine()
    if eng is None:
        yield None
        return
    with eng.begin() as conn:
        yield conn


# ── Registry class ────────────────────────────────────────────────────────
class SwarmRegistry:
    """High-level swarm registry abstraction."""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.r = redis_client or get_redis()

    # ── Health ────────────────────────────────────────────────────────────
    def health_check(self) -> dict[str, bool]:
        out = {"redis": False, "postgres": False}
        try:
            out["redis"] = bool(self.r.ping())
        except RedisError:
            pass
        eng = get_engine()
        if eng is not None:
            try:
                with eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                out["postgres"] = True
            except Exception:  # noqa: BLE001
                pass
        return out

    # ── Agent lifecycle ───────────────────────────────────────────────────
    def register_agent(
        self,
        agent_id: str,
        name: str,
        swarm: str,
        capabilities: Iterable[str] | None = None,
        agent_type: str = "worker",
        priority: int = 5,
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        caps = list(capabilities or [])
        cfg = dict(config or {})
        meta = dict(metadata or {})
        priority = max(1, min(int(priority), 10))

        # Postgres (canonical) — UPSERT
        with _db_conn() as conn:
            if conn is not None:
                conn.execute(
                    text(
                        """
                        INSERT INTO agent_registry
                            (agent_id, name, swarm_name, agent_type, status,
                             capabilities, priority, config, metadata, version)
                        VALUES
                            (:aid, :name, :swarm, :atype, 'idle',
                             CAST(:caps AS JSONB), :pri,
                             CAST(:cfg AS JSONB), CAST(:meta AS JSONB), '2.0')
                        ON CONFLICT (agent_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            swarm_name = EXCLUDED.swarm_name,
                            agent_type = EXCLUDED.agent_type,
                            capabilities = EXCLUDED.capabilities,
                            priority = EXCLUDED.priority,
                            config = EXCLUDED.config,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW();
                        """
                    ),
                    {
                        "aid": agent_id,
                        "name": name,
                        "swarm": swarm,
                        "atype": agent_type,
                        "caps": json.dumps(caps),
                        "pri": priority,
                        "cfg": json.dumps(cfg),
                        "meta": json.dumps(meta),
                    },
                )

        # Redis (hot cache)
        try:
            self.r.hset(
                f"{REGISTRY_PREFIX}{agent_id}",
                mapping={
                    "agent_id": agent_id,
                    "name": name,
                    "swarm": swarm,
                    "agent_type": agent_type,
                    "status": "idle",
                    "capabilities": json.dumps(caps),
                    "priority": str(priority),
                    "config": json.dumps(cfg),
                    "metadata": json.dumps(meta),
                    "registered_at": _iso_now(),
                    "version": "2.0",
                },
            )
            self.r.sadd(f"{SWARM_PREFIX}{swarm}", agent_id)
        except RedisError:
            log.warning("[Registry] Redis write failed for %s", agent_id, exc_info=True)

        log.info("[Registry] registered %s (swarm=%s, caps=%s)", agent_id, swarm, caps)
        return {"agent_id": agent_id, "swarm": swarm, "status": "idle"}

    def heartbeat(self, agent_id: str) -> None:
        try:
            self.r.setex(f"{HEARTBEAT_PREFIX}{agent_id}", HEARTBEAT_TTL, "1")
            redis_key = f"{REGISTRY_PREFIX}{agent_id}"
            current_status = self.r.hget(redis_key, "status")
            swarm_name = str(self.r.hget(redis_key, "swarm") or "").lower()
            updates = {"last_heartbeat": _iso_now()}
            # Auto-revive stale agents that send a fresh heartbeat.
            should_revive = current_status == "stopped" or (
                current_status == "paused" and swarm_name in AUTO_RESUME_SWARMS
            )
            if should_revive:
                updates["status"] = "idle"
            self.r.hset(redis_key, mapping=updates)
        except RedisError:
            log.debug("[Registry] heartbeat redis fail", exc_info=True)

        with _db_conn() as conn:
            if conn is not None:
                row = conn.execute(
                    text("SELECT status, swarm_name FROM agent_registry WHERE agent_id = :aid"),
                    {"aid": agent_id},
                ).mappings().first()
                next_status = None
                if row:
                    db_status = str(row.get("status") or "").lower()
                    db_swarm = str(row.get("swarm_name") or "").lower()
                    if db_status == "stopped" or (
                        db_status == "paused" and db_swarm in AUTO_RESUME_SWARMS
                    ):
                        next_status = "idle"
                conn.execute(
                    text(
                        "UPDATE agent_registry "
                        "SET last_heartbeat = NOW(), "
                        "    last_seen = NOW(), "
                        "    status = COALESCE(:next_status, status), "
                        "    updated_at = CASE "
                        "        WHEN :next_status IS NOT NULL THEN NOW() "
                        "        ELSE updated_at "
                        "    END "
                        "WHERE agent_id = :aid"
                    ),
                    {"aid": agent_id, "next_status": next_status},
                )

    def mark_status(self, agent_id: str, status: str) -> None:
        status = status.lower().strip()
        if status not in {"idle", "running", "paused", "error", "stopped"}:
            raise ValueError(f"invalid status: {status}")
        try:
            self.r.hset(f"{REGISTRY_PREFIX}{agent_id}", "status", status)
        except RedisError:
            pass
        with _db_conn() as conn:
            if conn is not None:
                conn.execute(
                    text(
                        "UPDATE agent_registry SET status = :s, updated_at = NOW() "
                        "WHERE agent_id = :aid"
                    ),
                    {"s": status, "aid": agent_id},
                )

    def update_load(self, agent_id: str, delta: int) -> None:
        """Bump active_tasks counter (delta can be +1 or -1)."""
        try:
            self.r.hincrby(f"{REGISTRY_PREFIX}{agent_id}", "active_tasks", int(delta))
        except RedisError:
            pass
        with _db_conn() as conn:
            if conn is not None:
                conn.execute(
                    text(
                        "UPDATE agent_registry "
                        "SET active_tasks = GREATEST(0, COALESCE(active_tasks,0) + :d) "
                        "WHERE agent_id = :aid"
                    ),
                    {"d": int(delta), "aid": agent_id},
                )

    def is_alive(self, agent_id: str) -> bool:
        try:
            return bool(self.r.exists(f"{HEARTBEAT_PREFIX}{agent_id}"))
        except RedisError:
            return False

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        try:
            data = self.r.hgetall(f"{REGISTRY_PREFIX}{agent_id}")
        except RedisError:
            data = None
        if data:
            return self._materialise(data)

        # Fallback: read from Postgres (cold cache)
        with _db_conn() as conn:
            if conn is None:
                return None
            row = conn.execute(
                text(
                    "SELECT agent_id, name, swarm_name, agent_type, status, "
                    "capabilities, priority, config, metadata, last_heartbeat, "
                    "active_tasks "
                    "FROM agent_registry WHERE agent_id = :aid"
                ),
                {"aid": agent_id},
            ).mappings().first()
            if row is None:
                return None
            return self._row_to_dict(row)

    def list_agents(
        self,
        swarm: str | None = None,
        alive_only: bool = False,
    ) -> list[dict[str, Any]]:
        # Try Redis first
        agents: list[dict[str, Any]] = []
        try:
            if swarm:
                ids = list(self.r.smembers(f"{SWARM_PREFIX}{swarm}"))
            else:
                keys = self.r.keys(f"{REGISTRY_PREFIX}*")
                ids = [k.removeprefix(REGISTRY_PREFIX) for k in keys]
            for aid in ids:
                agent = self.get_agent(aid)
                if agent is None:
                    continue
                if alive_only and not agent.get("alive"):
                    continue
                agents.append(agent)
        except RedisError:
            agents = []

        if agents:
            return agents

        # Fallback Postgres
        with _db_conn() as conn:
            if conn is None:
                return []
            sql = (
                "SELECT agent_id, name, swarm_name, agent_type, status, "
                "capabilities, priority, config, metadata, last_heartbeat, "
                "active_tasks "
                "FROM agent_registry "
            )
            params: dict[str, Any] = {}
            if swarm:
                sql += "WHERE swarm_name = :swarm "
                params["swarm"] = swarm
            sql += "ORDER BY swarm_name, name"
            rows = conn.execute(text(sql), params).mappings().all()
            agents = [self._row_to_dict(r) for r in rows]
            if alive_only:
                agents = [a for a in agents if a.get("alive")]
            return agents

    # ── Cache hydration / cleanup ─────────────────────────────────────────
    def hydrate_from_db(self) -> int:
        """Repopulate Redis cache from Postgres (run on app startup)."""
        eng = get_engine()
        if eng is None:
            return 0
        count = 0
        with eng.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT agent_id, name, swarm_name, agent_type, status, "
                    "capabilities, priority, config, metadata "
                    "FROM agent_registry"
                )
            ).mappings().all()
        for row in rows:
            try:
                self.r.hset(
                    f"{REGISTRY_PREFIX}{row['agent_id']}",
                    mapping={
                        "agent_id": row["agent_id"],
                        "name": row["name"],
                        "swarm": row["swarm_name"] or "default",
                        "agent_type": row["agent_type"] or "worker",
                        "status": row["status"] or "idle",
                        "capabilities": json.dumps(row["capabilities"] or []),
                        "priority": str(row["priority"] or 5),
                        "config": json.dumps(row["config"] or {}),
                        "metadata": json.dumps(row["metadata"] or {}),
                    },
                )
                self.r.sadd(f"{SWARM_PREFIX}{row['swarm_name'] or 'default'}", row["agent_id"])
                count += 1
            except RedisError:
                continue
        log.info("[Registry] hydrated %s agents from DB", count)
        return count

    def reap_dead(self, ttl_seconds: int | None = None) -> int:
        """Mark agents without heartbeat in last `ttl_seconds` as 'stopped'."""
        ttl = int(ttl_seconds or HEARTBEAT_TTL)
        cutoff = _utc_now() - timedelta(seconds=ttl)
        eng = get_engine()
        if eng is None:
            return 0
        with eng.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE agent_registry "
                    "SET status = 'stopped', updated_at = NOW() "
                    "WHERE last_heartbeat IS NOT NULL "
                    "  AND last_heartbeat < :cutoff "
                    "  AND status NOT IN ('stopped','error') "
                    "RETURNING agent_id"
                ),
                {"cutoff": cutoff},
            )
            reaped = [row[0] for row in res]
        for aid in reaped:
            try:
                self.r.hset(f"{REGISTRY_PREFIX}{aid}", "status", "stopped")
            except RedisError:
                pass
        if reaped:
            log.warning("[Registry] reaped %s dead agents: %s", len(reaped), reaped)
        return len(reaped)

    def cleanup_stopped(self, older_than_seconds: int | None = None) -> int:
        """
        Convert long-stopped agents to paused (archived standby state).

        This keeps live health dashboards clean while preserving non-runnable
        states for offline or dormant agents.
        """
        age = int(older_than_seconds or STOPPED_CLEANUP_SECONDS)
        if age <= 0:
            return 0
        cutoff = _utc_now() - timedelta(seconds=age)
        eng = get_engine()
        if eng is None:
            return 0
        with eng.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE agent_registry "
                    "SET status = 'paused', updated_at = NOW() "
                    "WHERE status = 'stopped' "
                    "  AND last_heartbeat IS NOT NULL "
                    "  AND last_heartbeat < :cutoff "
                    "RETURNING agent_id"
                ),
                {"cutoff": cutoff},
            )
            cleaned = [row[0] for row in res]
        for aid in cleaned:
            try:
                self.r.hset(f"{REGISTRY_PREFIX}{aid}", "status", "paused")
            except RedisError:
                pass
        if cleaned:
            log.info("[Registry] cleaned %s stopped agents -> paused: %s", len(cleaned), cleaned)
        return len(cleaned)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _materialise(self, data: dict[str, Any]) -> dict[str, Any]:
        for field in ("capabilities", "config", "metadata"):
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except (TypeError, ValueError):
                    data[field] = [] if field == "capabilities" else {}
        for field in ("priority", "active_tasks"):
            if field in data:
                try:
                    data[field] = int(data[field])
                except (TypeError, ValueError):
                    data[field] = 0
        aid = str(data.get("agent_id") or "")
        data["alive"] = self.is_alive(aid) if aid else False
        return data

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        d = dict(row)
        d["swarm"] = d.pop("swarm_name", "default") or "default"
        if d.get("last_heartbeat") is not None:
            d["last_heartbeat"] = d["last_heartbeat"].isoformat()
        d["alive"] = False
        if d.get("last_heartbeat"):
            try:
                ts = datetime.fromisoformat(d["last_heartbeat"])
                d["alive"] = ts > _utc_now() - timedelta(seconds=HEARTBEAT_TTL)
            except (TypeError, ValueError):
                pass
        return d


# Singleton
swarm_registry = SwarmRegistry()
