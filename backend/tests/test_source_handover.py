"""A change of source: what the new one lists is fetched from it, what it lacks is set aside."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import chapter_discover
from app.handlers.base import JobContext
from app.queue import repo
from app.sources.base import ChapterRef

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job, notification restart identity cascade"))
        await session.commit()


class FakeSource:
    def __init__(self):
        self.numbers: list[str] = []

    async def list_chapters(self, url):
        return [ChapterRef(Decimal(n), f"{url}/{n}") for n in self.numbers]


@pytest.fixture
def source(monkeypatch):
    fake = FakeSource()
    monkeypatch.setattr(chapter_discover, "source_for_url", lambda url: fake)

    async def none(*_args):
        return 0

    monkeypatch.setattr(chapter_discover, "reconcile_with_komga", none)
    monkeypatch.setattr(chapter_discover, "reconcile_with_disk", none)
    monkeypatch.setattr(chapter_discover, "queue_missing", none)
    return fake


async def _series(session) -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values ('Frieren', 'frieren', false, '{}'::jsonb) returning id"
            )
        )
    ).scalar_one()


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


async def _states(session, series_id: int) -> dict[str, tuple[str, str]]:
    rows = await session.execute(
        text("select number, state, source_url from chapter where series_id = :s order by number"),
        {"s": series_id},
    )
    return {str(row.number.normalize()): (row.state, row.source_url) for row in rows}


async def _set_state(session, series_id: int, number: str, state: str) -> None:
    await session.execute(
        text("update chapter set state = :state where series_id = :s and number = :n"),
        {"state": state, "s": series_id, "n": Decimal(number)},
    )
    await session.commit()


async def test_a_new_source_retries_failures_and_retires_what_it_lacks(source):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _map(session, series_id, "https://old.test/a")
        source.numbers = ["1", "2", "3", "4"]
        await _discover(session, series_id)
        await _set_state(session, series_id, "1", "downloaded")
        await _set_state(session, series_id, "2", "failed")

        await _map(session, series_id, "https://new.test/b")
        source.numbers = ["2", "3", "5"]
        await _discover(session, series_id)

        states = await _states(session, series_id)

    # Already in the library: untouched, even though the new source lacks it.
    assert states["1"][0] == "downloaded"
    # Failed on the old source, listed by the new one: worth another try there.
    assert states["2"] == ("known", "https://new.test/b/2")
    assert states["3"] == ("known", "https://new.test/b/3")
    # Only the old source had it: set aside rather than fetched from the old site.
    assert states["4"] == ("skipped", "https://old.test/a/4")
    assert states["5"] == ("known", "https://new.test/b/5")


async def test_a_later_discovery_that_misses_a_chapter_retires_nothing(source):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _map(session, series_id, "https://old.test/a")
        source.numbers = ["1", "2"]
        await _discover(session, series_id)
        source.numbers = ["1"]
        await _discover(session, series_id)

        assert (await _states(session, series_id))["2"][0] == "known"


async def test_the_first_ever_discovery_is_not_a_change_of_source(source):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await session.execute(
            text(
                "insert into chapter (series_id, number, state) values (:s, 9, 'failed')"
            ),
            {"s": series_id},
        )
        await _map(session, series_id, "https://old.test/a")
        source.numbers = ["1"]
        await _discover(session, series_id)

        assert (await _states(session, series_id))["9"][0] == "failed"
