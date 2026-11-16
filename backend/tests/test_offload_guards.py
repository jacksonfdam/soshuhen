"""Nothing turns an offloaded chapter or volume back into a server download.

Komga keeps deleted books in its trash and keeps reporting them, and J-Novel
Club revises volumes; either would otherwise undo the space an offload freed.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import chapter_discover, komga_scan
from app.handlers.base import JobContext
from app.handlers.jnc_library_sync import has_newer_revision, needs_download
from app.komga.client import KomgaBook
from app.queue import repo

OLD = datetime(2026, 9, 1, tzinfo=UTC)
NEW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


def _book(book_id, filename):
    return KomgaBook(id=book_id, series_id="K1", name=filename, path=f"/manga/a/{filename}",
                     completed=False, page=0)


class FakeKomga:
    has_credentials = True

    def __init__(self, books):
        self.books = books
        self.patched = []

    async def find_series(self, root, slug, library_id=None):
        return "K1"

    async def books_of_series(self, series_id):
        return self.books

    async def update_book_metadata(self, book_id, body):
        self.patched.append(book_id)


async def _series(session, kind="comic") -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind,"
                " komga_series_id) values ('A', 'a', false, '{}'::jsonb, :k, 'K1') returning id"
            ),
            {"k": kind},
        )
    ).scalar_one()


async def _offloaded_chapter(session, series_id, number=1) -> int:
    return (
        await session.execute(
            text(
                "insert into chapter (series_id, number, state) values (:s, :n, 'offloaded')"
                " returning id"
            ),
            {"s": series_id, "n": number},
        )
    ).scalar_one()


async def _state(session, table, row_id):
    return (
        await session.execute(
            text(f"select state, file_path from {table} where id = :id"), {"id": row_id}
        )
    ).one()


async def test_komga_reconcile_leaves_offloaded_chapter(monkeypatch):
    komga = FakeKomga([_book("B1", "a Ch.1.cbz")])
    monkeypatch.setattr(chapter_discover, "from_settings", lambda: komga)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _offloaded_chapter(session, series_id)
        await session.commit()
        await chapter_discover.reconcile_with_komga(session, series_id, "a")
        await session.commit()
        row = await _state(session, "chapter", chapter_id)
    assert row.state == "offloaded"
    assert row.file_path is None


async def test_adopt_book_ids_leaves_offloaded_chapter():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _offloaded_chapter(session, series_id)
        await session.commit()
        await komga_scan.adopt_book_ids(session, series_id, [_book("B1", "a Ch.1.cbz")])
        await session.commit()
        row = await _state(session, "chapter", chapter_id)
    assert row.state == "offloaded"


async def test_komga_scan_leaves_offloaded_volume():
    komga = FakeKomga([_book("B1", "a - Vol.0016.epub")])
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "prose")
        volume_id = (
            await session.execute(
                text(
                    "insert into volume (series_id, number, source_volume_id, status, state)"
                    " values (:s, 16, 'VOL-16', 'owned', 'offloaded') returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
        await session.commit()
        ctx = JobContext(session=session, job=job)
        await komga_scan.reconcile_volumes(ctx, komga, series_id, komga.books)
        await session.commit()
        row = await _state(session, "volume", volume_id)
    assert row.state == "offloaded"
    assert row.file_path is None


def test_needs_download_false_for_offloaded_even_after_revision():
    assert not needs_download(status="owned", has_link=True, state="offloaded",
                              downloaded_updated=OLD, last_updated=NEW)
    assert not needs_download(status="owned", has_link=True, state="offloaded",
                              downloaded_updated=None, last_updated=NEW)


def test_needs_download_unchanged_for_other_states():
    assert needs_download(status="owned", has_link=True, state="downloaded",
                          downloaded_updated=OLD, last_updated=NEW)


def test_has_newer_revision():
    assert has_newer_revision(OLD, NEW)
    assert not has_newer_revision(NEW, NEW)
    assert not has_newer_revision(None, NEW)
    assert not has_newer_revision(OLD, None)


async def test_queue_missing_never_queues_offloaded():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await session.execute(text("update series set auto_download = true where id = :id"),
                              {"id": series_id})
        await _offloaded_chapter(session, series_id)
        await repo.enqueue(session, JobType.CHAPTER_DISCOVER, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=[str(JobType.CHAPTER_DISCOVER)])
        await session.commit()
        await chapter_discover.queue_missing(JobContext(session=session, job=job), series_id)
        await session.commit()
        jobs = (
            await session.execute(text("select count(*) from job where type <> 'chapter_discover'"))
        ).scalar_one()
    assert jobs == 0


async def test_adopt_book_ids_leaves_a_marked_row_with_its_path():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, file_path)"
                    " values (:s, 1, 'offloaded', '/manga/a/a Ch.1.cbz') returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.commit()
        await komga_scan.adopt_book_ids(session, series_id, [_book("B1", "a Ch.1.cbz")])
        await session.commit()
        row = await _state(session, "chapter", chapter_id)
    assert row.state == "offloaded"
