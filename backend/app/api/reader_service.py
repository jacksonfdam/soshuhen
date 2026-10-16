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

from app import settings_store
from app.config import get_settings
from app.downloader.cbz import page_extension
from app.downloader.fetcher import PageFetchError, fetch_pages
from app.downloader.limits import reader_semaphore
from app.enums import JobType
from app.handlers import progress_events
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


class ProseChapter(RuntimeError):
    """A light novel chapter. This reader draws page images, and an EPUB opened
    as a zip would show its embedded illustrations as if they were the pages."""


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
    series_kind: str | None


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
                   s.canonical_title as series_title, m.source_site,
                   s.kind as series_kind
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
    found = ChapterRow(**row._mapping)
    if found.series_kind == "prose":
        raise ProseChapter(f"chapter {chapter_id} belongs to a light novel")
    return found


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
        try:
            return archive.read_page(found, index)
        except ValueError as exc:
            # A member named like an image that is not one. That page is
            # broken; the pages around it are not.
            raise PageFailed(f"page {index} of chapter {row.id} is not an image") from exc

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


async def series_exists(session: AsyncSession, series_id: int) -> bool:
    found = await session.execute(text("select 1 from series where id = :id"), {"id": series_id})
    return found.first() is not None


async def neighbours(
    session: AsyncSession, row: ChapterRow
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    async def one(query: str) -> dict[str, Any] | None:
        found = (await session.execute(text(query), {"s": row.series_id, "n": row.number})).first()
        if found is None:
            return None
        return {"id": found.id, "number": float(found.number), "title": found.title}

    previous = await one(
        "select id, number, title from chapter"
        " where series_id = :s and number < :n order by number desc limit 1"
    )
    following = await one(
        "select id, number, title from chapter"
        " where series_id = :s and number > :n order by number asc limit 1"
    )
    return previous, following


async def position_in(session: AsyncSession, row: ChapterRow) -> int | None:
    result = await session.execute(
        text("select chapter_id, page from reading_position where series_id = :s"),
        {"s": row.series_id},
    )
    found = result.first()
    return found.page if found is not None and found.chapter_id == row.id else None


async def save_position(
    session: AsyncSession, series_id: int, chapter_id: int, page: int
) -> None:
    owner = await session.execute(
        text("select 1 from chapter where id = :c and series_id = :s"),
        {"c": chapter_id, "s": series_id},
    )
    if owner.first() is None:
        raise ChapterMissing(f"chapter {chapter_id} is not part of series {series_id}")
    await session.execute(
        text(
            """
            insert into reading_position (series_id, chapter_id, page, updated_at)
            values (:s, :c, :p, now())
            on conflict (series_id) do update
               set chapter_id = excluded.chapter_id, page = excluded.page,
                   updated_at = excluded.updated_at
            """
        ),
        {"s": series_id, "c": chapter_id, "p": page},
    )


async def effective_prefs(session: AsyncSession, series_id: int) -> dict[str, Any]:
    result = await session.execute(
        text("select mode, scale, background from series_reader_pref where series_id = :s"),
        {"s": series_id},
    )
    found = result.first()
    if found is not None:
        return {
            "mode": found.mode,
            "scale": found.scale,
            "background": found.background,
            "custom": True,
        }
    return {
        "mode": await settings_store.get(session, settings_store.READER_DEFAULT_MODE),
        "scale": await settings_store.get(session, settings_store.READER_DEFAULT_SCALE),
        "background": await settings_store.get(
            session, settings_store.READER_DEFAULT_BACKGROUND
        ),
        "custom": False,
    }


async def save_prefs(
    session: AsyncSession, series_id: int, mode: str, scale: str, background: str
) -> None:
    await session.execute(
        text(
            """
            insert into series_reader_pref (series_id, mode, scale, background)
            values (:s, :m, :sc, :b)
            on conflict (series_id) do update
               set mode = excluded.mode, scale = excluded.scale,
                   background = excluded.background
            """
        ),
        {"s": series_id, "m": mode, "sc": scale, "b": background},
    )


async def save_defaults(session: AsyncSession, mode: str, scale: str, background: str) -> None:
    await settings_store.set_value(session, settings_store.READER_DEFAULT_MODE, mode)
    await settings_store.set_value(session, settings_store.READER_DEFAULT_SCALE, scale)
    await settings_store.set_value(session, settings_store.READER_DEFAULT_BACKGROUND, background)


async def resume(session: AsyncSession, series_id: int) -> dict[str, int]:
    saved = await session.execute(
        text(
            """
            select p.chapter_id, p.page from reading_position p
              join chapter c on c.id = p.chapter_id
             where p.series_id = :s
            """
        ),
        {"s": series_id},
    )
    found = saved.first()
    if found is not None:
        return {"chapter_id": found.chapter_id, "page": found.page}

    # The first chapter past the furthest one read, or the first chapter at
    # all when none is past it, so a series read to the end still opens.
    furthest = await progress_events.furthest_read(session, series_id)
    result = await session.execute(
        text(
            """
            select id from chapter where series_id = :s
             order by (number > :furthest) desc, number asc
             limit 1
            """
        ),
        {"s": series_id, "furthest": furthest},
    )
    chapter_id = result.scalar_one_or_none()
    if chapter_id is None:
        raise ChapterMissing(f"series {series_id} has no chapters")
    return {"chapter_id": chapter_id, "page": 0}
