"""reading_position: a place inside a volume, and how far through a section

Revision ID: 0029_reading_position_volume
Revises: 0028_volume_edition
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_reading_position_volume"
down_revision: str | None = "0028_volume_edition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A light novel volume is one book with no chapter rows, so a place in it
    # cannot name a chapter. Still one row per series: "where am I in this
    # series" keeps a single answer, whichever kind of book holds it.
    op.alter_column("reading_position", "chapter_id", nullable=True)
    op.add_column(
        "reading_position",
        sa.Column(
            "volume_id",
            sa.BigInteger(),
            sa.ForeignKey("volume.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    # Prose scrolls rather than turns pages: `page` is the section, and this is
    # how far down it the reader stood.
    op.add_column("reading_position", sa.Column("fraction", sa.Float(), nullable=True))
    op.create_check_constraint(
        "reading_position_one_target",
        "reading_position",
        "(chapter_id is null) <> (volume_id is null)",
    )


def downgrade() -> None:
    op.drop_constraint("reading_position_one_target", "reading_position", type_="check")
    op.execute("delete from reading_position where chapter_id is null")
    op.drop_column("reading_position", "fraction")
    op.drop_column("reading_position", "volume_id")
    op.alter_column("reading_position", "chapter_id", nullable=False)
