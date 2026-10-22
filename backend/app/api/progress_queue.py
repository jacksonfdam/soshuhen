"""Queueing a progress write, shared by the progress button and the reader."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, ProgressSource
from app.queue import repo


@dataclass(frozen=True)
class Bounds:
    current: int
    ceiling: int | None
    has_entries: bool


def chapter_ceiling(total_chapters: int | None, known: int | None) -> int | None:
    """The highest chapter a progress write may claim, or None when nothing knows.

    The forward-only guard stops progress moving backwards; nothing bounded it
    upwards, so a mistyped number or a +1 on a stale page was pushed to
    MyAnimeList and AniList, and no correction to this database takes that back.

    Two numbers can bound it and neither is authoritative alone: the provider's
    own total_chapters lags a release, and the discovered chapter count is
    whatever the source had indexed the last time we looked. The higher of the
    two is the ceiling, so a write is only refused when it is past both.

    An unmapped series with a provider that never stated a total has neither,
    and this returns None rather than inventing a bound: refusing every write
    on a series nobody has counted would make the +1 button dead on exactly the
    entries a user is most likely to be tracking by hand.
    """
    candidates = [value for value in (total_chapters, known) if value]
    return max(candidates) if candidates else None


async def progress_bounds(session: AsyncSession, series_id: int) -> Bounds:
    """Where a series' lists stand, and how far a write may take them.

    An aggregate with no group-by always returns one row, coalesced to 0, even
    when the series has no list_entry yet, so `has_entries` is counted rather
    than inferred from `current`.

    min(), not max(): a series with two providers at different chapters (say
    AniList 140, MyAnimeList 100) must still accept a write of 120 — it moves
    MyAnimeList forward and the handler leaves AniList alone. Comparing
    against the furthest-along provider would refuse a write the handler
    would have partially, correctly, applied.
    """
    result = await session.execute(
        text(
            """
            select coalesce(min(e.user_progress_chapter), 0) as current,
                   max(e.total_chapters) as total_chapters,
                   count(e.id) as entries,
                   (select count(*) from chapter where series_id = :id) as known
              from list_entry e
             where e.series_id = :id
            """
        ),
        {"id": series_id},
    )
    row = result.one()
    return Bounds(
        current=row.current,
        ceiling=chapter_ceiling(row.total_chapters, row.known),
        has_entries=row.entries > 0,
    )


async def queue_progress_write(
    session: AsyncSession,
    series_id: int,
    chapter: int,
    *,
    source: ProgressSource,
    read_at: datetime | None = None,
) -> None:
    payload: dict[str, object] = {"series_id": series_id, "chapter": chapter, "source": str(source)}
    if read_at is not None:
        # When the chapter was really read, for a client replaying offline
        # reading. Without it the event would be dated by the replay.
        payload["read_at"] = read_at.isoformat()
    stamp = payload.get("read_at")
    queued = await repo.enqueue(
        session,
        JobType.PROGRESS_WRITE,
        payload,
        priority=0,
        series_id=series_id,
        dedupe_key=f"progress_write:{series_id}",
    )
    if queued is None:
        # Two of these for one series is how a backwards write reaches someone
        # else's list: the grid card and the Continue-reading row each render
        # their own +1 with their own busy state, two workers lease both jobs,
        # both read the same pre-commit user_progress_chapter, and the higher
        # chapter can land at the provider first. The dedupe key refuses the
        # second job, so the request raises the chapter on the one already
        # waiting instead — the handler re-reads it before pushing, which is
        # what keeps this from silently dropping the click.
        await session.execute(
            text(
                """
                update job
                   -- The time moves with the chapter it belongs to, or an
                   -- offline chapter 5 would be dated by when 4 was read.
                   set payload = case
                         when cast(:read_at as text) is null
                         then jsonb_set(payload, '{chapter}',
                                        to_jsonb(cast(:chapter as integer))) - 'read_at'
                         else jsonb_set(
                                jsonb_set(payload, '{chapter}',
                                          to_jsonb(cast(:chapter as integer))),
                                '{read_at}', to_jsonb(cast(:read_at as text)))
                       end
                 where type = :type and series_id = :series_id
                   and state in ('pending', 'leased')
                   and (payload->>'chapter')::int < cast(:chapter as integer)
                """
            ),
            {
                "type": str(JobType.PROGRESS_WRITE),
                "series_id": series_id,
                "chapter": chapter,
                "read_at": stamp,
            },
        )
