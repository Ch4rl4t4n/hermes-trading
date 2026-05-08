"""Create community_agents table for user marketplace.

Revision ID: q9w8e7r6t5y4
Revises: z1y2x3w4v5u6
"""

from typing import Sequence, Union

from alembic import op

revision: str = "q9w8e7r6t5y4"
down_revision: Union[str, Sequence[str], None] = "z1y2x3w4v5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_agents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            category VARCHAR(20) NOT NULL,
            strategy VARCHAR(50) NOT NULL,
            risk_level VARCHAR(20) DEFAULT 'medium',
            description TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            win_rate NUMERIC(5,2) DEFAULT 0,
            total_return NUMERIC(10,2) DEFAULT 0,
            subscribers INTEGER DEFAULT 0,
            price_monthly NUMERIC(8,2) DEFAULT 0,
            is_featured BOOLEAN DEFAULT FALSE,
            reject_reason TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            approved_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_agents_status ON community_agents(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_agents_user ON community_agents(user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_community_agents_user")
    op.execute("DROP INDEX IF EXISTS idx_community_agents_status")
    op.execute("DROP TABLE IF EXISTS community_agents")
