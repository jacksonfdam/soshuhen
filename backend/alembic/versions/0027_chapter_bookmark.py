"""chapter.bookmarked: a chapter the reader marked to come back to

Revision ID: 0027_chapter_bookmark
Revises: 0026_source_mapping_discovered
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_chapter_bookmark"
down_revision: str | None = "0026_source_mapping_discovered"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chapter",
        sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chapter", "bookmarked")
