"""Everything the reader routes do that is not HTTP.

Kept apart from the routes so the page logic reads as one piece: which copy of
a chapter answers, how a stream falls back when its list goes stale, and when a
cache becomes a download.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.downloader.cbz import page_extension
from app.downloader.fetcher import PageFetchError, fetch_pages
from app.downloader.limits import reader_semaphore
from app.enums import JobType
from app.handlers.base import PermanentError
from app.handlers.download_chapter import load_catalogue_row
from app.handlers.reader_cache import store_page_list, stored_page_list
from app.queue import repo
from app.reader import archive, cache
from app.sources import source_for_url
from app.sources.base import ChapterUnavailable, PageRef
from app.sources.net import get_client


class ChapterMissing(LookupError):
    pass


class NoMapping(RuntimeError):
    """Not in the library, and no confirmed source to stream it from."""


class Unavailable(RuntimeError):
    """The source says the chapter is gone."""


class PageFailed(RuntimeError):
    """One page could not be fetched. The chapter may still be fine."""


@dataclass(frozen=True)
class ChapterRow:
    id: int
    series_id: int
    number: Decimal
    title: str | None
    state: str
    file_path: str | None
    komga_book_id: str | None
    chapter_url: str | None
    series_title: str
    source_site: str | None


# One page-list request per chapter at a time. A manifest and the first page
# arrive together when a chapter opens, and both would otherwise ask the
# source for the same list. Keyed by the running loop too: a lock belongs to
# the loop it first waited on, and the test suite gives every test its own.
_list_locks: dict[tuple[int, int], asyncio.Lock] = {}


def cache_root() -> Path:
    return get_settings().reader_cache_path


async def chapter(session: AsyncSession, chapter_id: int) -> ChapterRow:
    result = await session.execute(
        text(
            """
            select c.id, c.series_id, c.number, c.title, c.state, c.file_path,
                   c.komga_book_id, c.source_url as chapter_url,
                   s.canonical_title as series_title, m.source_site
              from chapter c
              join series s on s.id = c.series_id
              left join source_mapping m on m.series_id = s.id and m.active
             where c.id = :id
             order by m.confirmed_at desc nulls last
             limit 1
            """
        ),
        {"id": chapter_id},
    )
    row = result.first()
    if row is None:
        raise ChapterMissing(f"chapter {chapter_id} not found")
    return ChapterRow(**row._mapping)


def archive_of(row: ChapterRow) -> Path | None:
    if row.file_path is None:
        return None
    path = Path(row.file_path)
    if not path.is_file() or not archive.inside(path, get_settings().library_path):
        return None
    return path


async def page_count(
    session: AsyncSession, row: ChapterRow
) -> tuple[Literal["archive", "stream"], int]:
    found = archive_of(row)
    if found is not None:
        return "archive", len(archive.page_names(found))
    return "stream", len(await page_list(session, row))


async def serve_page(session: AsyncSession, row: ChapterRow, index: int) -> tuple[bytes, str]:
    if index < 0:
        raise IndexError(index)
    found = archive_of(row)
    if found is not None:
        return archive.read_page(found, index)

    root = cache_root()
    cached = cache.find_page(root, row.id, index)
    if cached is not None:
        cache.touch(root, row.id)
        data = cached.read_bytes()
        return data, page_extension(data)

    data = await _fetch_streamed(session, row, index)
    cache.write_page(root, row.id, index, data)
    await _mark_streaming(session, row.id)
    await _queue_assembly_when_complete(session, row)
    return data, page_extension(data)


async def page_list(
    session: AsyncSession, row: ChapterRow, *, refresh: bool = False
) -> list[PageRef]:
    key = (id(asyncio.get_running_loop()), row.id)
    lock = _list_locks.setdefault(key, asyncio.Lock())
    async with lock:
        if not refresh:
            stored = await stored_page_list(session, row.id)
            if stored is not None:
                return stored
        source = _source_of(row)
        async with await reader_semaphore(row.source_site):
            try:
                pages = await source.list_pages(row.chapter_url)
            except ChapterUnavailable as exc:
                raise Unavailable(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise PageFailed(f"could not list pages: {exc}") from exc
        if not pages:
            raise Unavailable(f"no pages listed for {row.chapter_url}")
        await store_page_list(session, row.id, pages)
        # Committed here rather than by the route: two requests waiting on this
        # lock read through separate sessions, and the second must see the list.
        await session.commit()
        return pages


def _source_of(row: ChapterRow) -> Any:
    if row.source_site is None:
        raise NoMapping(f"series {row.series_id} has no confirmed source")
    if row.chapter_url is None:
        raise Unavailable(f"chapter {row.id} has no source url of its own")
    try:
        return source_for_url(row.chapter_url)
    except ValueError as exc:
        raise NoMapping(str(exc)) from exc


async def _client_of(session: AsyncSession, row: ChapterRow):
    try:
        return get_client(await load_catalogue_row(session, row.source_site))
    except PermanentError as exc:
        raise NoMapping(str(exc)) from exc


async def _fetch_streamed(session: AsyncSession, row: ChapterRow, index: int) -> bytes:
    source = _source_of(row)
    client = await _client_of(session, row)
    pages = await page_list(session, row)
    if index >= len(pages):
        raise IndexError(index)
    try:
        return await _fetch_one(source, client, row.source_site, pages[index])
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (404, 410):
            raise PageFailed(str(exc)) from exc

    # The same rule fetch_chapter applies: a 404 on a list that resolved a
    # while ago is the address going stale, so ask for the list once more and
    # no more than once.
    pages = await page_list(session, row, refresh=True)
    if index >= len(pages):
        raise IndexError(index)
    try:
        return await _fetch_one(source, client, row.source_site, pages[index])
    except httpx.HTTPStatusError as exc:
        raise PageFailed(str(exc)) from exc


async def _fetch_one(source: Any, client: Any, site: str, page: PageRef) -> bytes:
    async with await reader_semaphore(site):
        try:
            [data] = await fetch_pages(client, [page], transform=source.descramble)
        except (PageFetchError, httpx.TransportError) as exc:
            raise PageFailed(str(exc)) from exc
    return data


async def _mark_streaming(session: AsyncSession, chapter_id: int) -> None:
    # Only from a resting state. A chapter already queued or downloading keeps
    # its state: the download lane owns it now, and it will reach the library
    # on its own.
    await session.execute(
        text(
            "update chapter set state = 'streaming'"
            " where id = :id and state in ('known', 'failed')"
        ),
        {"id": chapter_id},
    )


async def _queue_assembly_when_complete(session: AsyncSession, row: ChapterRow) -> None:
    listed = await stored_page_list(session, row.id)
    if listed is None or cache.cached_count(cache_root(), row.id) < len(listed):
        return
    state = (
        await session.execute(text("select state from chapter where id = :id"), {"id": row.id})
    ).scalar_one()
    if state != "streaming":
        return
    # The dedupe key is what makes two requests for the last page queue one
    # job: the partial unique index refuses the second while the first waits.
    await repo.enqueue(
        session,
        JobType.DOWNLOAD_CHAPTER,
        {"chapter_id": row.id, "from_cache": True},
        priority=50,
        series_id=row.series_id,
        dedupe_key=f"download_chapter:{row.id}",
    )
