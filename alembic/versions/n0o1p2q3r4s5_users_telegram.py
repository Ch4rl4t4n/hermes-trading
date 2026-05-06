"""users telegram columns + connect token

Revision ID: n0o1p2q3r4s5
Revises: m9n8o7p6q5r4
Create Date: 2026-05-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n0o1p2q3r4s5"
down_revision: Union[str, Sequence[str], None] = "m9n8o7p6q5r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "users",
        sa.Column("telegram_connected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("users", sa.Column("telegram_connect_token", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("telegram_connect_token_exp", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_telegram ON users (telegram_chat_id) "
        "WHERE telegram_chat_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_telegram")
    op.drop_column("users", "telegram_connect_token_exp")
    op.drop_column("users", "telegram_connect_token")
    op.drop_column("users", "telegram_connected_at")
    op.drop_column("users", "telegram_chat_id")
