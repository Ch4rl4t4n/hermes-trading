"""Pro trial promo and onboarding completion timestamp on users

Revision ID: a1b2c3d4e5f7
Revises: f8b9c0d1e2f3
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trial_promo_tier", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column("trial_promo_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "trial_promo_until")
    op.drop_column("users", "trial_promo_tier")
