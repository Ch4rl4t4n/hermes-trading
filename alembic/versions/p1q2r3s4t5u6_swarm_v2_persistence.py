"""Swarm v2 — persistence, dead-letter and capability indexes.

Revision ID: p1q2r3s4t5u6
Revises: o9p8q7r6s5t4
Create Date: 2026-05-08
"""

from typing import Sequence, Union

from alembic import op

revision: str = "p1q2r3s4t5u6"
down_revision: Union[str, Sequence[str], None] = "o9p8q7r6s5t4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── agent_registry: extra columns + indexy ────────────────────────────
    op.execute(
        """
        ALTER TABLE agent_registry
            ADD COLUMN IF NOT EXISTS load_score INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS active_tasks INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP DEFAULT NOW(),
            ADD COLUMN IF NOT EXISTS version VARCHAR(20) DEFAULT '2.0',
            ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_registry_swarm_status "
        "ON agent_registry (swarm_name, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_registry_capabilities "
        "ON agent_registry USING GIN (capabilities);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_registry_heartbeat "
        "ON agent_registry (last_heartbeat DESC);"
    )

    # ── task_queue: lifecycle stĺpce + dead-letter ────────────────────────
    op.execute(
        """
        ALTER TABLE task_queue
            ADD COLUMN IF NOT EXISTS swarm_name VARCHAR(50),
            ADD COLUMN IF NOT EXISTS routing_reason TEXT,
            ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS execution_time_ms INTEGER;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_queue_status_priority "
        "ON task_queue (status, priority DESC, created_at ASC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_queue_assigned "
        "ON task_queue (assigned_to, status) "
        "WHERE assigned_to IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_queue_capabilities "
        "ON task_queue USING GIN (required_capabilities);"
    )

    # ── routing_decisions: audit log (perzistentný) ───────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS routing_decisions (
            id BIGSERIAL PRIMARY KEY,
            task_id VARCHAR(64) NOT NULL,
            task_type VARCHAR(50) NOT NULL,
            assigned_agent VARCHAR(50),
            assigned_swarm VARCHAR(50),
            score INTEGER DEFAULT 0,
            reason TEXT,
            required_capabilities JSONB DEFAULT '[]'::jsonb,
            decided_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_routing_decisions_task
            ON routing_decisions (task_id);
        CREATE INDEX IF NOT EXISTS idx_routing_decisions_decided_at
            ON routing_decisions (decided_at DESC);
        """
    )

    # ── swarm_metrics: time-series (lightweight) ──────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS swarm_metrics (
            id BIGSERIAL PRIMARY KEY,
            swarm_name VARCHAR(50) NOT NULL,
            metric_name VARCHAR(50) NOT NULL,
            value NUMERIC NOT NULL,
            recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_swarm_metrics_swarm_time
            ON swarm_metrics (swarm_name, recorded_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS swarm_metrics;")
    op.execute("DROP TABLE IF EXISTS routing_decisions;")
    op.execute("DROP INDEX IF EXISTS idx_task_queue_capabilities;")
    op.execute("DROP INDEX IF EXISTS idx_task_queue_assigned;")
    op.execute("DROP INDEX IF EXISTS idx_task_queue_status_priority;")
    op.execute("DROP INDEX IF EXISTS idx_agent_registry_heartbeat;")
    op.execute("DROP INDEX IF EXISTS idx_agent_registry_capabilities;")
    op.execute("DROP INDEX IF EXISTS idx_agent_registry_swarm_status;")
    op.execute(
        """
        ALTER TABLE task_queue
            DROP COLUMN IF EXISTS execution_time_ms,
            DROP COLUMN IF EXISTS dead_lettered_at,
            DROP COLUMN IF EXISTS routing_reason,
            DROP COLUMN IF EXISTS swarm_name;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_registry
            DROP COLUMN IF EXISTS metadata,
            DROP COLUMN IF EXISTS version,
            DROP COLUMN IF EXISTS last_seen,
            DROP COLUMN IF EXISTS active_tasks,
            DROP COLUMN IF EXISTS load_score;
        """
    )
