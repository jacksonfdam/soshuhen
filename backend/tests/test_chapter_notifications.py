"""A discovery announces the chapters it inserted, never a series' whole backlog."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import chapter_discover
from app.handlers.base import JobContext
from app.handlers.chapter_discover import announce_new_chapters, upsert_chapters
from app.queue import repo
from app.sources.base import ChapterRef

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job, notification restart identity cascade"))
        await session.commit()


async def _series(session) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values ('Frieren', 'frieren', false, '{}'::jsonb) returning id"
            )
        )
    ).scalar_one()
    return int(series_id)


def _ref(number: int | str) -> ChapterRef:
    return ChapterRef(Decimal(number), f"https://x/{number}")


async def _rows(session):
    return (
        await session.execute(
            text("select kind, count, first_number, last_number from notification")
        )
    ).all()


async def test_upsert_returns_only_inserted_numbers():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        first = await upsert_chapters(session, series_id, [_ref(1), _ref(2)])
        again = await upsert_chapters(session, series_id, [_ref(1), _ref(2), _ref(3)])
    assert first == [Decimal("1.00"), Decimal("2.00")]
    assert again == [Decimal("3.00")]


async def test_first_discovery_records_nothing():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        result = await announce_new_chapters(
            session, series_id, first_discovery=True, inserted=[Decimal(1), Decimal(2)]
        )
        assert result is None
        assert await _rows(session) == []


async def test_later_discovery_records_one_row_per_run():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await announce_new_chapters(
            session,
            series_id,
            first_discovery=False,
            inserted=[Decimal(128), Decimal(129), Decimal(130)],
        )
        assert await _rows(session) == [("chapters", 3, Decimal("128.00"), Decimal("130.00"))]


async def test_fractional_numbers_survive():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await announce_new_chapters(
            session, series_id, first_discovery=False, inserted=[Decimal("128.5")]
        )
        assert await _rows(session) == [("chapters", 1, Decimal("128.50"), Decimal("128.50"))]


class FakeSource:
    def __init__(self):
        self.numbers: list[int] = []

    async def list_chapters(self, url):
        return [ChapterRef(Decimal(n), f"{url}/{n}") for n in self.numbers]


@pytest.fixture
def source(monkeypatch):
    fake = FakeSource()
    monkeypatch.setattr(chapter_discover, "source_for_url", lambda url: fake)

    async def none(*_args):
        return 0

    # Komga, the library on disk and the download queue are not what these
    # tests are about, and each would otherwise need its own world set up.
    monkeypatch.setattr(chapter_discover, "reconcile_with_komga", none)
    monkeypatch.setattr(chapter_discover, "reconcile_with_disk", none)
    monkeypatch.setattr(chapter_discover, "queue_missing", none)
    return fake


async def _map(session, series_id: int, url: str) -> None:
    await session.execute(
        text("update source_mapping set active = false where series_id = :s"), {"s": series_id}
    )
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active)"
            " values (:s, 'mangadex', :u, true)"
        ),
        {"s": series_id, "u": url},
    )
    await session.commit()


async def _discover(session, series_id: int) -> None:
    await repo.enqueue(session, JobType.CHAPTER_DISCOVER, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.CHAPTER_DISCOVER)])
    await session.commit()
    await chapter_discover.handle(JobContext(session=session, job=job))
    await session.commit()


async def test_a_new_series_announces_from_its_second_discovery(source):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _map(session, series_id, "https://mangadex.org/title/a")
        source.numbers = [1, 2, 3]
        await _discover(session, series_id)
        assert await _rows(session) == []
        source.numbers = [1, 2, 3, 4]
        await _discover(session, series_id)
        assert await _rows(session) == [("chapters", 1, Decimal("4.00"), Decimal("4.00"))]


async def test_a_new_source_does_not_announce_what_the_old_one_lacked(source):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _map(session, series_id, "https://mangadex.org/title/a")
        source.numbers = [1, 2, 3]
        await _discover(session, series_id)
        await _discover(session, series_id)

        await _map(session, series_id, "https://mangadex.org/title/b")
        source.numbers = [1, 2, 3, 3.5, 4]
        await _discover(session, series_id)
        assert await _rows(session) == []

        source.numbers = [1, 2, 3, 3.5, 4, 5]
        await _discover(session, series_id)
        assert await _rows(session) == [("chapters", 1, Decimal("5.00"), Decimal("5.00"))]


async def test_a_first_run_that_inserts_nothing_still_counts_as_discovered(source):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _map(session, series_id, "https://mangadex.org/title/a")
        source.numbers = [1, 2]
        await _discover(session, series_id)
        await _map(session, series_id, "https://mangadex.org/title/b")
        await _discover(session, series_id)  # the same two chapters: nothing new
        source.numbers = [1, 2, 3]
        await _discover(session, series_id)
        assert await _rows(session) == [("chapters", 1, Decimal("3.00"), Decimal("3.00"))]
