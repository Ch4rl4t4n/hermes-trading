"""Agent badge rules derived from paper-trades history (no separate performance table)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import scoped_session

BADGE_DEFINITIONS: dict[str, dict[str, str]] = {
    "top_gainer_24h": {
        "label": "Top Gainer",
        "icon": "🔥",
        "color": "#f97316",
        "desc": "Najvyšší zisk za 24h",
    },
    "hot_streak_3d": {
        "label": "Hot Streak",
        "icon": "⚡",
        "color": "#8b5cf6",
        "desc": "3 dni v zelenom",
    },
    "steady_7d": {
        "label": "Steady",
        "icon": "🛡",
        "color": "#10b981",
        "desc": "7 dní bez straty",
    },
    "reliable": {
        "label": "Reliable",
        "icon": "✓",
        "color": "#6366f1",
        "desc": "Vysoký uptime",
    },
}


def _date_from_ts(ts: Any) -> date:
    if ts is None:
        return datetime.now(timezone.utc).date()
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            return ts.astimezone(timezone.utc).date()
        return ts.date()
    if isinstance(ts, date):
        return ts
    s = str(ts)[:10]
    return date.fromisoformat(s)


def fetch_daily_performance_rows(sess: scoped_session, user_id: int, agent_id: str) -> list[dict[str, Any]]:
    """
    Build newest-first rows: { 'date': datetime (UTC midnight), 'pnl_pct': float, 'is_active': bool }
    Daily % is rough: day_pnl / max(1, abs(cumulative_pnl_before_that_day)) * 100.
    """
    rows = (
        sess.execute(
            text("""
            SELECT timestamp, pnl FROM paper_trades
            WHERE user_id = :uid AND agent_id = :aid
            ORDER BY timestamp ASC
            """),
            {"uid": user_id, "aid": agent_id},
        )
        .mappings()
        .all()
    )
    by_day: dict[date, float] = defaultdict(float)
    for row in rows:
        d = _date_from_ts(row["timestamp"])
        by_day[d] += float(row["pnl"] or 0)

    if not by_day:
        return []

    days_asc = sorted(by_day.keys())
    cum_before: dict[date, float] = {}
    run = 0.0
    for d in days_asc:
        cum_before[d] = run
        run += by_day[d]

    out: list[dict[str, Any]] = []
    for d in sorted(by_day.keys(), reverse=True):
        daily = by_day[d]
        base = max(1.0, abs(cum_before[d]))
        pnl_pct = (daily / base) * 100.0
        dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        out.append({"date": dt, "pnl_pct": pnl_pct, "is_active": True})
    return out


def fetch_daily_performance_rows_for_user_agent(
    sess: scoped_session, user_id: int, user_agent_id: int
) -> list[dict[str, Any]]:
    """Same shape as fetch_daily_performance_rows, for builder agents (paper_trades.user_agent_id)."""
    rows = (
        sess.execute(
            text("""
            SELECT timestamp, pnl FROM paper_trades
            WHERE user_id = :uid AND user_agent_id = :uaid
            ORDER BY timestamp ASC
            """),
            {"uid": user_id, "uaid": user_agent_id},
        )
        .mappings()
        .all()
    )
    by_day: dict[date, float] = defaultdict(float)
    for row in rows:
        d = _date_from_ts(row["timestamp"])
        by_day[d] += float(row["pnl"] or 0)

    if not by_day:
        return []

    days_asc = sorted(by_day.keys())
    cum_before: dict[date, float] = {}
    run = 0.0
    for d in days_asc:
        cum_before[d] = run
        run += by_day[d]

    out: list[dict[str, Any]] = []
    for d in sorted(by_day.keys(), reverse=True):
        daily = by_day[d]
        base = max(1.0, abs(cum_before[d]))
        pnl_pct = (daily / base) * 100.0
        dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        out.append({"date": dt, "pnl_pct": pnl_pct, "is_active": True})
    return out


def community_badges_for_user_agent(
    sess: scoped_session,
    author_user_id: int,
    user_agent_id: int,
    *,
    top_gainer_ids: set[int],
) -> list[dict[str, str]]:
    perf = fetch_daily_performance_rows_for_user_agent(sess, author_user_id, user_agent_id)
    base_ids = list(compute_badges_for_agent(str(user_agent_id), perf))
    if user_agent_id in top_gainer_ids and "top_gainer_24h" not in base_ids:
        base_ids.insert(0, "top_gainer_24h")
    return badge_payloads(base_ids)


def compute_badges_for_agent(
    agent_id: str, performance_rows: list[Mapping[str, Any]] | list[dict[str, Any]]
) -> list[str]:
    """
    performance_rows: dicts with keys date (datetime), pnl_pct (float), is_active (bool).
    Returns badge id strings earned from time-series rules (not top_gainer_24h).
    """
    del agent_id  # reserved for future per-agent rules
    badges: list[str] = []
    if not performance_rows:
        return badges

    rows = sorted(performance_rows, key=lambda r: r["date"], reverse=True)

    streak = 0
    for r in rows[:7]:
        if float(r["pnl_pct"]) > 0:
            streak += 1
        else:
            break
    if streak >= 3:
        badges.append("hot_streak_3d")

    if len(rows) >= 7 and all(float(r["pnl_pct"]) >= 0 for r in rows[:7]):
        badges.append("steady_7d")

    if len(rows) >= 14:
        active_ratio = sum(1 for r in rows[:30] if r.get("is_active", True)) / min(len(rows), 30)
        if active_ratio >= 0.90:
            badges.append("reliable")

    return badges


def _paper_pnl_sum_since(sess: scoped_session, user_id: int, agent_id: str, since: datetime) -> float:
    row = sess.execute(
        text("""
        SELECT COALESCE(SUM(pnl), 0) AS s FROM paper_trades
        WHERE user_id = :uid AND agent_id = :aid AND timestamp >= :since
        """),
        {"uid": user_id, "aid": agent_id, "since": since},
    ).mappings().first()
    return float(row["s"]) if row else 0.0


def compute_top_gainers_24h(sess: scoped_session, user_id: int) -> set[str]:
    """
    Subscribed agents only; winner = highest SUM(pnl) over last 24h.
    Returns set of agent_id (str) with strictly positive best PnL (at most one).
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    subs = sess.execute(
        text("""
        SELECT DISTINCT agent_id FROM user_subscriptions
        WHERE user_id = :uid AND is_active = :active
        """),
        {"uid": user_id, "active": True},
    ).mappings().all()
    if not subs:
        return set()

    best_id: str | None = None
    best_pnl = 0.0
    for s in subs:
        aid = str(s["agent_id"])
        pnl = _paper_pnl_sum_since(sess, user_id, aid, since)
        if pnl > best_pnl:
            best_pnl = pnl
            best_id = aid

    if best_id is not None and best_pnl > 0:
        return {best_id}
    return set()


def merge_badge_ids(series_badges: list[str], top_gainer_ids: set[str], agent_id: str) -> list[str]:
    out = list(series_badges)
    if agent_id in top_gainer_ids and "top_gainer_24h" not in out:
        out.insert(0, "top_gainer_24h")
    return out


def badge_payloads(badge_ids: list[str]) -> list[dict[str, str]]:
    """Map ids to definition dicts for API/JSON (skip unknown)."""
    return [dict(BADGE_DEFINITIONS[bid], id=bid) for bid in badge_ids if bid in BADGE_DEFINITIONS]


def compute_all_badge_ids_for_agent(sess: scoped_session, user_id: int, agent_id: str) -> list[str]:
    """Load trades, apply series rules + 24h top gainer."""
    rows = fetch_daily_performance_rows(sess, user_id, agent_id)
    base = compute_badges_for_agent(agent_id, rows)
    top = compute_top_gainers_24h(sess, user_id)
    return merge_badge_ids(base, top, agent_id)


def compute_user_badges_map(sess: scoped_session, user_id: int) -> dict[str, list[str]]:
    """agent_id -> badge id list for all active subscriptions."""
    subs = sess.execute(
        text("""
        SELECT agent_id FROM user_subscriptions
        WHERE user_id = :uid AND is_active = :active
        """),
        {"uid": user_id, "active": True},
    ).mappings().all()
    if not subs:
        return {}
    top = compute_top_gainers_24h(sess, user_id)
    out: dict[str, list[str]] = {}
    for s in subs:
        aid = str(s["agent_id"])
        rows = fetch_daily_performance_rows(sess, user_id, aid)
        base = compute_badges_for_agent(aid, rows)
        out[aid] = merge_badge_ids(base, top, aid)
    return out


# Alias for API / older import names
compute_top_gainers = compute_top_gainers_24h


def grouped_performance_from_table(
    sess: scoped_session, user_id: int, days: int = 30
) -> dict[str, list[dict[str, Any]]] | None:
    """
    Load agent_performance rows grouped by agent_id (newest-first per agent).
    Returns None if the table is missing or query fails (caller may fall back to paper_trades).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    try:
        rows = (
            sess.execute(
                text("""
                SELECT agent_id, date, pnl_pct, is_active
                FROM agent_performance
                WHERE user_id = :uid AND date >= :since
                ORDER BY agent_id ASC, date DESC
                """),
                {"uid": user_id, "since": since},
            )
            .mappings()
            .all()
        )
    except Exception:
        return None

    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        aid = str(r["agent_id"])
        d = r["date"]
        if isinstance(d, datetime):
            dt = d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)
        elif isinstance(d, date):
            dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
        by_agent[aid].append(
            {
                "date": dt,
                "pnl_pct": float(r["pnl_pct"] or 0),
                "is_active": bool(r.get("is_active", True)),
            }
        )
    return dict(by_agent)
