"""Create agent_registry and task_queue tables.

Revision ID: n1m2n3b4v5c6
Revises: p4q5r6s7t8u9
"""

from typing import Sequence, Union

from alembic import op

revision: str = "n1m2n3b4v5c6"
down_revision: Union[str, Sequence[str], None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_registry (
            id SERIAL PRIMARY KEY,
            agent_id VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            swarm_name VARCHAR(50),
            agent_type VARCHAR(50) DEFAULT 'worker',
            status VARCHAR(20) DEFAULT 'idle',
            capabilities JSONB DEFAULT '[]',
            priority INTEGER DEFAULT 5,
            config JSONB DEFAULT '{}',
            memory_enabled BOOLEAN DEFAULT TRUE,
            human_approval_required BOOLEAN DEFAULT FALSE,
            cost_limit_daily NUMERIC(8,2) DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            tasks_failed INTEGER DEFAULT 0,
            last_heartbeat TIMESTAMP,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            task_id VARCHAR(50) NOT NULL UNIQUE,
            task_type VARCHAR(50) NOT NULL,
            payload JSONB DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'pending',
            priority INTEGER DEFAULT 5,
            assigned_to VARCHAR(50) REFERENCES agent_registry(agent_id),
            required_capabilities JSONB DEFAULT '[]',
            result JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_registry_status ON agent_registry(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_registry_swarm ON agent_registry(swarm_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON task_queue(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_queue_priority ON task_queue(priority DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_queue_priority")
    op.execute("DROP INDEX IF EXISTS idx_queue_status")
    op.execute("DROP INDEX IF EXISTS idx_registry_swarm")
    op.execute("DROP INDEX IF EXISTS idx_registry_status")
    op.execute("DROP TABLE IF EXISTS task_queue")
    op.execute("DROP TABLE IF EXISTS agent_registry")
