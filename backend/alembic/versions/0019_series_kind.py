"""series.kind: comic or prose, so a light novel stops being searched as a manga

Revision ID: 0019_series_kind
Revises: 0018_reader
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_series_kind"
down_revision: str | None = "0018_reader"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The provider vocabularies are copied here rather than imported from
# app.providers: a migration has to keep meaning what it meant on the day it
# shipped, and the maps in the app are free to grow after that. The rules are
# series_kind_from_entries' rules - any comic entry makes the series a comic,
# because a mixed series is exactly the shape issue #88 found already merged,
# and resolving it to prose would let the corruption compound.
BACKFILL = """
with entry_kind as (
    select series_id,
           case
               when provider = 'mal' then
                   case when raw -> 'node' ->> 'media_type' in ('novel', 'light_novel')
                            then 'prose'
                        when raw -> 'node' ->> 'media_type' in ('manga', 'manhwa', 'manhua', 'oel')
                            then 'comic'
                   end
               when provider = 'anilist' then
                   case when raw -> 'media' ->> 'format' = 'NOVEL' then 'prose'
                        when raw -> 'media' ->> 'format' in ('MANGA', 'MANHWA', 'MANHUA', 'OEL')
                            then 'comic'
                   end
               when provider = 'mangabaka' then
                   case when lower(raw -> 'Series' ->> 'type') = 'novel' then 'prose'
                        when lower(raw -> 'Series' ->> 'type') in ('manga', 'manhwa', 'manhua', 'oel')
                            then 'comic'
                   end
           end as kind
      from list_entry
     where series_id is not null
)
update series s
   set kind = resolved.kind
  from (
      select series_id,
             case when bool_or(kind = 'comic') then 'comic'
                  when bool_or(kind = 'prose') then 'prose'
             end as kind
        from entry_kind
       group by series_id
  ) resolved
 where resolved.series_id = s.id
   and resolved.kind is not null
"""


def upgrade() -> None:
    op.add_column("series", sa.Column("kind", sa.Text(), nullable=True))
    op.create_check_constraint("series_kind_check", "series", "kind in ('comic', 'prose')")
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_constraint("series_kind_check", "series", type_="check")
    op.drop_column("series", "kind")
