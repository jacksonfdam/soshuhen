"""Everything the reader routes do that is not HTTP.

Kept apart from the routes so the page logic reads as one piece: which copy of
a chapter answers, how a stream falls back when its list goes stale, and when a
cache becomes a download.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
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
    """A light novel chapter asked of the page routes, which only draw images."""


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


async def chapter(
    session: AsyncSession, chapter_id: int, *, prose_ok: bool = False
) -> ChapterRow:
    """A chapter as the page routes see it.

    Prose is refused unless the caller says otherwise: the page routes draw
    images, and an EPUB opened as a zip would show its embedded illustrations
    as if they were the pages. Only finishing a chapter means the same thing
    for both kinds.
    """
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
    if found.series_kind == "prose" and not prose_ok:
        raise ProseChapter(f"chapter {chapter_id} belongs to a light novel")
    return found


def library_file(file_path: str | None) -> Path | None:
    """The stored path when it names a real file inside the library, else None."""
    if file_path is None:
        return None
    path = Path(file_path)
    if not path.is_file() or not archive.inside(path, get_settings().library_path):
        return None
    return path


def readable(file_path: str | None) -> bool:
    return library_file(file_path) is not None


def archive_of(row: ChapterRow) -> Path | None:
    return library_file(row.file_path)


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
    session: AsyncSession,
    series_id: int,
    *,
    chapter_id: int | None = None,
    volume_id: int | None = None,
    page: int,
    fraction: float | None = None,
    read_at: datetime | None = None,
) -> bool:
    """Store where reading stands. Returns whether the row was written.

    A position names a chapter or, for a light novel volume that has no
    chapters, a volume. Prose also sends `fraction`: `page` is then the section
    and this how far through it.

    `read_at` comes from a client that read offline and is replaying it later.
    Given one, the write applies only if it is newer than what is stored, so a
    position from this morning's train cannot overwrite this evening's. Without
    one the write always applies, which is what the web reader relies on.
    """
    table, book_id = ("chapter", chapter_id) if chapter_id is not None else ("volume", volume_id)
    owner = await session.execute(
        text(f"select 1 from {table} where id = :b and series_id = :s"),
        {"b": book_id, "s": series_id},
    )
    if owner.first() is None:
        raise ChapterMissing(f"{table} {book_id} is not part of series {series_id}")
    # Clamped to now(): a phone whose clock runs fast would otherwise win every
    # replay, including against reading done after it.
    newer_only = "where reading_position.updated_at < excluded.updated_at" if read_at else ""
    result = await session.execute(
        text(
            f"""
            insert into reading_position
                   (series_id, chapter_id, volume_id, page, fraction, updated_at)
            values (:s, :c, :v, :p, :f,
                    least(coalesce(cast(:at as timestamptz), now()), now()))
            on conflict (series_id) do update
               set chapter_id = excluded.chapter_id, volume_id = excluded.volume_id,
                   page = excluded.page, fraction = excluded.fraction,
                   updated_at = excluded.updated_at
             {newer_only}
            returning 1
            """
        ),
        {"s": series_id, "c": chapter_id, "v": volume_id, "p": page, "f": fraction, "at": read_at},
    )
    return result.first() is not None


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


# --- Prose -----------------------------------------------------------------
#
# A novel is read from the EPUB already on disk: one per chapter for web novel
# chapters, one per volume for a light novel volume. Nothing streams; a book
# that is not downloaded is not offered.

ProseKind = Literal["chapter", "volume"]


class WrongKind(RuntimeError):
    """The row exists but is not a book this reader opens: a comic chapter, or
    a web novel volume, which is only a range of chapters with no file."""


@dataclass(frozen=True)
class ProseBook:
    kind: ProseKind
    id: int
    series_id: int
    series_title: str
    title: str | None
    number: Decimal
    edition: str | None
    path: Path
    komga_book_id: str | None


async def prose_book(session: AsyncSession, kind: ProseKind, book_id: int) -> ProseBook:
    if kind == "chapter":
        query = """
            select c.id, c.series_id, s.canonical_title as series_title, c.title, c.number,
                   null as edition, c.file_path, c.komga_book_id, s.kind
              from chapter c join series s on s.id = c.series_id
             where c.id = :id
        """
    else:
        query = """
            select v.id, v.series_id, s.canonical_title as series_title, v.title, v.number,
                   v.edition, v.file_path, v.komga_book_id, s.kind
              from volume v join series s on s.id = v.series_id
             where v.id = :id
        """
    row = (await session.execute(text(query), {"id": book_id})).first()
    if row is None:
        raise ChapterMissing(f"{kind} {book_id} not found")
    if kind == "chapter" and row.kind != "prose":
        raise WrongKind(f"chapter {book_id} is a comic chapter")
    if kind == "volume" and row.edition == "web":
        raise WrongKind(f"volume {book_id} is a web novel volume; read its chapters")
    path = library_file(row.file_path)
    if path is None:
        raise ChapterMissing(f"{kind} {book_id} has no file in the library")
    return ProseBook(
        kind=kind,
        id=row.id,
        series_id=row.series_id,
        series_title=row.series_title,
        title=row.title,
        number=row.number,
        edition=row.edition,
        path=path,
        komga_book_id=row.komga_book_id,
    )


async def prose_volume_row(session: AsyncSession, volume_id: int) -> Any:
    """A light volume to mark read. Unlike opening it, finishing it needs no
    file: the Android app reads its own copy and only reports the end."""
    row = (
        await session.execute(
            text("select id, series_id, edition, komga_book_id from volume where id = :id"),
            {"id": volume_id},
        )
    ).first()
    if row is None:
        raise ChapterMissing(f"volume {volume_id} not found")
    if row.edition == "web":
        raise WrongKind(f"volume {volume_id} is a web novel volume; finish its chapters")
    return row


def _book_ref(kind: ProseKind, row: Any) -> dict[str, Any]:
    return {"kind": kind, "id": row.id, "number": float(row.number), "title": row.title}


async def _readable_rows(session: AsyncSession, book: ProseBook) -> list[Any]:
    if book.kind == "chapter":
        query = "select id, number, title, file_path from chapter where series_id = :s"
        params: dict[str, Any] = {"s": book.series_id}
    else:
        query = (
            "select id, number, title, file_path from volume"
            " where series_id = :s and edition = :e"
        )
        params = {"s": book.series_id, "e": book.edition}
    rows = (await session.execute(text(query + " order by number"), params)).all()
    # Readable only: "next" that opens onto a missing file is a dead end.
    return [row for row in rows if row.id == book.id or readable(row.file_path)]


async def prose_neighbours(
    session: AsyncSession, book: ProseBook
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    rows = await _readable_rows(session, book)
    at = next(i for i, row in enumerate(rows) if row.id == book.id)
    previous = _book_ref(book.kind, rows[at - 1]) if at > 0 else None
    following = _book_ref(book.kind, rows[at + 1]) if at + 1 < len(rows) else None
    return previous, following


async def prose_position(session: AsyncSession, book: ProseBook) -> dict[str, Any] | None:
    column = "chapter_id" if book.kind == "chapter" else "volume_id"
    row = (
        await session.execute(
            text(f"select page, fraction from reading_position where series_id = :s and {column} = :b"),
            {"s": book.series_id, "b": book.id},
        )
    ).first()
    if row is None:
        return None
    return {"section": row.page, "fraction": row.fraction or 0.0}


async def prose_prefs(session: AsyncSession) -> dict[str, Any]:
    return {
        "font_size": await settings_store.get_int(session, settings_store.READER_PROSE_FONT_SIZE),
        "theme": await settings_store.get(session, settings_store.READER_PROSE_THEME),
    }


async def save_prose_prefs(session: AsyncSession, font_size: int, theme: str) -> None:
    await settings_store.set_value(session, settings_store.READER_PROSE_FONT_SIZE, str(font_size))
    await settings_store.set_value(session, settings_store.READER_PROSE_THEME, theme)


async def prose_resume(session: AsyncSession, series_id: int) -> dict[str, Any]:
    """Where to open a novel: the saved place, else the first book not yet read."""
    saved = (
        await session.execute(
            text(
                "select chapter_id, volume_id, page, fraction from reading_position"
                " where series_id = :s"
            ),
            {"s": series_id},
        )
    ).first()
    if saved is not None:
        kind: ProseKind = "chapter" if saved.chapter_id is not None else "volume"
        try:
            await prose_book(session, kind, saved.chapter_id or saved.volume_id)
        except (ChapterMissing, WrongKind):
            pass
        else:
            return {
                "kind": kind,
                "id": saved.chapter_id or saved.volume_id,
                "section": saved.page,
                "fraction": saved.fraction or 0.0,
            }

    volume_read = (
        await session.execute(
            text(
                "select coalesce(max(user_progress_volume), 0) from list_entry"
                " where series_id = :s"
            ),
            {"s": series_id},
        )
    ).scalar_one()
    chapter_read = await progress_events.furthest_read(session, series_id)
    volumes = (
        await session.execute(
            text(
                "select id, number, file_path from volume"
                " where series_id = :s and edition = 'light' order by number"
            ),
            {"s": series_id},
        )
    ).all()
    chapters = (
        await session.execute(
            text(
                "select c.id, c.number, c.file_path from chapter c"
                " join series s on s.id = c.series_id and s.kind = 'prose'"
                " where c.series_id = :s order by c.number"
            ),
            {"s": series_id},
        )
    ).all()
    candidates: list[tuple[ProseKind, Any]] = [
        *(("volume", v) for v in volumes if v.number > volume_read),
        *(("chapter", c) for c in chapters if c.number > chapter_read),
        *(("volume", v) for v in volumes),
        *(("chapter", c) for c in chapters),
    ]
    for kind, row in candidates:
        if readable(row.file_path):
            return {"kind": kind, "id": row.id, "section": 0, "fraction": 0.0}
    raise ChapterMissing(f"series {series_id} has nothing readable in the library")
