"""chapter.available_until: when a source stops serving a chapter

Revision ID: 0022_chapter_available_until
Revises: 0021_seed_jnovelclub
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_chapter_available_until"
down_revision: str | None = "0021_seed_jnovelclub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Null is "never expires", which is every chapter of every source but
    # J-Novel Club's pre-publication parts, so nothing is backfilled.
    op.add_column("chapter", sa.Column("available_until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("chapter", "available_until")
