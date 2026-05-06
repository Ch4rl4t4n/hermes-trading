"""Community marketplace (user-built agents): publish rules, metrics, listing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import scoped_session

from core.badges import community_badges_for_user_agent
from core.tier_access import (
    TIER_ADMIN,
    TIER_ELITE,
    TIER_PRO,
    effective_tier,
    normalize_tier,
)

_NOTIONAL_EQUITY = 10_000.0


@dataclass
class PublishCheck:
    ok: bool
    errors: list[str]
    trade_count: int
    total_pnl: float
    age_days: float


def can_publish_tier(user: Any) -> bool:
    if bool(getattr(user, "is_admin", False)):
        return True
    t = normalize_tier(effective_tier(user))
    return t in (TIER_PRO, TIER_ELITE, TIER_ADMIN)


def author_tier_public(author_tier: str | None, is_admin: bool) -> str:
    if is_admin:
        return "elite"
    t = normalize_tier(author_tier or "")
    if t == TIER_ELITE:
        return "elite"
    return "pro"


def validate_publish_requirements(
    sess: scoped_session, user_id: int, user_agent_id: int, created_at: datetime | None
) -> PublishCheck:
    errs: list[str] = []
    trade_row = sess.execute(
        text("""
        SELECT COUNT(*)::int AS c, COALESCE(SUM(pnl), 0)::float AS pnl_sum
        FROM paper_trades
        WHERE user_agent_id = :uaid AND user_id = :uid
        """),
        {"uaid": user_agent_id, "uid": user_id},
    ).mappings().first()
    trade_count = int(trade_row["c"]) if trade_row else 0
    total_pnl = float(trade_row["pnl_sum"]) if trade_row and trade_row["pnl_sum"] is not None else 0.0

    age_days = 0.0
    if created_at is not None:
        ca = created_at
        if getattr(ca, "tzinfo", None) is None:
            ca = ca.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - ca).total_seconds() / 86400.0

    if age_days < 14.0:
        errs.append("Agent musí byť aktívny aspoň 14 dní pred publikovaním.")
    if trade_count < 20:
        errs.append(f"Minimálne 20 paper obchodov (aktuálne: {trade_count}).")
    if total_pnl <= 0:
        errs.append("Celkový P&L z paper obchodov musí byť kladný.")

    return PublishCheck(ok=not errs, errors=errs, trade_count=trade_count, total_pnl=total_pnl, age_days=age_days)


def compute_top_gainer_user_agent_ids(sess: scoped_session, ua_ids: list[int]) -> set[int]:
    if not ua_ids:
        return set()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = (
        sess.execute(
            text("""
            SELECT user_agent_id, COALESCE(SUM(pnl), 0)::double precision AS s
            FROM paper_trades
            WHERE user_agent_id = ANY(:ids) AND timestamp >= :since
            GROUP BY user_agent_id
            """),
            {"ids": ua_ids, "since": since},
        )
        .mappings()
        .all()
    )
    best_id: int | None = None
    best_pnl = 0.0
    for r in rows:
        p = float(r["s"] or 0.0)
        if p > best_pnl:
            best_pnl = p
            best_id = int(r["user_agent_id"]) if r["user_agent_id"] is not None else None
    if best_id is not None and best_pnl > 0:
        return {best_id}
    return set()


def _metric_subqueries() -> str:
    return """
        (SELECT COUNT(*)::int FROM paper_trades pt
         WHERE pt.user_agent_id = ua.id AND pt.user_id = ua.user_id) AS trade_count,
        (SELECT COALESCE(SUM(pt.pnl), 0)::double precision FROM paper_trades pt
         WHERE pt.user_agent_id = ua.id AND pt.user_id = ua.user_id) AS total_pnl,
        (SELECT COALESCE(SUM(pt.pnl), 0)::double precision FROM paper_trades pt
         WHERE pt.user_agent_id = ua.id AND pt.user_id = ua.user_id
           AND pt.timestamp >= (CURRENT_TIMESTAMP - INTERVAL '7 days')) AS pnl_usd_week,
        (SELECT COALESCE(SUM(pt.pnl), 0)::double precision FROM paper_trades pt
         WHERE pt.user_agent_id = ua.id AND pt.user_id = ua.user_id
           AND pt.timestamp >= (CURRENT_TIMESTAMP - INTERVAL '30 days')) AS pnl_usd_month,
        (SELECT CASE WHEN COUNT(*) = 0 THEN 0.0
            ELSE (100.0 * SUM(CASE WHEN pt.pnl > 0 THEN 1 ELSE 0 END) / COUNT(*))::double precision END
         FROM paper_trades pt
         WHERE pt.user_agent_id = ua.id AND pt.user_id = ua.user_id) AS win_rate
    """


def fetch_approved_agent_by_public_id(sess: scoped_session, public_id: Any) -> Optional[dict[str, Any]]:
    row = (
        sess.execute(
            text(f"""
            SELECT ua.*, u.tier AS author_db_tier, u.is_admin AS author_is_admin,
                   {_metric_subqueries()}
            FROM user_agents ua
            JOIN users u ON u.id = ua.user_id
            WHERE ua.public_id = CAST(:pid AS uuid)
              AND ua.marketplace_status = 'approved'
              AND ua.is_public IS TRUE
              AND ua.status != 'deleted'
            """),
            {"pid": str(public_id).strip()},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def fetch_approved_listing_candidates(
    sess: scoped_session,
    *,
    symbol_filter: str | None,
    strategy_filter: str | None,
) -> list[dict[str, Any]]:
    where = [
        "ua.marketplace_status = 'approved'",
        "ua.is_public IS TRUE",
        "ua.status != 'deleted'",
    ]
    params: dict[str, Any] = {}
    if symbol_filter:
        where.append("UPPER(REPLACE(ua.symbol, '/', '')) LIKE :sym_like")
        params["sym_like"] = f"%{symbol_filter.strip().upper().replace('/', '')}%"
    if strategy_filter:
        where.append("ua.strategy_type = :stype")
        params["stype"] = strategy_filter.strip().lower()
    w = " AND ".join(where)
    sql = f"""
        SELECT ua.*, u.tier AS author_db_tier, u.is_admin AS author_is_admin,
               {_metric_subqueries()}
        FROM user_agents ua
        JOIN users u ON u.id = ua.user_id
        WHERE {w}
    """
    rows = sess.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def sort_listing_rows(rows: list[dict[str, Any]], sort_key: str) -> list[dict[str, Any]]:
    sk = (sort_key or "pnl_week").strip().lower()
    if sk == "pnl_month":
        return sorted(rows, key=lambda r: float(r.get("pnl_usd_month") or 0.0), reverse=True)
    if sk == "popularity":
        return sorted(
            rows,
            key=lambda r: (int(r.get("popularity_score") or 0), int(r.get("clone_count") or 0)),
            reverse=True,
        )
    if sk == "newest":
        return sorted(rows, key=lambda r: str(r.get("published_at") or ""), reverse=True)
    # default pnl_week
    return sorted(rows, key=lambda r: float(r.get("pnl_usd_week") or 0.0), reverse=True)


def enrich_listing_for_api(
    sess: scoped_session,
    row: dict[str, Any],
    *,
    viewer_user_id: int | None,
    top_gainers: set[int],
) -> dict[str, Any]:
    ua_id = int(row["id"])
    author_id = int(row["user_id"])
    pid = row.get("public_id")
    public_s = str(pid) if pid is not None else ""
    if hasattr(pid, "hex"):
        public_s = str(pid)

    week = float(row.get("pnl_usd_week") or 0.0)
    month = float(row.get("pnl_usd_month") or 0.0)
    pnl_pct_week = (week / _NOTIONAL_EQUITY) * 100.0 if _NOTIONAL_EQUITY else 0.0
    pnl_pct_month = (month / _NOTIONAL_EQUITY) * 100.0 if _NOTIONAL_EQUITY else 0.0

    badges = community_badges_for_user_agent(
        sess, author_id, ua_id, top_gainer_ids=top_gainers
    )
    author_tier = author_tier_public(row.get("author_db_tier"), bool(row.get("author_is_admin")))

    has_clone: Optional[bool] = None
    if viewer_user_id is not None:
        mc = sess.execute(
            text("""
            SELECT 1 FROM marketplace_clones
            WHERE source_agent_id = :sid AND cloned_by_user_id = :uid
            LIMIT 1
            """),
            {"sid": ua_id, "uid": viewer_user_id},
        ).first()
        has_clone = mc is not None

    pub = row.get("published_at")
    if hasattr(pub, "isoformat"):
        pub = pub.isoformat()

    return {
        "id": ua_id,
        "public_id": public_s,
        "name": row.get("name"),
        "symbol": row.get("symbol"),
        "strategy_type": row.get("strategy_type"),
        "description": row.get("description"),
        "published_at": pub,
        "clone_count": int(row.get("clone_count") or 0),
        "popularity_score": int(row.get("popularity_score") or 0),
        "pnl_pct_week": round(pnl_pct_week, 4),
        "pnl_pct_month": round(pnl_pct_month, 4),
        "pnl_usd_week": round(week, 4),
        "win_rate": float(row.get("win_rate") or 0.0),
        "trade_count": int(row.get("trade_count") or 0),
        "author_tier": author_tier,
        "badges": badges,
        "user_has_clone": has_clone,
    }


def recent_trades_for_listing(sess: scoped_session, user_agent_id: int, author_user_id: int, limit: int = 10):
    rows = sess.execute(
        text("""
        SELECT id, symbol, action, price, quantity, pnl, timestamp, reason
        FROM paper_trades
        WHERE user_agent_id = :uaid AND user_id = :uid
        ORDER BY timestamp DESC
        LIMIT :lim
        """),
        {"uaid": user_agent_id, "uid": author_user_id, "lim": limit},
    ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        ts = d.get("timestamp")
        if hasattr(ts, "isoformat"):
            d["timestamp"] = ts.isoformat()
        out.append(d)
    return out
