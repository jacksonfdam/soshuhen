"""How often a series releases, and whether a discovery run should ask today.

The rhythm is read from Soshuhen's own record of when each chapter turned up,
because no source states a schedule and the chapter lists carry no dates the
parsers keep. Only chapters found after their series was already followed count
(the rule app/api/routes_updates.py documents): a first discovery stamps a whole
back catalogue with one day, which says nothing about how often it grows.

The day a chapter is found trails the day it was published by up to one
discovery interval. That blurs a daily series into "every day or two" and
leaves a weekly one weekly, which is the precision this needs.
"""

from datetime import date
from itertools import pairwise
from statistics import median

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Ten gaps need eleven release days. Older ones describe a schedule the series
# may have left.
RELEASE_DAYS_KEPT = 11
# Fewer than this and a median of the gaps is a guess.
MIN_RELEASE_DAYS = 3
LONGEST_RHYTHM = 28
# After this many expected releases with nothing new, a series is on a break
# rather than late, and is asked once every LONGEST_RHYTHM days instead.
MISSES_BEFORE_BACKING_OFF = 10


def rhythm_days(release_days: list[date]) -> int | None:
    """The middle gap between recent release days, or None when there are too few."""
    days = sorted(set(release_days))[-RELEASE_DAYS_KEPT:]
    if len(days) < MIN_RELEASE_DAYS:
        return None
    gaps = [(later - earlier).days for earlier, later in pairwise(days)]
    return max(1, min(round(median(gaps)), LONGEST_RHYTHM))


def is_due(release_days: list[date], today: date) -> bool:
    """Whether a scheduled discovery run should ask the source about this series today.

    Asked every run from the day before a chapter is expected to the day after.
    Late beyond that, once per rhythm, and once every four weeks after ten
    missed releases. Stateless on purpose: it needs nothing but the chapters,
    so there is no schedule to keep in step with them.
    """
    rhythm = rhythm_days(release_days)
    if rhythm is None:
        return True
    since = (today - max(release_days)).days
    if since < rhythm - 1:
        return False
    if since <= rhythm + 1:
        return True
    late = since - (rhythm + 1)
    missed = since // rhythm
    every = rhythm if missed < MISSES_BEFORE_BACKING_OFF else LONGEST_RHYTHM
    return late % every == 0


async def release_days(
    session: AsyncSession, series_ids: list[int] | None = None
) -> dict[int, list[date]]:
    """Each series' recent release days, as Soshuhen saw them.

    Days are UTC: the rule compares gaps, and the gaps are the same in any zone.
    """
    rows = (
        await session.execute(
            text(
                """
                select series_id, day from (
                    select c.series_id, (c.discovered_at at time zone 'UTC')::date as day,
                           dense_rank() over (
                               partition by c.series_id
                               order by (c.discovered_at at time zone 'UTC')::date desc
                           ) as recency
                      from chapter c
                     where (cast(:ids as bigint[]) is null
                            or c.series_id = any(cast(:ids as bigint[])))
                       and c.discovered_at > (
                           select min(m.discovered_at) from source_mapping m
                            where m.series_id = c.series_id
                       )
                       and not exists (
                           select 1 from source_mapping m
                            where m.series_id = c.series_id
                              and m.discovered_at = c.discovered_at
                       )
                ) ranked
                 where recency <= :kept
                 group by series_id, day
                """
            ),
            {"ids": series_ids, "kept": RELEASE_DAYS_KEPT},
        )
    ).all()
    found: dict[int, list[date]] = {}
    for series_id, day in rows:
        found.setdefault(series_id, []).append(day)
    return found
