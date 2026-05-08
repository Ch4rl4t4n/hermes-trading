"""Agents endpoints and websocket stream for Hermes FastAPI v2."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import decode_fastapi_token, get_current_user, get_db_session

router = APIRouter(tags=["agents"])


def _serialize_dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


@router.get("/agents")
async def list_agents(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
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
    return {
        "items": [
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
            for row in rows
        ],
        "total": len(rows),
    }


@router.get("/agents/{agent_id}/pnl")
async def get_agent_pnl(
    agent_id: str,
    limit: int = Query(default=30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
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
                WHERE user_id = :user_id
                  AND agent_id = :agent_id
                ORDER BY snapshot_date DESC, created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": current_user["id"], "agent_id": agent_id, "limit": int(limit)},
        )
    ).mappings().all()
    return {
        "agent_id": str(agent_id),
        "snapshots": [
            {
                "snapshot_date": str(row["snapshot_date"]) if row.get("snapshot_date") else None,
                "pnl_usd": float(row["pnl_usd"] or 0.0),
                "pnl_pct": float(row["pnl_pct"] or 0.0),
                "equity": float(row["equity"] or 0.0),
                "trade_count": int(row["trade_count"] or 0),
                "win_count": int(row["win_count"] or 0),
                "created_at": _serialize_dt(row.get("created_at")),
            }
            for row in rows
        ],
    }


@router.get("/agents/{agent_id}/trades")
async def get_agent_trades(
    agent_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
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
                WHERE user_id = :user_id
                  AND agent_id = :agent_id
                ORDER BY timestamp DESC
                LIMIT :limit
                """
            ),
            {"user_id": current_user["id"], "agent_id": agent_id, "limit": int(limit)},
        )
    ).mappings().all()
    return {
        "agent_id": str(agent_id),
        "trades": [
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
            for row in rows
        ],
    }


@router.post("/agents/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                UPDATE user_subscriptions
                SET is_active = NOT COALESCE(is_active, FALSE)
                WHERE user_id = :user_id AND agent_id = :agent_id
                RETURNING is_active, mode
                """
            ),
            {"user_id": current_user["id"], "agent_id": agent_id},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    await db.commit()
    return {"agent_id": str(agent_id), "is_active": bool(row["is_active"]), "mode": row["mode"]}


async def _resolve_ws_user(websocket: WebSocket, db: AsyncSession) -> dict[str, Any] | None:
    auth_header = websocket.headers.get("authorization", "")
    token = websocket.query_params.get("token")
    if not token and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        return None
    try:
        payload = decode_fastapi_token(token)
    except ValueError:
        return None
    user_id = str(payload.get("sub") or "").strip()
    row = (
        await db.execute(
            text(
                """
                SELECT id, email, tier
                FROM users
                WHERE CAST(id AS text) = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    if row is None:
        return None
    return {"id": int(row["id"]), "email": row["email"], "tier": row["tier"]}


async def _live_pnl_payload(user_id: int, db: AsyncSession) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    us.agent_id,
                    ta.name,
                    ta.symbol,
                    COALESCE(ls.pnl_usd, 0)::double precision AS pnl_usd,
                    COALESCE(ls.pnl_pct, 0)::double precision AS pnl_pct,
                    COALESCE(ls.trade_count, 0)::int AS trade_count,
                    COALESCE(ls.win_count, 0)::int AS win_count,
                    COALESCE(tp.today_pnl, 0)::double precision AS today_pnl
                FROM user_subscriptions us
                JOIN trading_agents ta ON ta.id = us.agent_id
                LEFT JOIN (
                    SELECT
                        agent_id,
                        pnl_usd,
                        pnl_pct,
                        trade_count,
                        win_count,
                        ROW_NUMBER() OVER (
                            PARTITION BY agent_id
                            ORDER BY snapshot_date DESC, created_at DESC
                        ) AS rn
                    FROM agent_pnl_snapshots
                    WHERE user_id = :user_id
                ) ls ON ls.agent_id = us.agent_id AND ls.rn = 1
                LEFT JOIN (
                    SELECT
                        agent_id,
                        COALESCE(SUM(pnl), 0)::double precision AS today_pnl
                    FROM paper_trades
                    WHERE user_id = :user_id
                      AND (timestamp AT TIME ZONE 'UTC')::date =
                          (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
                    GROUP BY agent_id
                ) tp ON tp.agent_id = us.agent_id
                WHERE us.user_id = :user_id
                  AND us.is_active IS TRUE
                ORDER BY ta.name ASC
                """
            ),
            {"user_id": int(user_id)},
        )
    ).mappings().all()

    items: list[dict[str, Any]] = []
    total = 0.0
    for row in rows:
        pnl_usd = float(row["pnl_usd"] or 0.0)
        total += pnl_usd
        trades = int(row["trade_count"] or 0)
        wins = int(row["win_count"] or 0)
        win_rate = (wins / trades * 100.0) if trades > 0 else 0.0
        items.append(
            {
                "agent_id": str(row["agent_id"]),
                "name": row["name"],
                "symbol": row["symbol"],
                "pnl_usd": round(pnl_usd, 2),
                "pnl_pct": round(float(row["pnl_pct"] or 0.0), 4),
                "today_pnl": round(float(row["today_pnl"] or 0.0), 2),
                "trade_count": trades,
                "win_count": wins,
                "win_rate": round(win_rate, 1),
            }
        )
    return {"items": items, "total_pnl_usd": round(total, 2)}


@router.websocket("/ws/pnl")
async def ws_pnl(websocket: WebSocket) -> None:
    await websocket.accept()
    async for db in get_db_session():
        user = await _resolve_ws_user(websocket, db)
        if user is None:
            await websocket.send_json({"error": "Unauthorized"})
            await websocket.close(code=1008)
            return
        try:
            while True:
                payload = await _live_pnl_payload(user["id"], db)
                await websocket.send_json(payload)
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            return
        except Exception:
            await websocket.close(code=1011)
            return
