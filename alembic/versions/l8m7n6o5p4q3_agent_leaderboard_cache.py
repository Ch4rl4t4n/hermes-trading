"""agent leaderboard cache + trading_agents.show_in_leaderboard

Revision ID: l8m7n6o5p4q3
Revises: k9l8m7n6o5p4
Create Date: 2026-05-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l8m7n6o5p4q3"
down_revision: Union[str, Sequence[str], None] = "k9l8m7n6o5p4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_leaderboard_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "agent_id",
            sa.String(64),
            sa.ForeignKey("trading_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("pnl_pct", sa.Numeric(8, 4), server_default="0", nullable=False),
        sa.Column("pnl_usd", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("win_rate", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("trade_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("subscriber_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "period", name="uq_agent_leaderboard_cache_agent_period"),
    )
    op.create_index(
        "idx_leaderboard_period_rank",
        "agent_leaderboard_cache",
        ["period", "rank"],
    )
    op.add_column(
        "trading_agents",
        sa.Column(
            "show_in_leaderboard",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_table(
        "leaderboard_cache_meta",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.execute(sa.text("INSERT INTO leaderboard_cache_meta (id) VALUES (1)"))


def downgrade() -> None:
    op.drop_table("leaderboard_cache_meta")
    op.drop_column("trading_agents", "show_in_leaderboard")
    op.drop_index("idx_leaderboard_period_rank", table_name="agent_leaderboard_cache")
    op.drop_table("agent_leaderboard_cache")
