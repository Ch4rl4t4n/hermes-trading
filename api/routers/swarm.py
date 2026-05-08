"""
FastAPI v2 — Swarm endpoints.

Exposed under `/api/v2/swarm/*` (mounted by `api/main.py`).

GET  /api/v2/swarm/status          — overall health + agent/queue counts
GET  /api/v2/swarm/swarms          — list of swarms with members
GET  /api/v2/swarm/agents          — full registry (filter by ?swarm=…&alive_only=true)
GET  /api/v2/swarm/agents/{id}     — single agent snapshot
GET  /api/v2/swarm/queue           — queue stats + recent tasks
GET  /api/v2/swarm/routing-log     — last N routing decisions
POST /api/v2/swarm/route           — simulate routing for a hypothetical task
POST /api/v2/swarm/dispatch        — actually push a task into the queue (admin)
POST /api/v2/swarm/seed            — re-run swarm bootstrap (admin)

All endpoints require a valid bearer (FastAPI JWT). `dispatch` and `seed`
additionally require `tier == 'admin'`.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import get_current_user, get_db_session

router = APIRouter(prefix="/swarm", tags=["swarm"])


# ── Helpers ───────────────────────────────────────────────────────────────
def _require_admin(current_user: dict) -> None:
    if (current_user or {}).get("tier") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin tier required")


def _serialize_dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


async def _list_agents_async(db: AsyncSession, swarm: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT agent_id, name, swarm_name, agent_type, status, capabilities, "
        "priority, config, metadata, last_heartbeat, active_tasks, "
        "tasks_completed, tasks_failed "
        "FROM agent_registry "
    )
    params: dict[str, Any] = {}
    if swarm:
        sql += "WHERE swarm_name = :swarm "
        params["swarm"] = swarm
    sql += "ORDER BY swarm_name, name"
    rows = (await db.execute(text(sql), params)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["last_heartbeat"] = _serialize_dt(d.get("last_heartbeat"))
        d["alive"] = False
        if row.get("last_heartbeat"):
            from datetime import timezone, timedelta
            now = datetime.now(timezone.utc)
            ts = row["last_heartbeat"]
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                d["alive"] = ts > now - timedelta(seconds=60)
        for f in ("capabilities", "config", "metadata"):
            if isinstance(d.get(f), str):
                try:
                    d[f] = json.loads(d[f])
                except (TypeError, ValueError, json.JSONDecodeError):
                    d[f] = [] if f == "capabilities" else {}
        out.append(d)
    return out


# ── Models ────────────────────────────────────────────────────────────────
class RouteSimulateRequest(BaseModel):
    task_type: str = Field(..., max_length=50)
    required_capabilities: list[str] | None = None
    preferred_swarm: str | None = None
    priority: int = Field(default=5, ge=1, le=10)


class DispatchRequest(BaseModel):
    task_type: str = Field(..., max_length=50)
    payload: dict[str, Any] | None = None
    required_capabilities: list[str] | None = None
    preferred_swarm: str | None = None
    priority: int = Field(default=5, ge=1, le=10)


# ── Endpoints ─────────────────────────────────────────────────────────────
@router.get("/status")
async def swarm_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Overall swarm health snapshot — safe for frontend polling."""
    agents_row = (await db.execute(
        text(
            "SELECT "
            "  COUNT(*) FILTER (WHERE TRUE) AS total, "
            "  COUNT(*) FILTER (WHERE last_heartbeat > NOW() - INTERVAL '60 seconds') AS alive, "
            "  COUNT(*) FILTER (WHERE status = 'running') AS running, "
            "  COUNT(*) FILTER (WHERE status = 'idle') AS idle, "
            "  COUNT(*) FILTER (WHERE status = 'paused') AS paused, "
            "  COUNT(*) FILTER (WHERE status = 'error') AS unhealthy, "
            "  COUNT(*) FILTER (WHERE status = 'stopped') AS stopped "
            "FROM agent_registry"
        )
    )).mappings().first() or {}

    queue_row = (await db.execute(
        text(
            "SELECT "
            "  COUNT(*) FILTER (WHERE status = 'pending') AS pending, "
            "  COUNT(*) FILTER (WHERE status = 'assigned') AS assigned, "
            "  COUNT(*) FILTER (WHERE status = 'running') AS running, "
            "  COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
            "  COUNT(*) FILTER (WHERE status = 'failed') AS failed, "
            "  COUNT(*) FILTER (WHERE status = 'dead') AS dead "
            "FROM task_queue"
        )
    )).mappings().first() or {}

    swarms_rows = (await db.execute(
        text(
            "SELECT swarm_name, COUNT(*) AS members, "
            "       COUNT(*) FILTER (WHERE last_heartbeat > NOW() - INTERVAL '60 seconds') AS alive_members "
            "FROM agent_registry "
            "GROUP BY swarm_name "
            "ORDER BY swarm_name"
        )
    )).mappings().all()

    redis_ok = False
    heartbeat_ttl = 60
    stopped_cleanup_seconds = 1800
    auto_resume_swarms: list[str] = []
    try:
        try:
            from core.swarm_registry import (
                AUTO_RESUME_SWARMS,
                HEARTBEAT_TTL,
                STOPPED_CLEANUP_SECONDS,
                swarm_registry,
            )
        except ModuleNotFoundError:
            from hermes.core.swarm_registry import (
                AUTO_RESUME_SWARMS,
                HEARTBEAT_TTL,
                STOPPED_CLEANUP_SECONDS,
                swarm_registry,
            )
        redis_ok = swarm_registry.health_check().get("redis", False)
        heartbeat_ttl = int(HEARTBEAT_TTL)
        stopped_cleanup_seconds = int(STOPPED_CLEANUP_SECONDS)
        auto_resume_swarms = sorted(str(s).lower() for s in AUTO_RESUME_SWARMS)
    except Exception:  # noqa: BLE001
        redis_ok = False

    return {
        "version": "2.0.0",
        "redis_ok": redis_ok,
        "policy": {
            "heartbeat_ttl_seconds": heartbeat_ttl,
            "stopped_to_paused_seconds": stopped_cleanup_seconds,
            "auto_resume_swarms": auto_resume_swarms,
        },
        "agents": {k: int(v or 0) for k, v in agents_row.items()},
        "queue": {k: int(v or 0) for k, v in queue_row.items()},
        "swarms": [
            {
                "name": row["swarm_name"],
                "members": int(row["members"] or 0),
                "alive_members": int(row["alive_members"] or 0),
            }
            for row in swarms_rows
        ],
    }


@router.get("/swarms")
async def list_swarms(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = (await db.execute(
        text(
            "SELECT swarm_name, "
            "  COUNT(*) AS total, "
            "  COUNT(*) FILTER (WHERE last_heartbeat > NOW() - INTERVAL '60 seconds') AS alive, "
            "  COUNT(*) FILTER (WHERE status = 'running') AS running, "
            "  array_agg(agent_id ORDER BY name) AS members "
            "FROM agent_registry "
            "GROUP BY swarm_name "
            "ORDER BY swarm_name"
        )
    )).mappings().all()
    return {
        "swarms": [
            {
                "swarm_name": row["swarm_name"],
                "total": int(row["total"] or 0),
                "alive": int(row["alive"] or 0),
                "running": int(row["running"] or 0),
                "members": list(row["members"] or []),
            }
            for row in rows
        ]
    }


@router.get("/agents")
async def list_swarm_agents(
    swarm: str | None = Query(default=None, max_length=50),
    alive_only: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    agents = await _list_agents_async(db, swarm=swarm)
    if alive_only:
        agents = [a for a in agents if a.get("alive")]
    return {"items": agents, "total": len(agents)}


@router.get("/agents/{agent_id}")
async def get_swarm_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    row = (await db.execute(
        text(
            "SELECT agent_id, name, swarm_name, agent_type, status, capabilities, "
            "priority, config, metadata, last_heartbeat, active_tasks, "
            "tasks_completed, tasks_failed "
            "FROM agent_registry WHERE agent_id = :aid"
        ),
        {"aid": agent_id},
    )).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    d = dict(row)
    d["last_heartbeat"] = _serialize_dt(d.get("last_heartbeat"))
    return d


@router.get("/queue")
async def queue_overview(
    limit: int = Query(default=25, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    stats_row = (await db.execute(
        text(
            "SELECT status, COUNT(*)::int AS c "
            "FROM task_queue GROUP BY status"
        )
    )).all()
    stats = {str(s): int(c) for s, c in stats_row}

    rows = (await db.execute(
        text(
            "SELECT task_id, task_type, status, priority, assigned_to, swarm_name, "
            "       retry_count, created_at, started_at, completed_at, "
            "       execution_time_ms, dead_lettered_at "
            "FROM task_queue "
            "ORDER BY created_at DESC "
            "LIMIT :limit"
        ),
        {"limit": int(limit)},
    )).mappings().all()
    items = []
    for row in rows:
        d = dict(row)
        for f in ("created_at", "started_at", "completed_at", "dead_lettered_at"):
            d[f] = _serialize_dt(d.get(f))
        items.append(d)
    return {"stats": stats, "recent": items}


@router.get("/routing-log")
async def routing_log(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = (await db.execute(
        text(
            "SELECT task_id, task_type, assigned_agent, assigned_swarm, "
            "       score, reason, required_capabilities, decided_at "
            "FROM routing_decisions "
            "ORDER BY decided_at DESC "
            "LIMIT :limit"
        ),
        {"limit": int(limit)},
    )).mappings().all()
    items = []
    for row in rows:
        d = dict(row)
        d["decided_at"] = _serialize_dt(d.get("decided_at"))
        items.append(d)
    return {"items": items, "total": len(items)}


@router.post("/route")
async def simulate_route(
    body: RouteSimulateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dry-run — does NOT enqueue."""
    try:
        from core.task_router import task_router
    except ModuleNotFoundError:
        from hermes.core.task_router import task_router
    decision = task_router.simulate_route(
        task_type=body.task_type,
        required_capabilities=body.required_capabilities,
        preferred_swarm=body.preferred_swarm,
        priority=body.priority,
    )
    return decision


@router.post("/dispatch")
async def dispatch_task(
    body: DispatchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Actually enqueue a task — admin only."""
    _require_admin(current_user)
    try:
        from core.task_router import task_router
    except ModuleNotFoundError:
        from hermes.core.task_router import task_router
    decision = task_router.route_task(
        task_type=body.task_type,
        payload=body.payload or {},
        priority=body.priority,
        required_capabilities=body.required_capabilities,
        preferred_swarm=body.preferred_swarm,
    )

    # Hand off to Dramatiq if a worker is configured
    try:
        try:
            from core.swarm_actors import execute_task
        except ModuleNotFoundError:
            from hermes.core.swarm_actors import execute_task
        if decision.get("assigned_agent"):
            execute_task.send(
                decision["task_id"],
                decision["assigned_agent"],
                body.task_type,
                body.payload or {},
            )
            decision["dispatched_to_dramatiq"] = True
    except Exception:  # noqa: BLE001
        decision["dispatched_to_dramatiq"] = False

    return decision


@router.post("/seed")
async def seed_swarm(current_user: dict = Depends(get_current_user)) -> dict:
    """Re-run swarm bootstrap — admin only."""
    _require_admin(current_user)
    try:
        from core.swarm_bootstrap import hydrate_and_seed
    except ModuleNotFoundError:
        from hermes.core.swarm_bootstrap import hydrate_and_seed
    return hydrate_and_seed()
