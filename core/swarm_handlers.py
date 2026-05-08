"""
Domain-specific task handlers for the Swarm v2.

Each handler is registered with `core.swarm_actors.register_handler(...)`
and consumed by the generic `execute_task` Dramatiq actor:

    register_handler("analyze_market", handle_analyze_market)
    register_handler("generate_report", handle_generate_report)
    register_handler("send_alert", handle_send_alert)
    register_handler("snapshot_pnl", handle_snapshot_pnl)

Handlers must be **pure** (no global state) and return a JSON-serialisable
dict. All errors should bubble up — Dramatiq retries are configured at
the actor level, dead-letter at queue_manager.mark_failed.
"""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

import httpx
from sqlalchemy import text

try:
    from core.swarm_registry import get_engine
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from hermes.core.swarm_registry import get_engine

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 1. Market analysis (Intelligence swarm) ───────────────────────────────
def handle_analyze_market(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Pull latest snapshot for a symbol from agent_pnl_snapshots and emit
    a structured signal. Lightweight and safe — works as a building block.
    """
    symbol = str(payload.get("symbol") or "BTC").upper()[:10]
    eng = get_engine()
    if eng is None:
        return {"ok": False, "reason": "no_database", "symbol": symbol}

    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ta.name, ta.symbol, aps.pnl_usd, aps.pnl_pct, aps.snapshot_date
                FROM agent_pnl_snapshots aps
                JOIN trading_agents ta ON ta.id = aps.agent_id
                WHERE UPPER(ta.symbol) = :sym
                ORDER BY aps.snapshot_date DESC
                LIMIT 7
                """
            ),
            {"sym": symbol},
        ).mappings().all()

    if not rows:
        return {"ok": True, "symbol": symbol, "signal": "neutral", "samples": 0}

    avg_pct = sum(float(r["pnl_pct"] or 0) for r in rows) / len(rows)
    last_pct = float(rows[0]["pnl_pct"] or 0)
    signal = "neutral"
    if avg_pct > 1.5 and last_pct > 0:
        signal = "bullish"
    elif avg_pct < -1.5 and last_pct < 0:
        signal = "bearish"

    return {
        "ok": True,
        "symbol": symbol,
        "signal": signal,
        "avg_pct_7d": round(avg_pct, 4),
        "last_pct": round(last_pct, 4),
        "samples": len(rows),
        "generated_at": _now_iso(),
    }


# ── 2. Generate report (Intelligence + Marketing swarm) ──────────────────
def handle_generate_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate metrics across all swarms — fast read-only summary."""
    eng = get_engine()
    if eng is None:
        return {"ok": False, "reason": "no_database"}

    with eng.connect() as conn:
        agents_row = conn.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "       COUNT(*) FILTER (WHERE last_heartbeat > NOW() - INTERVAL '60 seconds') AS alive "
                "FROM agent_registry"
            )
        ).mappings().first() or {}
        queue_row = conn.execute(
            text(
                "SELECT "
                "  COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
                "  COUNT(*) FILTER (WHERE status = 'failed')    AS failed, "
                "  COUNT(*) FILTER (WHERE status = 'dead')      AS dead, "
                "  COALESCE(AVG(execution_time_ms),0)::int      AS avg_ms "
                "FROM task_queue "
                "WHERE created_at > NOW() - INTERVAL '24 hours'"
            )
        ).mappings().first() or {}

    return {
        "ok": True,
        "report_type": str(payload.get("report_type") or "daily_summary"),
        "agents_total": int(agents_row.get("total") or 0),
        "agents_alive": int(agents_row.get("alive") or 0),
        "tasks_24h": {
            "completed": int(queue_row.get("completed") or 0),
            "failed": int(queue_row.get("failed") or 0),
            "dead": int(queue_row.get("dead") or 0),
            "avg_ms": int(queue_row.get("avg_ms") or 0),
        },
        "generated_at": _now_iso(),
    }


# ── 3. Send alert (User Experience swarm) ─────────────────────────────────
def handle_send_alert(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch an alert to one of the supported channels (telegram | email).
    No-op if credentials are absent — the task still completes.
    """
    channel = str(payload.get("channel") or "telegram").lower()
    title = str(payload.get("title") or "Hermes alert")[:120]
    body = str(payload.get("body") or "")[:1000]
    target = str(payload.get("target") or "").strip()
    sent = False

    if channel == "telegram":
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = target or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if bot_token and chat_id:
            try:
                with httpx.Client(timeout=10) as http:
                    http.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": f"*{title}*\n{body}",
                            "parse_mode": "Markdown",
                        },
                    )
                sent = True
            except Exception:  # noqa: BLE001
                log.exception("[Alert] telegram send failed")

    elif channel == "email":
        host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("GMAIL_USER", "").strip()
        password = os.getenv("GMAIL_PASSWORD", "").strip()
        recipient = target or user
        if user and password and recipient:
            try:
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = title
                msg["From"] = user
                msg["To"] = recipient
                with smtplib.SMTP(host, port, timeout=15) as smtp:
                    smtp.starttls()
                    smtp.login(user, password)
                    smtp.send_message(msg)
                sent = True
            except Exception:  # noqa: BLE001
                log.exception("[Alert] email send failed")

    return {
        "ok": True,
        "channel": channel,
        "title": title,
        "sent": sent,
        "target": target or None,
        "generated_at": _now_iso(),
    }


# ── 4. Snapshot PnL (Trading swarm housekeeping) ──────────────────────────
def handle_snapshot_pnl(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Compute aggregate PnL across all paper_trades for a user (or all)
    in the last 24h. Returns a thin summary; persistence stays in
    `agent_pnl_snapshots` (handled by watcher).
    """
    eng = get_engine()
    if eng is None:
        return {"ok": False, "reason": "no_database"}

    user_id = payload.get("user_id")
    sql = (
        "SELECT "
        "  COUNT(*) AS trades, "
        "  COALESCE(SUM(pnl), 0)::float AS total_pnl, "
        "  COALESCE(AVG(pnl), 0)::float AS avg_pnl, "
        "  COUNT(*) FILTER (WHERE pnl > 0) AS wins "
        "FROM paper_trades "
        "WHERE timestamp > NOW() - INTERVAL '24 hours'"
    )
    params: dict[str, Any] = {}
    if user_id is not None:
        sql += " AND user_id = :uid"
        params["uid"] = int(user_id)
    with eng.connect() as conn:
        row = conn.execute(text(sql), params).mappings().first() or {}
    return {
        "ok": True,
        "scope": "user" if user_id is not None else "global",
        "user_id": user_id,
        "trades_24h": int(row.get("trades") or 0),
        "total_pnl": float(row.get("total_pnl") or 0.0),
        "avg_pnl": float(row.get("avg_pnl") or 0.0),
        "wins": int(row.get("wins") or 0),
        "generated_at": _now_iso(),
    }


# ── Registration ──────────────────────────────────────────────────────────
def register_all() -> list[str]:
    """Register all handlers with the actor TASK_HANDLERS map."""
    try:
        from core.swarm_actors import register_handler
    except ModuleNotFoundError:
        from hermes.core.swarm_actors import register_handler

    handlers = {
        "analyze_market": handle_analyze_market,
        "generate_report": handle_generate_report,
        "send_alert": handle_send_alert,
        "snapshot_pnl": handle_snapshot_pnl,
    }
    for name, fn in handlers.items():
        register_handler(name, fn)
    return list(handlers.keys())
