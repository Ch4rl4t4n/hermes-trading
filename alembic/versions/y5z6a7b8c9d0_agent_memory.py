"""add agent_memory table for persistent memory vault."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y5z6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_memory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("trading_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_key", sa.String(length=100), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("agent_id", "user_id", "memory_key", name="uq_agent_memory_agent_user_key"),
    )
    op.create_index("idx_agent_memory_agent_user", "agent_memory", ["agent_id", "user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_agent_memory_agent_user", table_name="agent_memory")
    op.drop_table("agent_memory")
