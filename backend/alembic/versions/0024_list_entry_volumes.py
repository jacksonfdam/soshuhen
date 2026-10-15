"""list_entry volumes: volumes read and the list's own volume count

Revision ID: 0024_list_entry_volumes
Revises: 0023_volume
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_list_entry_volumes"
down_revision: str | None = "0023_volume"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both nullable and not backfilled: the next list sync fills them, and
    # until then the forward-only guard reads null as 0 and the cap as none.
    op.add_column("list_entry", sa.Column("user_progress_volume", sa.Integer()))
    op.add_column("list_entry", sa.Column("total_volumes", sa.Integer()))


def downgrade() -> None:
    op.drop_column("list_entry", "total_volumes")
    op.drop_column("list_entry", "user_progress_volume")
