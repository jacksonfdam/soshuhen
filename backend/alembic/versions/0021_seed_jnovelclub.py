"""seed J-Novel Club as a prose source

Revision ID: 0021_seed_jnovelclub
Revises: 0020_seed_prose_sources
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_seed_jnovelclub"
down_revision: str | None = "0020_seed_prose_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enabled on arrival: its search needs no sign-in, so it answers for every
# light novel straight away, and downloading still waits for one. One request
# per second is the pace agreed in the design for a publisher's own API.
CATALOGUE = sa.text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, rate_limit, version, hand_ported)
    values ('jnovelclub', 'J-Novel Club', 'native', 'https://labs.j-novel.club', 'en', false,
            '{}'::jsonb, '{"permits": 1, "period_seconds": 1}'::jsonb, '1', true)
    on conflict (key) do nothing
    """
)
PREFERENCE = sa.text(
    "insert into source_pref (key, enabled) values ('jnovelclub', true) on conflict (key) do nothing"
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(CATALOGUE)
    bind.execute(PREFERENCE)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("delete from source_pref where key = 'jnovelclub'"))
    bind.execute(sa.text("delete from site_catalogue where key = 'jnovelclub'"))
