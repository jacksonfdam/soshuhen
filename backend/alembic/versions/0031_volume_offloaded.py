"""allow a volume to be offloaded to a device

Revision ID: 0031_volume_offloaded
Revises: 0030_seed_gadgetizedpanda
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_volume_offloaded"
down_revision: str | None = "0030_seed_gadgetizedpanda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WITH_OFFLOADED = "state in ('known', 'queued', 'downloading', 'downloaded', 'failed', 'offloaded')"
WITHOUT = "state in ('known', 'queued', 'downloading', 'downloaded', 'failed')"


def upgrade() -> None:
    op.drop_constraint("volume_state_check", "volume", type_="check")
    op.create_check_constraint("volume_state_check", "volume", WITH_OFFLOADED)


def downgrade() -> None:
    # An offloaded volume has no file on the server any more. Rewriting it to
    # any older state would claim either a file that is gone or a download
    # nobody asked for, so the downgrade refuses instead of guessing.
    held = op.get_bind().execute(
        sa.text("select 1 from volume where state = 'offloaded' limit 1")
    ).first()
    if held is not None:
        raise RuntimeError("volumes are offloaded to a device; download them again first")
    op.drop_constraint("volume_state_check", "volume", type_="check")
    op.create_check_constraint("volume_state_check", "volume", WITHOUT)
