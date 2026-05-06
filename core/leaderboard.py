"""Leaderboard cache: aggregate agent performance from PnL snapshots."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

_VALID_PERIODS = frozenset({"weekly", "monthly", "alltime"})

# Whitelisted DATE filters (avoid dynamic SQL on user input).
_PERIOD_DATE_FILTER_SQL = {
    "weekly": "aps.snapshot_date >= (CURRENT_DATE - INTERVAL '7 days')",
    "monthly": "aps.snapshot_date >= (CURRENT_DATE - INTERVAL '30 days')",
    "alltime": "aps.snapshot_date >= (CURRENT_DATE - INTERVAL '3650 days')",
}


def compute_leaderboard_cache(conn: Connection) -> int:
    """Recompute all periods into ``agent_leaderboard_cache``. Returns rows upserted."""
    total = 0
    for period_name in ("weekly", "monthly", "alltime"):
        total += _compute_one_period(conn, period_name)
    conn.execute(text("UPDATE leaderboard_cache_meta SET refreshed_at = NOW() WHERE id = 1"))
    return total


def _compute_one_period(conn: Connection, period_name: str) -> int:
    if period_name not in _VALID_PERIODS:
        raise ValueError("invalid period")
    date_filter = _PERIOD_DATE_FILTER_SQL[period_name]
    conn.execute(
        text("DELETE FROM agent_leaderboard_cache WHERE period = :period"),
        {"period": period_name},
    )
    rows = conn.execute(
        text(f"""
            WITH agg AS (
              SELECT
                ta.id AS agent_id,
                ta.win_rate::double precision AS ta_win_rate,
                AVG(aps.pnl_pct::numeric)::double precision AS avg_pnl_pct,
                AVG(aps.pnl_usd::numeric)::double precision AS avg_pnl_usd,
                COALESCE(SUM(aps.trade_count), 0)::bigint AS total_trades,
                COUNT(DISTINCT aps.user_id)::int AS subscriber_count
              FROM trading_agents ta
              LEFT JOIN agent_pnl_snapshots aps
                ON aps.agent_id = ta.id
                AND {date_filter}
              WHERE ta.is_active IS TRUE
                AND ta.show_in_leaderboard IS NOT FALSE
              GROUP BY ta.id, ta.win_rate
              HAVING COALESCE(SUM(aps.trade_count), 0) >= 5
            )
            SELECT
              agent_id,
              ta_win_rate,
              avg_pnl_pct,
              avg_pnl_usd,
              total_trades,
              subscriber_count
            FROM agg
            ORDER BY avg_pnl_pct DESC NULLS LAST
            LIMIT 20
        """)
    ).mappings().all()

    rank = 0
    for row in rows:
        rank += 1
        conn.execute(
            text("""
                INSERT INTO agent_leaderboard_cache (
                    agent_id, period, rank, pnl_pct, pnl_usd, win_rate,
                    trade_count, subscriber_count, updated_at
                ) VALUES (
                    :agent_id, :period, :rank, :pnl_pct, :pnl_usd, :win_rate,
                    :trade_count, :subscriber_count, NOW()
                )
                ON CONFLICT (agent_id, period) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    pnl_pct = EXCLUDED.pnl_pct,
                    pnl_usd = EXCLUDED.pnl_usd,
                    win_rate = EXCLUDED.win_rate,
                    trade_count = EXCLUDED.trade_count,
                    subscriber_count = EXCLUDED.subscriber_count,
                    updated_at = NOW()
            """),
            {
                "agent_id": row["agent_id"],
                "period": period_name,
                "rank": rank,
                "pnl_pct": float(row["avg_pnl_pct"] or 0),
                "pnl_usd": float(row["avg_pnl_usd"] or 0),
                "win_rate": float(row["ta_win_rate"] or 0),
                "trade_count": int(row["total_trades"] or 0),
                "subscriber_count": int(row["subscriber_count"] or 0),
            },
        )
    return len(rows)
