"""source_mapping.discovered_at: when this mapping's chapters were first listed

Revision ID: 0026_source_mapping_discovered
Revises: 0025_notification
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_source_mapping_discovered"
down_revision: str | None = "0025_notification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_mapping", sa.Column("discovered_at", sa.DateTime(timezone=True))
    )
    # A mapping that already has chapters has been discovered. Left null, every
    # series would go silent for one more run after this ships.
    op.execute(
        """
        update source_mapping m set discovered_at = now()
         where m.active
           and exists (select 1 from chapter c where c.series_id = m.series_id)
        """
    )


def downgrade() -> None:
    op.drop_column("source_mapping", "discovered_at")
