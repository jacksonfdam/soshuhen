"""volume: J-Novel Club volumes the user owns, kept apart from chapters

Revision ID: 0023_volume
Revises: 0022_chapter_available_until
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_volume"
down_revision: str | None = "0022_chapter_available_until"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Its own table, not chapter rows with a unit column: everything that counts
    # chapters or turns a Komga book into a chapter number would otherwise need
    # a filter, and the one forgotten would count volume 16 as chapter 16.
    op.create_table(
        "volume",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "series_id",
            sa.BigInteger(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Numeric(8, 2), nullable=False),
        sa.Column("source_volume_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True)),
        sa.Column("downloaded_updated", sa.DateTime(timezone=True)),
        sa.Column("first_part", sa.Numeric(8, 2)),
        sa.Column("last_part", sa.Numeric(8, 2)),
        sa.Column("state", sa.Text(), nullable=False, server_default="known"),
        sa.Column("file_path", sa.Text()),
        sa.Column("komga_book_id", sa.Text()),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("series_id", "number", name="volume_series_number_key"),
        sa.UniqueConstraint("series_id", "source_volume_id", name="volume_series_source_key"),
        sa.CheckConstraint("status in ('owned', 'preorder')", name="volume_status_check"),
        sa.CheckConstraint(
            "state in ('known', 'queued', 'downloading', 'downloaded', 'failed')",
            name="volume_state_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("volume")
