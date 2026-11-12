"""job.rerun_requested: work that arrived while its job was already running

Revision ID: 0031_job_rerun_requested
Revises: 0030_seed_gadgetizedpanda
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_job_rerun_requested"
down_revision: str | None = "0030_seed_gadgetizedpanda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job",
        sa.Column("rerun_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("job", "rerun_requested")
