"""Add Stripe subscription status, tier expiry, billing cycle + partial index."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1p2q3r4s5t6"
down_revision: Union[str, Sequence[str], None] = "n0o1p2q3r4s5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_subscription_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("tier_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "billing_cycle",
            sa.String(8),
            nullable=False,
            server_default="monthly",
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users (stripe_customer_id) "
        "WHERE stripe_customer_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_stripe_customer")
    op.drop_column("users", "billing_cycle")
    op.drop_column("users", "tier_expires_at")
    op.drop_column("users", "stripe_subscription_status")
