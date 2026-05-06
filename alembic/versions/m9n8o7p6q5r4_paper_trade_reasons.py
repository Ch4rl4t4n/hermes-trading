"""paper_trades reason/signals/confidence + trade_explanations

Revision ID: m9n8o7p6q5r4
Revises: l8m7n6o5p4q3
Create Date: 2026-05-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "m9n8o7p6q5r4"
down_revision: Union[str, Sequence[str], None] = "l8m7n6o5p4q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paper_trades", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column(
        "paper_trades",
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "paper_trades",
        sa.Column("confidence", sa.Numeric(5, 2), server_default="0", nullable=False),
    )

    op.create_table(
        "trade_explanations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "trade_id",
            sa.Integer(),
            sa.ForeignKey("paper_trades.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_te_trade", "trade_explanations", ["trade_id"])


def downgrade() -> None:
    op.drop_index("idx_te_trade", table_name="trade_explanations")
    op.drop_table("trade_explanations")
    op.drop_column("paper_trades", "confidence")
    op.drop_column("paper_trades", "signals")
    op.drop_column("paper_trades", "reason")
