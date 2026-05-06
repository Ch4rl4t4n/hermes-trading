"""User lockout columns and canonical subscription tiers

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE users SET tier = 'basic' WHERE tier = 'free'"))
    op.execute(sa.text("UPDATE users SET tier = 'medium' WHERE tier = 'starter'"))
    op.execute(sa.text("UPDATE users SET tier = 'pro' WHERE tier = 'professional'"))
    # Normalize default_tier inside registration blob when present (PostgreSQL JSON).
    op.execute(
        sa.text(
            """
            UPDATE platform_settings
            SET value = jsonb_set(value::jsonb, '{default_tier}', '"basic"', true)
            WHERE key = 'registration' AND value IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE users SET tier = 'free' WHERE tier = 'basic'"))
    op.execute(sa.text("UPDATE users SET tier = 'starter' WHERE tier = 'medium'"))
    op.execute(sa.text("UPDATE users SET tier = 'professional' WHERE tier = 'pro'"))
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
