"""Agent marketplace: catalog, subscriptions, paper-trade P&L aggregation."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

import core.database as db
from core.models import User
from core.tier_access import (
    TIER_RANK,
    effective_tier,
    effective_max_marketplace_agents,
    features_payload,
    normalize_tier,
    referral_extra_agent_slots,
)
from core.trade_reasons import generate_trade_reason

TIER_VISIBILITY: dict[str, list[str]] = {
    "basic": ["basic"],
    "medium": ["basic", "medium"],
    "pro": ["basic", "medium", "pro"],
    "elite": ["basic", "medium", "pro", "elite"],
    "admin": ["basic", "medium", "pro", "elite", "admin"],
}

# Per-category slot ceilings for dashboard UI (aligned with tier positioning).
TIER_CATEGORY_SLOTS: dict[str, dict[str, int]] = {
    "basic": {"crypto": 2, "stock": 2, "commodity": 1, "total": 3},
    "medium": {"crypto": 4, "stock": 4, "commodity": 2, "total": 8},
    "pro": {"crypto": 8, "stock": 8, "commodity": 4, "total": 10},
    "elite": {"crypto": 99, "stock": 99, "commodity": 99, "total": 999},
    "admin": {"crypto": 99, "stock": 99, "commodity": 99, "total": 99},
}

TIER_UPGRADE_NEXT: dict[str, str] = {
    "basic": "medium",
    "medium": "pro",
    "pro": "elite",
}

# Preset marketplace agents for onboarding (ids must match ``trading_agents.id`` seeds).
DEMO_AGENTS: dict[str, str] = {
    "crypto": "btc_momentum",
    "stock": "spy_index",
    "commodity": "gold_safe",
}


def assign_demo_agents(user_id: int, db_conn) -> list[str]:
    """Attach default paper subscriptions for one user per category; return assigned agent ids.

    ``db_conn`` is a SQLAlchemy 2.0 :class:`~sqlalchemy.engine.Connection` (e.g. from
    ``with engine.begin() as conn``). Safe to call in its own transaction.
    """
    dialect = getattr(getattr(db_conn, "dialect", None), "name", "") or "default"
    active = _active_predicate(dialect)
    assigned: list[str] = []

    for category, preferred_agent_id in DEMO_AGENTS.items():
        agent_row = db_conn.execute(
            text(f"""
            SELECT id FROM trading_agents
            WHERE id = :preferred AND {active}
            LIMIT 1
            """),
            {"preferred": preferred_agent_id},
        ).fetchone()
        if not agent_row:
            agent_row = db_conn.execute(
                text(f"""
                SELECT id FROM trading_agents
                WHERE category = :cat AND {active}
                ORDER BY win_rate DESC
                LIMIT 1
                """),
                {"cat": category},
            ).fetchone()
        if not agent_row:
            continue

        agent_id = str(agent_row[0])

        sub = db_conn.execute(
            text("""
            SELECT is_active FROM user_subscriptions
            WHERE user_id = :uid AND agent_id = :aid
            """),
            {"uid": user_id, "aid": agent_id},
        ).mappings().first()
        if sub and bool(sub["is_active"]):
            continue

        db_conn.execute(
            text("""
            INSERT INTO user_subscriptions (user_id, agent_id, mode, is_active)
            VALUES (:uid, :aid, 'paper', TRUE)
            ON CONFLICT (user_id, agent_id) DO UPDATE
            SET is_active = TRUE, mode = 'paper'
            """),
            {"uid": user_id, "aid": agent_id},
        )
        assigned.append(agent_id)

        info = db_conn.execute(
            text("SELECT name, symbol FROM trading_agents WHERE id = :aid"),
            {"aid": agent_id},
        ).mappings().first()
        if info:
            db_conn.execute(
                text("""
                INSERT INTO notifications (user_id, type, title, message)
                VALUES (:uid, 'demo_agent', :title, :msg)
                """),
                {
                    "uid": user_id,
                    "title": f"Uvítací agent: {info['name']}",
                    "msg": (
                        f"Priradili sme ti demo agenta {info['name']} "
                        f"({info['symbol']}) v paper trading móde. "
                        f"Sleduj jeho výkonnosť v dashboarde!"
                    ),
                },
            )

    return assigned


def _active_predicate(dialect_name: str) -> str:
    if dialect_name == "sqlite":
        return "(is_active = 1 OR is_active = true)"
    return "is_active IS TRUE"


def get_all_agents(category: str | None = None, tier_filter: str | None = None) -> list[dict[str, Any]]:
    sess = db.db_session()
    dialect = sess.get_bind().dialect.name
    active = _active_predicate(dialect)
    q = f"SELECT * FROM trading_agents WHERE {active}"
    params: dict[str, Any] = {}
    if category and category != "all":
        q += " AND category = :cat"
        params["cat"] = category
    if tier_filter:
        tf = normalize_tier(tier_filter)
        allowed = TIER_VISIBILITY.get(tf, ["basic"])
        ph = ", ".join(f":t{i}" for i in range(len(allowed)))
        q += f" AND min_tier IN ({ph})"
        for i, t in enumerate(allowed):
            params[f"t{i}"] = t
    q += " ORDER BY category, min_tier, win_rate DESC"
    rows = sess.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


def get_user_subscriptions(user_id: int) -> list[dict[str, Any]]:
    sess = db.db_session()
    rows = sess.execute(
        text("""
        SELECT us.*, ta.name, ta.symbol, ta.category, ta.strategy, ta.risk_level, ta.win_rate, ta.min_tier
        FROM user_subscriptions us
        JOIN trading_agents ta ON us.agent_id = ta.id
        WHERE us.user_id = :uid AND us.is_active = :active
        ORDER BY us.subscribed_at DESC
        """),
        {"uid": user_id, "active": True},
    ).mappings().all()
    return [dict(r) for r in rows]


def subscribe_agent(user_id: int, agent_id: str, mode: str = "paper") -> dict[str, Any]:
    sess = db.db_session()
    user = sess.get(User, user_id)
    if not user:
        return {"success": False, "error": "User not found"}
    feats = features_payload(user)
    row = sess.execute(
        text("""
        SELECT COUNT(*) AS cnt FROM user_subscriptions
        WHERE user_id = :uid AND is_active = :active
        """),
        {"uid": user_id, "active": True},
    ).mappings().first()
    cnt = int(row["cnt"]) if row else 0
    max_agents = effective_max_marketplace_agents(user)
    if isinstance(max_agents, int) and cnt >= max_agents:
        ut = normalize_tier(user.tier)
        return {
            "success": False,
            "error": "slot_limit_reached",
            "message": f"Tvoj {ut} plán umožňuje max {max_agents} agentov.",
            "upgrade_required": True,
            "current_tier": ut,
        }

    agent = sess.execute(
        text("SELECT * FROM trading_agents WHERE id = :aid"),
        {"aid": agent_id},
    ).mappings().first()
    if not agent:
        return {"success": False, "error": "Agent not found"}

    user_tier = normalize_tier(feats.get("tier", "basic"))
    need_tier = normalize_tier(agent["min_tier"])
    if TIER_RANK.get(need_tier, 0) > TIER_RANK.get(user_tier, 0):
        return {"success": False, "error": f"This agent requires {need_tier} tier"}

    if mode == "live" and not feats.get("real_money"):
        return {"success": False, "error": "Live trading requires Pro tier"}

    row = sess.execute(
        text("""
        SELECT id FROM user_subscriptions WHERE user_id = :uid AND agent_id = :aid
        """),
        {"uid": user_id, "aid": agent_id},
    ).first()
    existing = row[0] if row is not None else None

    if existing is not None:
        sess.execute(
            text("""
            UPDATE user_subscriptions
            SET is_active = :on, mode = :mode
            WHERE user_id = :uid AND agent_id = :aid
            """),
            {"uid": user_id, "aid": agent_id, "mode": mode, "on": True},
        )
    else:
        sess.execute(
            text("""
            INSERT INTO user_subscriptions (user_id, agent_id, mode) VALUES (:uid, :aid, :mode)
            """),
            {"uid": user_id, "aid": agent_id, "mode": mode},
        )
    sess.commit()
    return {"success": True, "message": f"Subscribed to {agent['name']}"}


def unsubscribe_agent(user_id: int, agent_id: str) -> dict[str, Any]:
    sess = db.db_session()
    sess.execute(
        text("""
        UPDATE user_subscriptions SET is_active = :off WHERE user_id = :uid AND agent_id = :aid
        """),
        {"uid": user_id, "aid": agent_id, "off": False},
    )
    sess.commit()
    return {"success": True}


def record_paper_trade(
    user_id: int,
    agent_id: str | None,
    symbol: str,
    action: str,
    price: float,
    quantity: float,
    pnl: float = 0.0,
    *,
    user_agent_id: int | None = None,
    agent_row: dict[str, Any] | None = None,
    write_explanation: bool = True,
) -> dict[str, Any]:
    """Insert a paper trade with synthetic reason/signals; optional ``trade_explanations`` row."""
    sess = db.db_session()
    act = (action or "buy").strip().lower()
    if act not in ("buy", "sell"):
        raise ValueError("action must be buy or sell")
    if (agent_id is None) == (user_agent_id is None):
        raise ValueError("exactly one of agent_id or user_agent_id must be set")

    agent = agent_row
    if agent is None and agent_id is not None:
        row = sess.execute(
            text("SELECT * FROM trading_agents WHERE id = :aid"),
            {"aid": agent_id},
        ).mappings().first()
        agent = dict(row) if row else {}
    if agent is None:
        agent = {}

    gen = generate_trade_reason(agent, act, symbol, float(price), float(pnl))
    reason = gen["reason"]
    signals = gen["signals"]
    confidence = float(gen["confidence"])

    tid = sess.execute(
        text("""
            INSERT INTO paper_trades (
                user_id, agent_id, user_agent_id, symbol, action, price, quantity, pnl,
                reason, signals, confidence
            ) VALUES (
                :uid, :aid, :uaid, :sym, :act, :price, :qty, :pnl,
                :reason, CAST(:signals AS jsonb), :confidence
            )
            RETURNING id
        """),
        {
            "uid": user_id,
            "aid": agent_id,
            "uaid": user_agent_id,
            "sym": symbol,
            "act": act,
            "price": float(price),
            "qty": float(quantity),
            "pnl": float(pnl),
            "reason": reason,
            "signals": json.dumps(signals),
            "confidence": confidence,
        },
    ).scalar()

    if write_explanation and tid is not None:
        sess.execute(
            text("""
                INSERT INTO trade_explanations (trade_id, explanation, signals)
                VALUES (:tid, :ex, CAST(:sig AS jsonb))
            """),
            {
                "tid": int(tid),
                "ex": reason,
                "sig": json.dumps(signals),
            },
        )
    sess.commit()
    return {"trade_id": int(tid) if tid is not None else None, **gen}


def get_user_pnl(user_id: int) -> list[dict[str, Any]]:
    sess = db.db_session()
    rows = sess.execute(
        text("""
        SELECT agent_id, symbol, SUM(pnl) AS total_pnl, COUNT(*) AS trades
        FROM paper_trades WHERE user_id = :uid
        GROUP BY agent_id, symbol
        """),
        {"uid": user_id},
    ).mappings().all()
    return [dict(r) for r in rows]


PNL_BASELINE_USD = 10000.0


def _iso_ts_utc(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        s = v.isoformat()
        if s.endswith("+00:00"):
            return s.replace("+00:00", "Z")
        return s
    return None


def get_live_pnl_payload(user_id: int) -> dict[str, Any]:
    """Aggregated live P&L for active marketplace subscriptions (snapshots + paper_trades)."""
    sess = db.db_session()
    subs = get_user_subscriptions(user_id)
    if not subs:
        return {"pnl": {}, "total_pnl_usd": 0.0, "best_agent_id": None}

    snapshots: dict[str, dict[str, Any]] = {}
    try:
        rows = sess.execute(
            text("""
            SELECT agent_id, pnl_usd, pnl_pct, trade_count, win_count, created_at
            FROM (
                SELECT agent_id, pnl_usd, pnl_pct, trade_count, win_count, created_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY agent_id
                           ORDER BY snapshot_date DESC, created_at DESC
                       ) AS rn
                FROM agent_pnl_snapshots
                WHERE user_id = :uid
            ) t
            WHERE rn = 1
            """),
            {"uid": user_id},
        ).mappings().all()
        for r in rows:
            snapshots[str(r["agent_id"])] = dict(r)
    except (ProgrammingError, OperationalError):
        sess.rollback()
        snapshots = {}

    pnl_out: dict[str, dict[str, Any]] = {}
    total = 0.0
    best_aid: str | None = None
    best_val: float | None = None

    for s in subs:
        aid = str(s["agent_id"])
        today_row = sess.execute(
            text("""
            SELECT COALESCE(SUM(pnl), 0) AS t
            FROM paper_trades
            WHERE user_id = :u AND agent_id = :a
              AND (timestamp AT TIME ZONE 'UTC')::date = ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date)
            """),
            {"u": user_id, "a": aid},
        ).mappings().first()
        today_pnl = float(today_row["t"] or 0) if today_row else 0.0

        sn = snapshots.get(aid)
        if sn is not None:
            pnl_usd = float(sn["pnl_usd"] or 0)
            pnl_pct = float(sn["pnl_pct"] or 0)
            tc = int(sn["trade_count"] or 0)
            wc = int(sn["win_count"] or 0)
            lu = sn["created_at"]
        else:
            agg = sess.execute(
                text("""
                SELECT COALESCE(SUM(pnl), 0) AS total,
                       COUNT(*)::int AS ntr,
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0)::int AS nw,
                       MAX(timestamp) AS ts
                FROM paper_trades
                WHERE user_id = :u AND agent_id = :a
                """),
                {"u": user_id, "a": aid},
            ).mappings().first()
            pnl_usd = float(agg["total"] or 0) if agg else 0.0
            tc = int(agg["ntr"] or 0) if agg else 0
            wc = int(agg["nw"] or 0) if agg else 0
            lu = agg["ts"] if agg else None
            pnl_pct = (pnl_usd / PNL_BASELINE_USD * 100.0) if PNL_BASELINE_USD else 0.0

        win_rate = (wc / tc * 100.0) if tc > 0 else 0.0
        pnl_out[aid] = {
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 4),
            "today_pnl": round(today_pnl, 2),
            "trade_count": tc,
            "win_rate": round(win_rate, 1),
            "last_updated": _iso_ts_utc(lu),
        }
        total += pnl_usd
        if best_val is None or pnl_usd > best_val:
            best_val = pnl_usd
            best_aid = aid

    return {
        "pnl": pnl_out,
        "total_pnl_usd": round(total, 2),
        "best_agent_id": best_aid,
    }


def get_marketplace_slots(user: User) -> dict[str, Any]:
    """Return per-category subscription usage vs tier limits for the dashboard."""
    feats = features_payload(user)
    t = normalize_tier(feats.get("tier", "basic"))
    limits = dict(TIER_CATEGORY_SLOTS.get(t, TIER_CATEGORY_SLOTS["basic"]))
    ex = referral_extra_agent_slots(user)
    if ex and limits.get("total", 0) < 9000:
        limits = {k: int(v) + ex for k, v in limits.items()}
    sess = db.db_session()
    rows = sess.execute(
        text("""
        SELECT ta.category, COUNT(*) AS cnt
        FROM user_subscriptions us
        JOIN trading_agents ta ON us.agent_id = ta.id
        WHERE us.user_id = :uid AND us.is_active = :active
        GROUP BY ta.category
        """),
        {"uid": user.id, "active": True},
    ).mappings().all()
    used_by_cat: dict[str, int] = {}
    for r in rows:
        used_by_cat[str(r["category"])] = int(r["cnt"])
    uc = used_by_cat.get("crypto", 0)
    us = used_by_cat.get("stock", 0)
    uco = used_by_cat.get("commodity", 0)
    total_used = uc + us + uco
    next_key = TIER_UPGRADE_NEXT.get(t)
    next_limits: dict[str, int] | None = None
    if next_key:
        nl = TIER_CATEGORY_SLOTS.get(next_key)
        if nl is not None:
            next_limits = dict(nl)
    return {
        "tier": t,
        "tier_display": feats.get("tier_display"),
        "agents_limit": feats.get("agents_limit"),
        "history_days": feats.get("history_days"),
        "real_money": feats.get("real_money"),
        "crypto": {"used": uc, "limit": limits["crypto"]},
        "stock": {"used": us, "limit": limits["stock"]},
        "commodity": {"used": uco, "limit": limits["commodity"]},
        "total": {"used": total_used, "limit": limits["total"]},
        "next_tier": next_key,
        "next_limits": next_limits,
    }
