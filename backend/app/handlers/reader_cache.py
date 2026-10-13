"""The database side of the reader cache, shared by `api` and the download lane."""

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.reader import cache
from app.reader import pages as page_json
from app.sources.base import PageRef

# A week: long enough that a chapter put down on Friday is still cached on
# Monday, short enough that a series abandoned mid-chapter does not hold its
# pages for good.
READER_CACHE_MAX_AGE = 7 * 86400


async def stored_page_list(session: AsyncSession, chapter_id: int) -> list[PageRef] | None:
    result = await session.execute(
        text("select pages from chapter_page_list where chapter_id = :id"), {"id": chapter_id}
    )
    raw = result.scalar_one_or_none()
    return None if raw is None else page_json.load(raw)


async def store_page_list(session: AsyncSession, chapter_id: int, pages: list[PageRef]) -> None:
    await session.execute(
        text(
            """
            insert into chapter_page_list (chapter_id, pages, fetched_at)
            values (:id, cast(:pages as jsonb), now())
            on conflict (chapter_id) do update
               set pages = excluded.pages, fetched_at = excluded.fetched_at
            """
        ),
        {"id": chapter_id, "pages": json.dumps(page_json.dump(pages))},
    )


async def prune(
    session: AsyncSession, root: Path, *, max_age_seconds: float = READER_CACHE_MAX_AGE
) -> int:
    stale = cache.stale_chapters(root, max_age_seconds)
    for chapter_id in stale:
        cache.remove(root, chapter_id)
    if stale:
        # Back to known only from streaming: a chapter downloaded meanwhile
        # keeps the state that says so.
        await session.execute(
            text(
                "update chapter set state = 'known'"
                " where id = any(cast(:ids as bigint[])) and state = 'streaming'"
            ),
            {"ids": stale},
        )
    return len(stale)
