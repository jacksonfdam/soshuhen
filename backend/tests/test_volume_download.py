"""An owned volume lands in the library as J-Novel Club's own EPUB."""

import io
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError
from app.handlers.volume_download import handle
from app.queue import repo
from app.sources.base import ProseSource, RegisteredSource, SignInRequired, install_registry
from app.sources.jnovelclub import OwnedVolume

OLD = datetime(2026, 9, 1, tzinfo=UTC)
NEW = datetime(2026, 10, 1, tzinfo=UTC)


def _epub(marker: bytes = b"v1") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr("OEBPS/marker", marker)
    return buffer.getvalue()


class FakeJnc(ProseSource):
    site = "jnovelclub"
    domains = ("j-novel.club",)

    def __init__(self, *, owned=True, body=None, title="Volume 16", updated=OLD, signed_in=True):
        self.owned, self.body, self.title = owned, body, title
        self.updated, self.signed_in = updated, signed_in

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotImplementedError

    async def library(self):
        if not self.signed_in:
            raise SignInRequired("J-Novel Club sign-in expired; sign in again in Settings")
        if not self.owned:
            return []
        return [OwnedVolume("the-apothecary-diaries", "VOL-16", Decimal(16), self.title,
                            "owned", self.updated, "https://cdn.example/v16.epub?sig=x")]

    async def fetch_volume(self, link):
        return self.body if self.body is not None else _epub()


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _volume(session, *, file_path=None, downloaded_updated=None) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('The Apothecary Diaries', 'apothecary', false, '{}'::jsonb, 'prose')"
                " returning id"
            )
        )
    ).scalar_one()
    volume_id = (
        await session.execute(
            text(
                """
                insert into volume (series_id, number, source_volume_id, title, status,
                                    last_updated, last_part, state, file_path,
                                    downloaded_updated)
                values (:s, 16, 'VOL-16', 'Volume 16', 'owned', :u, 216, 'queued',
                        cast(:f as text), cast(:d as timestamptz))
                returning id
                """
            ),
            {"s": series_id, "u": OLD, "f": file_path, "d": downloaded_updated},
        )
    ).scalar_one()
    await session.commit()
    return int(volume_id)


async def _run(session, source, volume_id):
    install_registry({"jnovelclub": RegisteredSource(source, "https://labs.j-novel.club")})
    await repo.enqueue(session, JobType.VOLUME_DOWNLOAD, {"volume_id": volume_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.VOLUME_DOWNLOAD)])
    await session.commit()
    await handle(JobContext(session=session, job=job))
    await session.commit()


async def _row(session, volume_id):
    return (
        await session.execute(
            text("select state, file_path, downloaded_updated from volume where id = :id"),
            {"id": volume_id},
        )
    ).one()


async def test_an_owned_volume_is_placed_and_scanned():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await _run(session, FakeJnc(), volume_id)
        row = await _row(session, volume_id)
        assert row.state == "downloaded"
        assert row.file_path.endswith("apothecary - Vol.0016 - Volume 16.epub")
        assert Path(row.file_path).read_bytes() == _epub()
        assert row.downloaded_updated == OLD
        scans = (
            await session.execute(text("select count(*) from job where type = 'komga_scan'"))
        ).scalar_one()
        assert scans == 1


async def test_a_revision_replaces_the_file_in_place():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await _run(session, FakeJnc(), volume_id)
        await _run(session, FakeJnc(body=_epub(b"v2"), updated=NEW), volume_id)
        row = await _row(session, volume_id)
        assert Path(row.file_path).read_bytes() == _epub(b"v2")


async def test_a_renamed_revision_replaces_the_old_file():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await _run(session, FakeJnc(), volume_id)
        old = Path((await _row(session, volume_id)).file_path)
        await _run(session, FakeJnc(title="Volume 16: Revised", updated=NEW), volume_id)
        new = Path((await _row(session, volume_id)).file_path)
        assert new != old
        assert new.exists()
        assert not old.exists()
        # Only that one file: the folder holds exactly the new edition.
        assert sorted(p.name for p in new.parent.iterdir()) == [new.name]


async def test_an_html_answer_places_nothing():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(Exception, match="not an EPUB"):
            await _run(session, FakeJnc(body=b"<html>expired</html>"), volume_id)
        await session.rollback()
        row = await _row(session, volume_id)
        assert row.state != "downloaded"
        assert row.file_path is None


async def test_a_volume_gone_from_the_library_fails_for_good():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(PermanentError, match="no longer in your J-Novel Club library"):
            await _run(session, FakeJnc(owned=False), volume_id)
        await session.rollback()
        assert (await _row(session, volume_id)).state == "known"


async def test_a_lapsed_sign_in_leaves_the_volume_waiting():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(PermanentError, match="sign in again"):
            await _run(session, FakeJnc(signed_in=False), volume_id)
        await session.rollback()
        assert (await _row(session, volume_id)).state == "known"


class BrokenLibrary(FakeJnc):
    async def library(self):
        raise RuntimeError("J-Novel Club answered 503")


async def test_an_error_reading_the_library_does_not_strand_the_volume():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(RuntimeError):
            await _run(session, BrokenLibrary(), volume_id)
        await session.rollback()
        assert (await _row(session, volume_id)).state == "known"


async def test_a_volume_without_a_revision_date_is_not_downloaded_again():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await session.execute(text("update volume set last_updated = null"))
        await session.commit()
        await _run(session, FakeJnc(updated=None), volume_id)
        row = await _row(session, volume_id)
        # Something must mark this edition as on disk, or every sync re-fetches it.
        assert row.downloaded_updated is not None


async def test_a_previous_path_that_is_not_this_volume_is_never_deleted(tmp_path):
    chapter = tmp_path / "apothecary" / "apothecary - Ch.0012 - Vol.16 Extra.epub"
    chapter.parent.mkdir(parents=True)
    chapter.write_bytes(b"a chapter")
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session, file_path=str(chapter))
        await _run(session, FakeJnc(), volume_id)
    assert chapter.exists()
