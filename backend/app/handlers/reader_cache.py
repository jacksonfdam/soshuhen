"""The database side of the reader cache, shared by `api` and the download lane."""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.reader import pages as page_json
from app.sources.base import PageRef


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
