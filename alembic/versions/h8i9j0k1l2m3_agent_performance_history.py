"""agent_performance daily history (per user + trading agent)

Revision ID: h8i9j0k1l2m3
Revises: g2h3i4j5k6l7
Create Date: 2026-05-04

Note: agent_id is VARCHAR(64) to match trading_agents.ic, not INTEGER.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_performance",
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
        sa.Column(
            "date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("pnl_pct", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("pnl_abs", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id",
            "user_id",
            "date",
            name="uq_agent_performance_agent_user_date",
        ),
    )
    op.create_index(
        "idx_ap_agent_date",
        "agent_performance",
        ["agent_id", "date"],
        postgresql_ops={"date": "DESC"},
    )
    op.create_index("idx_ap_user", "agent_performance", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_ap_user", table_name="agent_performance")
    op.drop_index("idx_ap_agent_date", table_name="agent_performance")
    op.drop_table("agent_performance")
