"""Ensure API key table has daily usage columns.

Revision ID: z1y2x3w4v5u6
Revises: y5z6a7b8c9d0
"""

from typing import Sequence, Union

from alembic import op

revision: str = "z1y2x3w4v5u6"
down_revision: Union[str, Sequence[str], None] = "y5z6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key_hash VARCHAR(64) NOT NULL UNIQUE,
            key_prefix VARCHAR(8) NOT NULL,
            name VARCHAR(100) DEFAULT 'Default',
            is_active BOOLEAN DEFAULT TRUE,
            requests_today INTEGER DEFAULT 0,
            requests_total INTEGER DEFAULT 0,
            rate_limit INTEGER DEFAULT 1000,
            last_used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
    )
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS requests_today INTEGER DEFAULT 0")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS requests_total INTEGER DEFAULT 0")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS rate_limit INTEGER DEFAULT 1000")
    op.execute("ALTER TABLE api_keys ALTER COLUMN requests_today SET DEFAULT 0")
    op.execute("ALTER TABLE api_keys ALTER COLUMN requests_total SET DEFAULT 0")
    op.execute("ALTER TABLE api_keys ALTER COLUMN rate_limit SET DEFAULT 1000")
    op.execute("UPDATE api_keys SET requests_today = COALESCE(requests_today, 0)")
    op.execute("UPDATE api_keys SET requests_total = COALESCE(requests_total, 0)")
    op.execute("UPDATE api_keys SET rate_limit = COALESCE(rate_limit, 1000)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_keys_hash")
    op.execute("DROP INDEX IF EXISTS idx_api_keys_user")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS rate_limit")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS requests_total")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS requests_today")
