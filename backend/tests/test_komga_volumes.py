"""Volume books sit right after their own parts in Komga, numbered and locked."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext
from app.handlers.komga_scan import reconcile_volumes, wanted_volume_metadata
from app.komga.client import KomgaBook, parse_books
from app.queue import repo


def test_a_volume_sorts_just_after_its_last_part():
    assert wanted_volume_metadata(Decimal(16), Decimal(216)) == {
        "number": "Vol. 16", "numberLock": True, "numberSort": 216.5, "numberSortLock": True,
    }


def test_a_volume_without_known_parts_sorts_last():
    assert wanted_volume_metadata(Decimal(3), None)["numberSort"] == 100003.0


def test_book_numbers_and_locks_are_read():
    [book] = parse_books({"content": [{
        "id": "B1", "seriesId": "S1", "name": "x", "url": "/manga/a/a - Vol.0016.epub",
        "metadata": {"number": "Vol. 16", "numberSort": 216.5,
                     "numberLock": True, "numberSortLock": True},
    }]})
    assert (book.number, book.number_sort, book.number_lock, book.number_sort_lock) == (
        "Vol. 16", 216.5, True, True,
    )


class FakeKomga:
    def __init__(self):
        self.patched: list[tuple[str, dict]] = []

    async def update_book_metadata(self, book_id, body):
        self.patched.append((book_id, body))


def _book(book_id, filename, **metadata):
    return KomgaBook(id=book_id, series_id="S1", name=filename, path=f"/manga/a/{filename}",
                     completed=False, page=0, **metadata)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


async def _ctx(session) -> tuple[JobContext, int]:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('A', 'a', false, '{}'::jsonb, 'prose') returning id"
            )
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into volume (series_id, number, source_volume_id, status, last_part, state)"
            " values (:s, 16, 'VOL-16', 'owned', 216, 'queued')"
        ),
        {"s": series_id},
    )
    await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
    await session.commit()
    return JobContext(session=session, job=job), int(series_id)


async def test_volume_books_are_matched_and_numbered():
    async with get_sessionmaker()() as session:
        ctx, series_id = await _ctx(session)
        komga = FakeKomga()
        books = [_book("B1", "a - Vol.0016 - Volume 16.epub"), _book("B2", "a - Ch.0204.epub")]
        assert await reconcile_volumes(ctx, komga, series_id, books) == 1
        row = (await session.execute(text("select komga_book_id, state from volume"))).one()
        assert (row.komga_book_id, row.state) == ("B1", "downloaded")
        assert komga.patched == [("B1", wanted_volume_metadata(Decimal(16), Decimal(216)))]


async def test_a_volume_already_in_place_is_not_patched_again():
    async with get_sessionmaker()() as session:
        ctx, series_id = await _ctx(session)
        komga = FakeKomga()
        books = [_book("B1", "a - Vol.0016.epub", number="Vol. 16", number_sort=216.5,
                       number_lock=True, number_sort_lock=True)]
        await reconcile_volumes(ctx, komga, series_id, books)
        assert komga.patched == []
