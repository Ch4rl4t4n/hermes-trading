"""user_agents table + paper_trades.user_agent_id, nullable agent_id."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "o1p2q3r4s5t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_agents",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("strategy_type", sa.String(50), nullable=False),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=True,
        ),
        sa.Column("marketplace_status", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_user_agents_user_id", "user_agents", ["user_id"])
    op.create_index("ix_user_agents_status", "user_agents", ["status"])

    op.alter_column(
        "paper_trades",
        "agent_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.add_column(
        "paper_trades",
        sa.Column(
            "user_agent_id",
            sa.Integer(),
            sa.ForeignKey("user_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_paper_trades_user_agent_id", "paper_trades", ["user_agent_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_trades_user_agent_id", table_name="paper_trades")
    op.drop_column("paper_trades", "user_agent_id")
    op.alter_column(
        "paper_trades",
        "agent_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.drop_index("ix_user_agents_status", table_name="user_agents")
    op.drop_index("ix_user_agents_user_id", table_name="user_agents")
    op.drop_table("user_agents")
