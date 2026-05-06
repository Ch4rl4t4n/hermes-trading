"""historical_candles cache + backtest_results

Revision ID: t9u0v1w2x3y4
Revises: s8t9u0v1w2x3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "t9u0v1w2x3y4"
down_revision: Union[str, Sequence[str], None] = "s8t9u0v1w2x3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historical_candles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=True),
        sa.Column("high", sa.Numeric(20, 8), nullable=True),
        sa.Column("low", sa.Numeric(20, 8), nullable=True),
        sa.Column("close", sa.Numeric(20, 8), nullable=True),
        sa.Column("volume", sa.Numeric(20, 8), nullable=True),
        sa.UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_historical_candles_sym_tf_ts"),
    )
    op.create_index(
        "ix_historical_candles_sym_tf_ts_desc",
        "historical_candles",
        ["symbol", "timeframe", "timestamp"],
        postgresql_ops={"timestamp": "DESC"},
    )

    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_type", sa.String(20), nullable=False),
        sa.Column("user_agent_id", sa.Integer(), sa.ForeignKey("user_agents.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "trading_agent_id",
            sa.String(64),
            sa.ForeignKey("trading_agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(user_agent_id IS NOT NULL AND trading_agent_id IS NULL) OR "
            "(user_agent_id IS NULL AND trading_agent_id IS NOT NULL)",
            name="ck_backtest_results_one_agent_ref",
        ),
    )
    op.create_index("ix_backtest_results_user_id", "backtest_results", ["user_id"])
    op.create_index(
        "ix_backtest_results_user_created",
        "backtest_results",
        ["user_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_results_user_created", table_name="backtest_results")
    op.drop_index("ix_backtest_results_user_id", table_name="backtest_results")
    op.drop_table("backtest_results")
    op.drop_index("ix_historical_candles_sym_tf_ts_desc", table_name="historical_candles")
    op.drop_table("historical_candles")
