"""Agents endpoints for Hermes FastAPI v2."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes_api_v2.core.database import get_db_session
from hermes_api_v2.dependencies import get_current_user

router = APIRouter(tags=["agents"])


def _serialize_dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


@router.get("/agents")
async def list_agents(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    ta.id,
                    ta.name,
                    ta.symbol,
                    ta.category,
                    ta.strategy,
                    us.mode,
                    us.is_active,
                    us.subscribed_at
                FROM user_subscriptions us
                JOIN trading_agents ta ON ta.id = us.agent_id
                WHERE us.user_id = :user_id
                ORDER BY us.is_active DESC, us.subscribed_at DESC NULLS LAST, ta.name ASC
                """
            ),
            {"user_id": current_user["id"]},
        )
    ).mappings().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": str(row["id"]),
                "name": row["name"],
                "symbol": row["symbol"],
                "category": row["category"],
                "strategy": row["strategy"],
                "mode": row["mode"],
                "is_active": bool(row["is_active"]),
                "subscribed_at": _serialize_dt(row.get("subscribed_at")),
            }
        )
    return {"items": items, "total": len(items)}


@router.get("/agents/{agent_id}/pnl")
async def get_agent_pnl(
    agent_id: str,
    limit: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    subscribed = (
        await db.execute(
            text(
                """
                SELECT 1
                FROM user_subscriptions
                WHERE user_id = :user_id AND agent_id = :agent_id
                LIMIT 1
                """
            ),
            {"user_id": current_user["id"], "agent_id": str(agent_id)},
        )
    ).first()
    if subscribed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    rows = (
        await db.execute(
            text(
                """
                SELECT
                    snapshot_date,
                    pnl_usd,
                    pnl_pct,
                    equity,
                    trade_count,
                    win_count,
                    created_at
                FROM agent_pnl_snapshots
                WHERE user_id = :user_id AND agent_id = :agent_id
                ORDER BY snapshot_date DESC, created_at DESC
                LIMIT :limit
                """
            ),
            {
                "user_id": current_user["id"],
                "agent_id": str(agent_id),
                "limit": int(limit),
            },
        )
    ).mappings().all()

    snapshots: list[dict[str, Any]] = []
    for row in rows:
        snapshots.append(
            {
                "snapshot_date": str(row["snapshot_date"]) if row.get("snapshot_date") is not None else None,
                "pnl_usd": float(row["pnl_usd"] or 0.0),
                "pnl_pct": float(row["pnl_pct"] or 0.0),
                "equity": float(row["equity"] or 0.0),
                "trade_count": int(row["trade_count"] or 0),
                "win_count": int(row["win_count"] or 0),
                "created_at": _serialize_dt(row.get("created_at")),
            }
        )

    return {"agent_id": str(agent_id), "snapshots": snapshots}


@router.get("/agents/{agent_id}/trades")
async def get_agent_trades(
    agent_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    id,
                    symbol,
                    action,
                    price,
                    quantity,
                    pnl,
                    reason,
                    signals,
                    confidence,
                    timestamp
                FROM paper_trades
                WHERE user_id = :user_id AND agent_id = :agent_id
                ORDER BY timestamp DESC
                LIMIT :limit
                """
            ),
            {
                "user_id": current_user["id"],
                "agent_id": str(agent_id),
                "limit": int(limit),
            },
        )
    ).mappings().all()

    trades: list[dict[str, Any]] = []
    for row in rows:
        trades.append(
            {
                "id": int(row["id"]),
                "symbol": row["symbol"],
                "action": row["action"],
                "price": float(row["price"] or 0.0),
                "quantity": float(row["quantity"] or 0.0),
                "pnl": float(row["pnl"] or 0.0),
                "reason": row["reason"],
                "signals": row["signals"],
                "confidence": float(row["confidence"] or 0.0),
                "timestamp": _serialize_dt(row.get("timestamp")),
            }
        )

    return {"agent_id": str(agent_id), "trades": trades}


@router.post("/agents/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    updated = (
        await db.execute(
            text(
                """
                UPDATE user_subscriptions
                SET is_active = NOT COALESCE(is_active, FALSE)
                WHERE user_id = :user_id AND agent_id = :agent_id
                RETURNING is_active, mode
                """
            ),
            {"user_id": current_user["id"], "agent_id": str(agent_id)},
        )
    ).mappings().first()

    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    await db.commit()
    return {
        "agent_id": str(agent_id),
        "is_active": bool(updated["is_active"]),
        "mode": updated["mode"],
    }

