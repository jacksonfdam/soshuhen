"""Komga forgets the books of offloaded chapters, and nothing else."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext
from app.handlers.komga_scan import release_offloaded
from app.komga.client import KomgaBook
from app.queue import repo


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


class FakeKomga:
    def __init__(self):
        self.emptied: list[str] = []

    async def empty_trash(self, library_id):
        self.emptied.append(library_id)


def _book(book_id, deleted):
    return KomgaBook(id=book_id, series_id="K1", name=book_id, path=f"/manga/a/{book_id}.cbz",
                     completed=False, page=0, deleted=deleted)


async def _setup(session, rows):
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('A', 'a', false, '{}'::jsonb, 'comic') returning id"
            )
        )
    ).scalar_one()
    for number, state, book_id in rows:
        await session.execute(
            text(
                "insert into chapter (series_id, number, state, komga_book_id)"
                " values (:s, :n, :st, :b)"
            ),
            {"s": series_id, "n": number, "st": state, "b": book_id},
        )
    await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
    await session.commit()
    return JobContext(session=session, job=job), series_id


async def _book_ids(session):
    return dict(
        (await session.execute(text("select number::int, komga_book_id from chapter"))).all()
    )


async def test_offloaded_books_are_emptied_and_forgotten():
    komga = FakeKomga()
    async with get_sessionmaker()() as session:
        ctx, series_id = await _setup(session, [(1, "offloaded", "b1"), (2, "downloaded", "b2")])
        released = await release_offloaded(
            ctx, komga, "lib-1", series_id, [_book("b1", True), _book("b2", False)]
        )
        await session.commit()
        ids = await _book_ids(session)
    assert released == 1
    assert komga.emptied == ["lib-1"]
    assert ids == {1: None, 2: "b2"}


async def test_a_deleted_book_we_did_not_offload_stops_the_cleanup():
    # A library whose mount went away shows every book deleted; emptying the
    # trash then would wipe Komga's whole record of it.
    komga = FakeKomga()
    async with get_sessionmaker()() as session:
        ctx, series_id = await _setup(session, [(1, "offloaded", "b1"), (2, "downloaded", "b2")])
        released = await release_offloaded(
            ctx, komga, "lib-1", series_id, [_book("b1", True), _book("b2", True)]
        )
        await session.commit()
        ids = await _book_ids(session)
    assert released == 0
    assert komga.emptied == []
    assert ids == {1: "b1", 2: "b2"}


async def test_nothing_deleted_yet_waits_for_a_later_scan():
    komga = FakeKomga()
    async with get_sessionmaker()() as session:
        ctx, series_id = await _setup(session, [(1, "offloaded", "b1")])
        released = await release_offloaded(ctx, komga, "lib-1", series_id, [_book("b1", False)])
        await session.commit()
        ids = await _book_ids(session)
    assert released == 0
    assert komga.emptied == []
    assert ids == {1: "b1"}
