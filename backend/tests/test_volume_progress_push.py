"""Komga reading moves each list's volumes forward, beside its chapters."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import progress_push
from app.handlers.base import JobContext
from app.handlers.komga_scan import mark_read_up_to_lists
from app.komga.client import KomgaBook
from app.providers.base import WriteRefused
from app.queue import repo


class FakeKomgaClient:
    has_credentials = True

    def __init__(self, books):
        self.books = books

    async def books_of_series(self, series_id):
        return self.books


class RecordingProvider:
    def __init__(self, refuse_volume=False):
        self.calls: list[tuple] = []
        self.refuse_volume = refuse_volume

    async def push_progress(self, token, media_id, chapter, volume=None):
        if volume is not None and self.refuse_volume:
            raise WriteRefused("no")
        self.calls.append((media_id, chapter, volume))


def _book(book_id, completed=True):
    return KomgaBook(id=book_id, series_id="K", name=book_id, path=f"/m/{book_id}",
                     completed=completed, page=0)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


async def _series(session, *, kind="prose", progress_chapter=0, progress_volume=None,
                  total_volumes=None) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind,"
                " komga_series_id) values ('A', 'a', false, '{}'::jsonb, :k, 'K') returning id"
            ),
            {"k": kind},
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, synonyms, status,
                                    user_progress_chapter, user_progress_volume, total_volumes,
                                    raw)
            values ('local', 'L1', :s, '[]'::jsonb, 'reading', :c,
                    cast(:v as integer), cast(:t as integer), '{}'::jsonb)
            """
        ),
        {"s": series_id, "c": progress_chapter, "v": progress_volume, "t": total_volumes},
    )
    await session.execute(
        text(
            "insert into volume (series_id, number, source_volume_id, status, first_part,"
            " last_part, state, komga_book_id)"
            " values (:s, 16, 'VOL-16', 'owned', 204, 216, 'downloaded', 'V16')"
        ),
        {"s": series_id},
    )
    await session.commit()
    return int(series_id)


async def _run(session, monkeypatch, series_id, books, provider):
    monkeypatch.setattr(progress_push, "from_settings", lambda: FakeKomgaClient(books))
    monkeypatch.setattr(progress_push, "get_source", lambda p: provider)

    async def token(session, p):
        return "t"

    monkeypatch.setattr(progress_push, "access_token_for", token)
    await repo.enqueue(session, JobType.PROGRESS_PUSH, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.PROGRESS_PUSH)])
    await session.commit()
    await progress_push.handle(JobContext(session=session, job=job))
    await session.commit()


async def _entry(session):
    return (
        await session.execute(
            text("select user_progress_chapter, user_progress_volume from list_entry")
        )
    ).one()


async def test_a_finished_volume_alone_pushes(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, 16)]
        assert tuple(await _entry(session)) == (216, 16)


async def test_a_list_already_past_the_volume_gets_no_volume(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_volume=20)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, None)]


async def test_a_volume_only_move_sends_the_current_chapter(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_chapter=300, progress_volume=3)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 300, 16)]


async def test_the_volume_is_capped_at_the_lists_total(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session, total_volumes=12)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, 12)]


async def test_a_refused_volume_is_retried_without_it(monkeypatch):
    provider = RecordingProvider(refuse_volume=True)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, None)]
        assert tuple(await _entry(session)) == (216, None)


async def test_nothing_read_sends_nothing(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _run(session, monkeypatch, series_id, [_book("V16", completed=False)], provider)
        assert provider.calls == []


class MarkingClient:
    def __init__(self):
        self.marked: list[str] = []

    async def set_read_progress(self, book_id, *, page, completed):
        self.marked.append(book_id)


async def test_volume_books_the_lists_count_as_read_are_marked():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_volume=16)
        await session.execute(
            text(
                "insert into volume (series_id, number, source_volume_id, status, state,"
                " komga_book_id) values (:s, 17, 'VOL-17', 'owned', 'downloaded', 'V17')"
            ),
            {"s": series_id},
        )
        await session.commit()
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
        await session.commit()
        client = MarkingClient()
        books = [_book("V16", completed=False), _book("V17", completed=False)]
        await mark_read_up_to_lists(JobContext(session=session, job=job), client, series_id, books)
        assert client.marked == ["V16"]
