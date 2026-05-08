"""Add intelligence_reports table.

Revision ID: o9p8q7r6s5t4
Revises: n1m2n3b4v5c6
"""

from typing import Sequence, Union

from alembic import op

revision: str = "o9p8q7r6s5t4"
down_revision: Union[str, Sequence[str], None] = "n1m2n3b4v5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS intelligence_reports (
            id SERIAL PRIMARY KEY,
            report_type VARCHAR(50) NOT NULL,
            symbol VARCHAR(20),
            title VARCHAR(200),
            content TEXT,
            sentiment VARCHAR(10),
            sentiment_score NUMERIC(4,3),
            source VARCHAR(100),
            tags JSONB DEFAULT '[]',
            agent_id VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_type ON intelligence_reports(report_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_symbol ON intelligence_reports(symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_created ON intelligence_reports(created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_intel_created")
    op.execute("DROP INDEX IF EXISTS idx_intel_symbol")
    op.execute("DROP INDEX IF EXISTS idx_intel_type")
    op.execute("DROP TABLE IF EXISTS intelligence_reports")
