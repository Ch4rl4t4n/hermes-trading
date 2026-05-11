"""community feed: posts + likes for CMC-style dashboard panel."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4f5d6e7b8a9"
down_revision: Union[str, Sequence[str], None] = "q2w3e4r5t6y7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "community_posts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sentiment", sa.String(length=10), nullable=True),  # 'bullish' | 'bearish' | NULL
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("views_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("sentiment IN ('bullish','bearish') OR sentiment IS NULL", name="ck_community_post_sentiment"),
    )
    op.create_index("idx_community_posts_created_at", "community_posts", ["created_at"], unique=False)
    op.create_index("idx_community_posts_symbol", "community_posts", ["symbol"], unique=False)
    op.create_index("idx_community_posts_sentiment_created", "community_posts", ["sentiment", "created_at"], unique=False)

    op.create_table(
        "community_post_likes",
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("community_posts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_community_post_likes_user", "community_post_likes", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_community_post_likes_user", table_name="community_post_likes")
    op.drop_table("community_post_likes")
    op.drop_index("idx_community_posts_sentiment_created", table_name="community_posts")
    op.drop_index("idx_community_posts_symbol", table_name="community_posts")
    op.drop_index("idx_community_posts_created_at", table_name="community_posts")
    op.drop_table("community_posts")
