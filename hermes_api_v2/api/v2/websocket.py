"""WebSocket endpoints for Hermes FastAPI v2."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from hermes_api_v2.core.database import get_db_session
from hermes_api_v2.core.security import decode_fastapi_token

router = APIRouter(tags=["websocket"])


async def _resolve_ws_user(websocket: WebSocket) -> dict[str, Any] | None:
    raw_auth = websocket.headers.get("authorization") or ""
    token = websocket.query_params.get("token")
    if not token and raw_auth.lower().startswith("bearer "):
        token = raw_auth[7:].strip()
    if not token:
        return None

    try:
        payload = decode_fastapi_token(token)
    except ValueError:
        return None
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        return None

    async for db in get_db_session():
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
    return None


async def _build_live_pnl_payload(user_id: int) -> dict[str, Any]:
    async for db in get_db_session():
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
                        COALESCE(tp.today_pnl, 0)::double precision AS today_pnl,
                        ls.snapshot_date
                    FROM user_subscriptions us
                    JOIN trading_agents ta ON ta.id = us.agent_id
                    LEFT JOIN (
                        SELECT
                            agent_id,
                            pnl_usd,
                            pnl_pct,
                            trade_count,
                            win_count,
                            snapshot_date,
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
                {"user_id": user_id},
            )
        ).mappings().all()

        items: list[dict[str, Any]] = []
        total_pnl = 0.0
        best_agent_id: str | None = None
        best_pnl: float | None = None
        for row in rows:
            agent_pnl = float(row["pnl_usd"] or 0.0)
            total_pnl += agent_pnl
            if best_pnl is None or agent_pnl > best_pnl:
                best_pnl = agent_pnl
                best_agent_id = str(row["agent_id"])

            trade_count = int(row["trade_count"] or 0)
            win_count = int(row["win_count"] or 0)
            win_rate = (100.0 * win_count / trade_count) if trade_count > 0 else 0.0
            items.append(
                {
                    "agent_id": str(row["agent_id"]),
                    "name": row["name"],
                    "symbol": row["symbol"],
                    "pnl_usd": round(agent_pnl, 2),
                    "pnl_pct": round(float(row["pnl_pct"] or 0.0), 4),
                    "today_pnl": round(float(row["today_pnl"] or 0.0), 2),
                    "trade_count": trade_count,
                    "win_count": win_count,
                    "win_rate": round(win_rate, 1),
                    "snapshot_date": str(row["snapshot_date"]) if row.get("snapshot_date") else None,
                }
            )

        return {
            "items": items,
            "total_pnl_usd": round(total_pnl, 2),
            "best_agent_id": best_agent_id,
        }

    return {"items": [], "total_pnl_usd": 0.0, "best_agent_id": None}


@router.websocket("/ws/pnl")
async def ws_pnl(websocket: WebSocket) -> None:
    await websocket.accept()
    user = await _resolve_ws_user(websocket)
    if user is None:
        await websocket.send_json({"error": "Unauthorized"})
        await websocket.close(code=1008)
        return

    try:
        while True:
            payload = await _build_live_pnl_payload(user["id"])
            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011)

