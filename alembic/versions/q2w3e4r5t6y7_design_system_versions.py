"""design_system_versions — Owner CMS schema history + apply audit."""

from typing import Sequence, Union

from alembic import op

revision: str = "q2w3e4r5t6y7"
down_revision: Union[str, Sequence[str], None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS design_system_versions (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            label VARCHAR(240),
            schema_json JSONB NOT NULL,
            applied_at TIMESTAMPTZ,
            applied_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_design_system_versions_applied_at "
        "ON design_system_versions (applied_at DESC NULLS LAST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_design_system_versions_applied_at")
    op.execute("DROP TABLE IF EXISTS design_system_versions")
