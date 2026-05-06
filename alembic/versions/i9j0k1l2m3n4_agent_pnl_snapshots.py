"""agent_pnl_snapshots — live P&L history per user + agent

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-05-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_pnl_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "agent_id",
            sa.String(64),
            sa.ForeignKey("trading_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("pnl_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("pnl_pct", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("equity", sa.Numeric(12, 2), nullable=False, server_default="10000"),
        sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "user_id", "snapshot_date", name="uq_agent_pnl_snapshots_agent_user_date"),
    )
    op.create_index(
        "idx_pnl_user_date",
        "agent_pnl_snapshots",
        ["user_id", "snapshot_date"],
    )
    op.create_index("idx_pnl_agent", "agent_pnl_snapshots", ["agent_id"])


def downgrade() -> None:
    op.drop_index("idx_pnl_agent", table_name="agent_pnl_snapshots")
    op.drop_index("idx_pnl_user_date", table_name="agent_pnl_snapshots")
    op.drop_table("agent_pnl_snapshots")
