"""admin_cms platform_settings announcements user_announcements

Revision ID: d4e5f6a7b8c9
Revises: b9acb762aab1
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b9acb762aab1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_announcements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "announcement_id", name="uq_user_announcement_dismissal"),
    )
    op.create_index(op.f("ix_user_announcements_user_id"), "user_announcements", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_user_announcements_announcement_id"), "user_announcements", ["announcement_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_announcements_announcement_id"), table_name="user_announcements")
    op.drop_index(op.f("ix_user_announcements_user_id"), table_name="user_announcements")
    op.drop_table("user_announcements")
    op.drop_table("announcements")
    op.drop_table("platform_settings")
