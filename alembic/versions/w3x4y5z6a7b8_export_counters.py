"""Export counters on users.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, Sequence[str], None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("export_csv_count_month", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("export_pdf_count_week", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("export_reset_month", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("export_reset_week", sa.Date(), nullable=True))
    op.execute("UPDATE users SET export_reset_month = CURRENT_DATE WHERE export_reset_month IS NULL")
    op.execute("UPDATE users SET export_reset_week = CURRENT_DATE WHERE export_reset_week IS NULL")


def downgrade() -> None:
    op.drop_column("users", "export_reset_week")
    op.drop_column("users", "export_reset_month")
    op.drop_column("users", "export_pdf_count_week")
    op.drop_column("users", "export_csv_count_month")
