"""Community marketplace MVP: user_agents publish fields + marketplace_clones.

Revision ID: s8t9u0v1w2x3
Revises: r7s8t9u0v1w2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s8t9u0v1w2x3"
down_revision: Union[str, Sequence[str], None] = "r7s8t9u0v1w2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_agents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "user_agents",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_agents",
        sa.Column("popularity_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_agents",
        sa.Column("clone_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("user_agents", sa.Column("marketplace_reject_reason", sa.Text(), nullable=True))

    op.create_table(
        "marketplace_clones",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "source_agent_id",
            sa.Integer(),
            sa.ForeignKey("user_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cloned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cloned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_agent_id",
            "cloned_by_user_id",
            name="uq_marketplace_clones_source_user",
        ),
    )
    op.create_index(
        "ix_marketplace_clones_source_agent_id",
        "marketplace_clones",
        ["source_agent_id"],
    )
    op.create_index(
        "ix_marketplace_clones_cloned_by_user_id",
        "marketplace_clones",
        ["cloned_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_marketplace_clones_cloned_by_user_id", table_name="marketplace_clones")
    op.drop_index("ix_marketplace_clones_source_agent_id", table_name="marketplace_clones")
    op.drop_table("marketplace_clones")
    op.drop_column("user_agents", "marketplace_reject_reason")
    op.drop_column("user_agents", "clone_count")
    op.drop_column("user_agents", "popularity_score")
    op.drop_column("user_agents", "published_at")
    op.drop_column("user_agents", "description")
