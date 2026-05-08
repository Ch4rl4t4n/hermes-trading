"""Leaderboard endpoints for Hermes FastAPI v2."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import get_current_user, get_db_session, get_redis_client

router = APIRouter(tags=["leaderboard"])

PERIOD_MAP = {"7d": "weekly", "30d": "monthly", "all": "alltime"}
CACHE_TTL_SECONDS = 60


@router.get("/leaderboard")
async def get_leaderboard(
    period: str = Query(default="7d"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis | None = Depends(get_redis_client),
) -> dict[str, Any]:
    del current_user
    normalized = PERIOD_MAP.get(period.strip().lower())
    if normalized is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period must be 7d|30d|all")

    cache_key = f"fastapi:v2:leaderboard:{normalized}"
    if redis is not None:
        cached = await redis.get(cache_key)
        if cached:
            payload = json.loads(cached)
            payload["cached"] = True
            return payload

    rows = (
        await db.execute(
            text(
                """
                SELECT
                    c.rank,
                    c.agent_id,
                    ta.name,
                    ta.symbol,
                    ta.category,
                    c.pnl_pct,
                    c.pnl_usd,
                    c.win_rate,
                    c.trade_count,
                    c.subscriber_count
                FROM agent_leaderboard_cache c
                JOIN trading_agents ta ON ta.id = c.agent_id
                WHERE c.period = :period
                ORDER BY c.rank ASC
                LIMIT 50
                """
            ),
            {"period": normalized},
        )
    ).mappings().all()

    items = [
        {
            "rank": int(row["rank"]),
            "agent_id": str(row["agent_id"]),
            "name": row["name"],
            "symbol": row["symbol"],
            "category": row["category"],
            "pnl_pct": float(row["pnl_pct"] or 0.0),
            "pnl_usd": float(row["pnl_usd"] or 0.0),
            "win_rate": float(row["win_rate"] or 0.0),
            "trade_count": int(row["trade_count"] or 0),
            "subscriber_count": int(row["subscriber_count"] or 0),
        }
        for row in rows
    ]
    payload = {"period": period, "period_normalized": normalized, "items": items, "cached": False}
    if redis is not None:
        await redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(payload))
    return payload
