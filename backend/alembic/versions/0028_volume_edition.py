"""volume.edition: a volume in its web novel or its light novel edition

Revision ID: 0028_volume_edition
Revises: 0027_chapter_bookmark
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_volume_edition"
down_revision: str | None = "0027_chapter_bookmark"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A user can own both editions of one volume: the light novel rewrites and
    # merges the web chapters, so they are two books under one number. Every
    # row before this was a J-Novel Club volume, which is the light novel.
    op.add_column(
        "volume", sa.Column("edition", sa.Text(), nullable=False, server_default="light")
    )
    op.create_check_constraint("volume_edition_check", "volume", "edition in ('web', 'light')")
    op.drop_constraint("volume_series_number_key", "volume", type_="unique")
    op.create_unique_constraint(
        "volume_series_number_edition_key", "volume", ["series_id", "number", "edition"]
    )


def downgrade() -> None:
    # The old key cannot hold both editions; the web rows are only chapter
    # ranges, and their chapters stay.
    op.execute("delete from volume where edition = 'web'")
    op.drop_constraint("volume_series_number_edition_key", "volume", type_="unique")
    op.create_unique_constraint("volume_series_number_key", "volume", ["series_id", "number"])
    op.drop_constraint("volume_edition_check", "volume", type_="check")
    op.drop_column("volume", "edition")
