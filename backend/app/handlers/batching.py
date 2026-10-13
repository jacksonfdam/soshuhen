"""Turn a list of pending chapters into batch jobs."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.enums import JobType
from app.queue import repo


def chunk(ids: Sequence[int], size: int) -> list[list[int]]:
    """Bounded batches: one job for the whole backlog would be one lease held for hours."""
    size = max(size, 1)
    return [list(ids[start : start + size]) for start in range(0, len(ids), size)]


async def queue_batches(
    session: AsyncSession,
    series_id: int,
    chapter_ids: Sequence[int],
    *,
    priority: int = 100,
) -> int:
    """Enqueue one job per batch and mark those chapters queued. Returns how many."""
    if not chapter_ids:
        return 0

    handed = await queue_from_reader(session, series_id, chapter_ids, priority=priority)
    queued = len(handed)
    chapter_ids = [chapter_id for chapter_id in chapter_ids if chapter_id not in handed]

    size = await settings_store.get_int(session, settings_store.DOWNLOAD_BATCH_SIZE)
    for batch in chunk(list(chapter_ids), size):
        payload: dict[str, Any] = {"series_id": series_id, "chapter_ids": batch}
        job_id = await repo.enqueue(
            session,
            JobType.DOWNLOAD_BATCH,
            payload,
            priority=priority,
            series_id=series_id,
            dedupe_key=f"download_batch:{series_id}:{min(batch)}",
        )
        if job_id is None:
            continue
        await session.execute(
            text("update chapter set state = 'queued' where id = any(cast(:ids as bigint[]))"),
            {"ids": batch},
        )
        queued += len(batch)
    return queued


async def queue_from_reader(
    session: AsyncSession, series_id: int, chapter_ids: Sequence[int], *, priority: int = 100
) -> set[int]:
    """Hand chapters the reader is streaming to the job that builds them from its cache.

    Not into a batch: a batch would fetch every page from the source while the
    reader's cache already holds some of them, and marking them `queued` would
    take away the state that tells the reader's pages where to go. Left out
    entirely, a chapter someone opened and put down would silently miss every
    download asked for that week.

    Returns the chapters handed on. One already waiting counts: the caller
    asked for it and it is on its way.
    """
    result = await session.execute(
        text(
            "select id from chapter"
            " where id = any(cast(:ids as bigint[])) and state = 'streaming'"
        ),
        {"ids": list(chapter_ids)},
    )
    handed = {int(chapter_id) for chapter_id in result.scalars()}
    for chapter_id in sorted(handed):
        await repo.enqueue(
            session,
            JobType.DOWNLOAD_CHAPTER,
            {"chapter_id": chapter_id, "from_cache": True},
            priority=priority,
            series_id=series_id,
            dedupe_key=f"download_chapter:{chapter_id}",
        )
    return handed
