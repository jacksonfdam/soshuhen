"""the reader: page position, per-series display, streamed page lists

Revision ID: 0018_reader
Revises: 0017_removed_entry
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018_reader"
down_revision: str | None = "0017_removed_entry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_position",
        sa.Column(
            "series_id",
            sa.BigInteger,
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "chapter_id",
            sa.BigInteger,
            sa.ForeignKey("chapter.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "series_reader_pref",
        sa.Column(
            "series_id",
            sa.BigInteger,
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("scale", sa.String(20), nullable=False),
        sa.Column("background", sa.String(20), nullable=False),
    )
    op.create_table(
        "chapter_page_list",
        sa.Column(
            "chapter_id",
            sa.BigInteger,
            sa.ForeignKey("chapter.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pages", JSONB, nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("chapter_page_list")
    op.drop_table("series_reader_pref")
    op.drop_table("reading_position")
