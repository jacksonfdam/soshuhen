"""seed the gadgetizedpanda prose source

Revision ID: 0030_seed_gadgetizedpanda
Revises: 0029_reading_position_volume
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_seed_gadgetizedpanda"
down_revision: str | None = "0029_reading_position_volume"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enabled from the start: the blog sits behind no challenge, so unlike
# EmpireNovel it needs nothing from the user before it can answer.
KEY = "gadgetizedpanda"
ROW = {"key": KEY, "name": "Gadgetized Panda", "base_url": "https://gadgetizedpanda.net"}

CATALOGUE = sa.text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
    values (:key, :name, 'native', :base_url, 'en', false, '{}'::jsonb, '1', true)
    on conflict (key) do nothing
    """
)
PREFERENCE = sa.text(
    "insert into source_pref (key, enabled) values (:key, true) on conflict (key) do nothing"
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(CATALOGUE, ROW)
    bind.execute(PREFERENCE, {"key": KEY})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("delete from source_pref where key = :key"), {"key": KEY})
    bind.execute(sa.text("delete from site_catalogue where key = :key"), {"key": KEY})
