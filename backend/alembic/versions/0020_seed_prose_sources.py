"""seed the three prose sources

Revision ID: 0020_seed_prose_sources
Revises: 0019_series_kind
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_seed_prose_sources"
down_revision: str | None = "0019_series_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# EmpireNovel arrives disabled: every request it makes meets a Cloudflare
# challenge, and without the flaresolverr profile enabling it would only add a
# source that fails every search. Turning it on is the user's call, made in the
# same place they turn on the solver.
SITES = [
    ("lolobun", "LoLoBun", "https://www.lolobun.com", True),
    ("novelight", "Novelight", "https://novelight.net", True),
    ("empirenovel", "EmpireNovel", "https://www.empirenovel.com", False),
]

CATALOGUE = sa.text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
    values (:key, :name, 'native', :base_url, 'en', false, '{}'::jsonb, '1', true)
    on conflict (key) do nothing
    """
)
PREFERENCE = sa.text(
    "insert into source_pref (key, enabled) values (:key, :enabled) on conflict (key) do nothing"
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, base_url, enabled in SITES:
        bind.execute(CATALOGUE, {"key": key, "name": name, "base_url": base_url})
        bind.execute(PREFERENCE, {"key": key, "enabled": enabled})


def downgrade() -> None:
    bind = op.get_bind()
    keys = [key for key, *_ in SITES]
    bind.execute(sa.text("delete from source_pref where key = any(:keys)"), {"keys": keys})
    bind.execute(sa.text("delete from site_catalogue where key = any(:keys)"), {"keys": keys})
