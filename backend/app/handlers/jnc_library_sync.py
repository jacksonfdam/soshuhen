"""Read the J-Novel Club library and keep volume rows and downloads in step.

Buying a volume is the decision to have it, so an owned volume of a series
mapped to J-Novel Club downloads without being asked - unlike chapters, which
wait for a range or auto_download. Volumes of series no list holds are only
named in the log: a series is created by a reading list, never by a shop.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, NotificationKind
from app.handlers.base import JobContext, register
from app.notifications import record
from app.sources.base import SignInRequired, get_prose_source

SITE = "jnovelclub"
_SERIES_SLUG = re.compile(r"/series/([^/?#]+)")

UPSERT = """
insert into volume (series_id, number, source_volume_id, title, status, last_updated,
                    first_part, last_part)
values (:series_id, :number, :volume_id, :title, :status, cast(:last_updated as timestamptz),
        cast(:first_part as numeric), cast(:last_part as numeric))
on conflict (series_id, source_volume_id) do update
   set number = excluded.number,
       title = excluded.title,
       status = excluded.status,
       last_updated = excluded.last_updated,
       -- A volume's part range only grows. An aggregate that leaves a volume
       -- out says nothing about its parts, and writing null over the range
       -- would cost its reading progress and the next sync's parts news.
       first_part = coalesce(excluded.first_part, volume.first_part),
       last_part = coalesce(excluded.last_part, volume.last_part)
returning id, state, downloaded_updated, last_updated
"""


def needs_download(
    *,
    status: str,
    has_link: bool,
    state: str,
    downloaded_updated: datetime | None,
    last_updated: datetime | None,
) -> bool:
    """Owned, downloadable, and not on disk at this revision.

    Whether a download is already on its way is the job table's to say, not
    the row's: enqueue dedupes against a waiting or running job, while a row
    can say queued long after "Cancel queue" deleted the job it meant.
    """
    if status != "owned" or not has_link:
        return False
    if downloaded_updated is None:
        return True
    return last_updated is not None and downloaded_updated < last_updated


@dataclass(frozen=True)
class VolumeNews:
    new_volume: bool
    #: First and last new part, inclusive.
    new_parts: tuple[Decimal, Decimal] | None


def volume_news(
    *,
    before: tuple[str, Decimal | None] | None,
    status: str,
    last_part: Decimal | None,
) -> VolumeNews:
    """What one upserted volume adds that the user can now read.

    `before` is the volume's (status, last_part) ahead of the upsert, or None
    when the volume is new. A pre-order cannot be read yet, so it is news only
    on the sync that finds it owned.
    """
    new_volume = status == "owned" and (before is None or before[0] == "preorder")
    new_parts = None
    # A range unknown last time is not one that grew: there is nothing to say
    # which of its parts are new.
    if (
        before is not None
        and before[1] is not None
        and last_part is not None
        and last_part > before[1]
    ):
        new_parts = (before[1] + 1, last_part)
    return VolumeNews(new_volume, new_parts)


async def series_by_slug(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text(
                "select series_id, source_url from source_mapping"
                " where active and source_site = :site"
            ),
            {"site": SITE},
        )
    ).all()
    found: dict[str, int] = {}
    for row in rows:
        match = _SERIES_SLUG.search(row.source_url or "")
        if match:
            found[match.group(1)] = row.series_id
    return found


@register(JobType.JNC_LIBRARY_SYNC)
async def handle(ctx: JobContext) -> None:
    try:
        source = get_prose_source(SITE)
    except (ValueError, TypeError):
        await ctx.log("J-Novel Club is not enabled; skipping the library")
        return
    try:
        owned = await source.library()
    except SignInRequired:
        # Done, not failed: a free account or a signed-out install would
        # otherwise turn this cron red every six hours for nothing.
        await ctx.log("J-Novel Club is not signed in; skipping the library", pct=100)
        return

    mapped = await series_by_slug(ctx.session)
    by_slug: dict[str, list[Any]] = defaultdict(list)
    for volume in owned:
        by_slug[volume.series_slug].append(volume)

    unmapped: list[str] = []
    queued = revised = preorders = 0
    for slug, volumes in by_slug.items():
        series_id = mapped.get(slug)
        if series_id is None:
            unmapped.append(slug)
            continue
        ranges = await source.part_ranges(slug)
        known = {
            row.source_volume_id: (row.status, row.last_part)
            for row in await ctx.session.execute(
                text(
                    "select source_volume_id, status, last_part from volume"
                    " where series_id = :s"
                ),
                {"s": series_id},
            )
        }
        # On a series' first sync every owned volume is new to this table, and
        # announcing a whole shelf the user already bought is not news.
        first_sync = not known
        new_volumes: list[Decimal] = []
        for volume in volumes:
            first, last = ranges.get(volume.number, (None, None))
            try:
                # One savepoint per volume: a number another edition already
                # holds must cost that volume, not every series' sync forever.
                async with ctx.session.begin_nested():
                    row = (
                        await ctx.session.execute(
                            text(UPSERT),
                            {
                                "series_id": series_id,
                                "number": volume.number,
                                "volume_id": volume.volume_id,
                                "title": volume.title,
                                "status": volume.status,
                                "last_updated": volume.last_updated,
                                "first_part": first,
                                "last_part": last,
                            },
                        )
                    ).one()
            except IntegrityError:
                await ctx.log(
                    f"{slug}: skipped volume {volume.number}, its number is already held by"
                    " another edition",
                    level="warning",
                )
                continue
            if volume.status == "preorder":
                preorders += 1
            if not first_sync:
                news = volume_news(
                    before=known.get(volume.volume_id), status=volume.status, last_part=last
                )
                if news.new_volume:
                    new_volumes.append(volume.number)
                if news.new_parts:
                    first_new, last_new = news.new_parts
                    # J-Novel Club numbers parts with whole numbers, so the
                    # range names every new part exactly.
                    await record(
                        ctx.session,
                        series_id,
                        NotificationKind.PARTS,
                        [Decimal(n) for n in range(int(first_new), int(last_new) + 1)],
                        volume_number=volume.number,
                    )
            if not needs_download(
                status=volume.status,
                has_link=volume.epub_link is not None,
                state=row.state,
                downloaded_updated=row.downloaded_updated,
                last_updated=row.last_updated,
            ):
                continue
            job_id = await ctx.enqueue(
                JobType.VOLUME_DOWNLOAD,
                {"volume_id": row.id},
                series_id=series_id,
                dedupe_key=f"volume_download:{row.id}",
            )
            if job_id is None:
                continue  # already waiting or running
            if row.downloaded_updated is not None:
                revised += 1
            await ctx.session.execute(
                text("update volume set state = 'queued' where id = :id"), {"id": row.id}
            )
            queued += 1
        await record(ctx.session, series_id, NotificationKind.VOLUMES, new_volumes)

    await ctx.session.commit()
    summary = f"{len(owned)} owned on J-Novel Club, {queued} queued"
    if revised:
        summary += f" ({revised} revised)"
    if preorders:
        summary += f", {preorders} pre-orders waiting"
    if unmapped:
        summary += f"; owned but not mapped: {', '.join(sorted(unmapped))}"
    await ctx.log(summary, pct=100)
