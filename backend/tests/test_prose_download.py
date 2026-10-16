"""A prose series downloads through the same handlers, as EPUB."""

import zipfile
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.downloader.paths import chapter_path
from app.enums import JobType
from app.handlers import download_batch, download_chapter
from app.handlers.base import JobContext, PermanentError
from app.handlers.prose_download import cover_for
from app.queue import repo
from app.sources.base import (
    ChapterText,
    ChapterUnavailable,
    NotConfigured,
    PageRef,
    ProseSource,
    RegisteredSource,
    SignInRequired,
    install_registry,
)
from tests.test_download_batch_handler import (  # noqa: F401 - clean is an autouse fixture
    EVERY_TYPE,
    Stub,
    _catalogue,
    _chapter,
    _context,
    _series,
    clean,
)

pytestmark = pytest.mark.asyncio

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeProse(ProseSource):
    domains = ()

    def __init__(self, site: str, locked: frozenset[str] = frozenset()) -> None:
        self.site = site
        self._locked = locked

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        if chapter_url in self._locked:
            raise ChapterUnavailable("locked")
        return ChapterText(
            title=None, body="<p>Text {{img:0}}</p>", images=[PageRef(url="/art.png")]
        )


async def _make_prose(session, series_id: int) -> None:
    await session.execute(
        text("update series set kind = 'prose' where id = :id"), {"id": series_id}
    )
    await session.commit()


async def test_a_prose_batch_writes_epubs():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [await _chapter(session, series_id, str(n), u) for n, u in zip((1, 2), urls)]
            ctx = await _context(session, ids)
            await download_batch.handle(ctx)
            await session.commit()
            rows = (
                await session.execute(
                    text("select state, file_path from chapter order by number")
                )
            ).all()
        assert [r.state for r in rows] == ["downloaded", "downloaded"]
        for row in rows:
            assert row.file_path.endswith(".epub")
            with zipfile.ZipFile(row.file_path) as archive:
                assert archive.read("mimetype") == b"application/epub+zip"
                assert "OEBPS/images/001.png" in archive.namelist()
    finally:
        stub.close()


async def test_a_locked_prose_chapter_is_skipped_not_fatal():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        source = FakeProse(stub.key, locked=frozenset({urls[1]}))
        install_registry({stub.key: RegisteredSource(source, stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [await _chapter(session, series_id, str(n), u) for n, u in zip((1, 2), urls)]
            ctx = await _context(session, ids)
            await download_batch.handle(ctx)
            await session.commit()
            states = (
                await session.execute(text("select state from chapter order by number"))
            ).scalars().all()
        assert states == ["downloaded", "skipped"]
    finally:
        stub.close()


async def test_a_prose_batch_skips_a_chapter_already_on_disk_as_cbz():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            existing = chapter_path(
                Path(get_settings().library_path),
                "rebirth-monarch-of-the-dead",
                Decimal("1"),
                "Chapter 1",
            )
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"old comic file")
            ctx = await _context(session, [chapter_id])
            await download_batch.handle(ctx)
            await session.commit()
            row = (await session.execute(text("select state, file_path from chapter"))).one()
        assert row.state == "downloaded"
        assert row.file_path == str(existing)
    finally:
        stub.close()


async def test_a_single_prose_chapter_job_writes_an_epub():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            await repo.enqueue(session, JobType.DOWNLOAD_CHAPTER, {"chapter_id": chapter_id})
            await session.commit()
            job = await repo.lease(session, types=EVERY_TYPE)
            await session.commit()
            await download_chapter.handle(JobContext(session=session, job=job))
            await session.commit()
            path = (await session.execute(text("select file_path from chapter"))).scalar_one()
        assert path.endswith(".epub")
    finally:
        stub.close()


class ComicOnly:
    domains: tuple[str, ...] = ()

    def __init__(self, site: str) -> None:
        self.site = site

    async def list_pages(self, chapter_url, *, language="en"):
        return []

    def descramble(self, data, page):
        return data


async def test_a_prose_series_mapped_to_a_comic_source_fails_the_batch_by_name():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(ComicOnly(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            ctx = await _context(session, [chapter_id])
            with pytest.raises(PermanentError, match=stub.key):
                await download_batch.handle(ctx)
    finally:
        stub.close()


async def test_a_comic_series_mapped_to_a_prose_source_fails_the_chapter_job():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            await repo.enqueue(session, JobType.DOWNLOAD_CHAPTER, {"chapter_id": chapter_id})
            await session.commit()
            job = await repo.lease(session, types=EVERY_TYPE)
            await session.commit()
            with pytest.raises(PermanentError, match="prose source"):
                await download_chapter.handle(JobContext(session=session, job=job))
    finally:
        stub.close()


async def test_a_cover_that_cannot_be_fetched_ships_the_chapter_without_one(monkeypatch):
    async def broken(ctx, series_id):
        raise httpx.ConnectError("cdn down")

    monkeypatch.setattr("app.handlers.prose_download.fetch_series_artwork", broken)
    logged: list[str] = []

    class Ctx:
        async def log(self, message, **kwargs):
            logged.append(message)

    assert await cover_for(Ctx(), 1) is None
    assert any("cover unavailable" in line for line in logged)


async def test_a_cover_in_an_unrecognised_format_ships_the_chapter_without_one(monkeypatch):
    async def svg(ctx, series_id):
        return b"<svg/>"

    monkeypatch.setattr("app.handlers.prose_download.fetch_series_artwork", svg)
    logged: list[str] = []

    class Ctx:
        async def log(self, message, **kwargs):
            logged.append(message)

    assert await cover_for(Ctx(), 1) is None
    assert any("cover unavailable" in line for line in logged)


async def test_a_prose_series_on_a_comic_source_is_refused_before_the_chapter_is_touched():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(ComicOnly(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            before = (
                await session.execute(
                    text("select state from chapter where id = :id"), {"id": chapter_id}
                )
            ).scalar_one()
            await repo.enqueue(session, JobType.DOWNLOAD_CHAPTER, {"chapter_id": chapter_id})
            await session.commit()
            job = await repo.lease(session, types=EVERY_TYPE)
            await session.commit()
            with pytest.raises(PermanentError, match="comic source"):
                await download_chapter.handle(JobContext(session=session, job=job))
            after = (
                await session.execute(
                    text("select state from chapter where id = :id"), {"id": chapter_id}
                )
            ).scalar_one()
        assert after == before
    finally:
        stub.close()


class SignedOutProse(FakeProse):
    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise SignInRequired("J-Novel Club sign-in expired; sign in again in Settings")


class SignedOutHalfway(FakeProse):
    """The sign-in lapses after the first chapter of the batch is saved."""

    async def fetch_chapter(self, chapter_url, *, language="en"):
        if chapter_url.endswith("/1"):
            return await super().fetch_chapter(chapter_url, language=language)
        raise SignInRequired("J-Novel Club sign-in expired; sign in again in Settings")


class NotSetUpForOneChapter(FakeProse):
    """ComiciViewer's shape: one chapter needs a login this deployment lacks."""

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotConfigured("this chapter needs a login")


async def test_an_expired_sign_in_leaves_the_chapters_known():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        install_registry({stub.key: RegisteredSource(SignedOutProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [
                await _chapter(session, series_id, str(n), u)
                for n, u in zip((1, 2), urls, strict=True)
            ]
            ctx = await _context(session, ids)
            with pytest.raises(PermanentError, match="sign in again"):
                await download_batch.handle(ctx)
            await session.commit()
            states = (
                await session.execute(text("select state from chapter order by number"))
            ).scalars().all()
        assert states == ["known", "known"]
    finally:
        stub.close()


async def test_chapters_saved_before_the_sign_in_lapsed_stay_and_get_scanned():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        install_registry({stub.key: RegisteredSource(SignedOutHalfway(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [
                await _chapter(session, series_id, str(n), u)
                for n, u in zip((1, 2), urls, strict=True)
            ]
            ctx = await _context(session, ids)
            with pytest.raises(PermanentError, match="sign in again"):
                await download_batch.handle(ctx)
            await session.commit()
            states = (
                await session.execute(text("select state from chapter order by number"))
            ).scalars().all()
            scans = (
                await session.execute(text("select count(*) from job where type = 'komga_scan'"))
            ).scalar_one()
        assert states == ["downloaded", "known"]
        assert scans == 1
    finally:
        stub.close()


async def test_a_source_not_set_up_for_one_chapter_is_not_a_sign_in_problem():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry(
            {stub.key: RegisteredSource(NotSetUpForOneChapter(stub.key), stub.base_url)}
        )
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [await _chapter(session, series_id, "1", url)]
            ctx = await _context(session, ids)
            with pytest.raises(NotConfigured) as raised:
                await download_batch.handle(ctx)
        assert not isinstance(raised.value, PermanentError)
    finally:
        stub.close()
