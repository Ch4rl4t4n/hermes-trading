"""Align User/Account ORM relationships (no schema change)

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f7
Create Date: 2026-05-04

`User.accounts` / `Account.user` are SQLAlchemy-only; the database already has
`accounts.user_id` from prior migrations. Autogenerate would emit no ops when DB
matches metadata.
"""

from typing import Sequence, Union


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
