"""weekly report columns on users

Revision ID: k9l8m7n6o5p4
Revises: j0k1l2m3n4o5
Create Date: 2026-05-04

"""
from __future__ import annotations

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k9l8m7n6o5p4"
down_revision: Union[str, Sequence[str], None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "weekly_report_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("weekly_report_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_users_unsubscribe_token",
        "users",
        ["unsubscribe_token"],
        unique=True,
    )

    conn = op.get_bind()
    for row in conn.execute(sa.text("SELECT id FROM users WHERE unsubscribe_token IS NULL")):
        uid = row[0]
        conn.execute(
            sa.text("UPDATE users SET unsubscribe_token = :t WHERE id = :id"),
            {"t": secrets.token_hex(32), "id": uid},
        )


def downgrade() -> None:
    op.drop_index("ix_users_unsubscribe_token", table_name="users")
    op.drop_column("users", "unsubscribe_token")
    op.drop_column("users", "weekly_report_sent_at")
    op.drop_column("users", "weekly_report_enabled")
