"""intelligence news bubbles — agent-fed dashboard ticker."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4f5d6e7b8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED_ROWS = [
    {
        "kind": "news",
        "title": "Tom Lee's 2026 targets for ETH & BTC",
        "icon": "🟧",
        "accent": "orange",
        "source": "Fundstrat",
        "priority": 9,
    },
    {
        "kind": "alert",
        "title": "Add AI alert",
        "icon": "🔵",
        "accent": "blue",
        "source": "Hermes",
        "priority": 8,
    },
    {
        "kind": "news",
        "title": "CLARITY Act advances toward key Senate vote",
        "icon": "🟥",
        "accent": "red",
        "source": "Reuters",
        "priority": 7,
    },
    {
        "kind": "question",
        "title": "Why is the market up today?",
        "icon": "🟧",
        "accent": "orange",
        "source": "Hermes AI",
        "priority": 6,
    },
    {
        "kind": "question",
        "title": "Are altcoins outperforming Bitcoin?",
        "icon": "🟧",
        "accent": "orange",
        "source": "Hermes AI",
        "priority": 5,
    },
    {
        "kind": "question",
        "title": "What are the trending narratives?",
        "icon": "🟧",
        "accent": "orange",
        "source": "Hermes AI",
        "priority": 4,
    },
    {
        "kind": "question",
        "title": "What cryptos are trending right now?",
        "icon": "🔵",
        "accent": "blue",
        "source": "Hermes AI",
        "priority": 3,
    },
    {
        "kind": "insight",
        "title": "Whales accumulated $310M ETH overnight",
        "icon": "🟢",
        "accent": "green",
        "source": "WhaleAlert",
        "priority": 2,
    },
]


def upgrade() -> None:
    op.create_table(
        "intelligence_news",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'news'"),
        ),  # news | question | alert | insight
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=True),
        sa.Column("accent", sa.String(length=16), nullable=True),  # orange|blue|green|red|purple
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column(
            "agent_id",
            sa.String(length=64),
            sa.ForeignKey("trading_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "kind IN ('news','question','alert','insight')",
            name="ck_intelligence_news_kind",
        ),
    )
    op.create_index(
        "idx_intelligence_news_active",
        "intelligence_news",
        ["expires_at", "priority", "created_at"],
        unique=False,
    )

    # Seed example bubbles so the UI ships "alive" — agents will append later.
    intelligence_news = sa.table(
        "intelligence_news",
        sa.column("kind", sa.String),
        sa.column("title", sa.Text),
        sa.column("icon", sa.String),
        sa.column("accent", sa.String),
        sa.column("source", sa.String),
        sa.column("priority", sa.Integer),
    )
    op.bulk_insert(intelligence_news, _SEED_ROWS)


def downgrade() -> None:
    op.drop_index("idx_intelligence_news_active", table_name="intelligence_news")
    op.drop_table("intelligence_news")
