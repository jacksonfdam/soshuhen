"""A volume in both its web novel and its light novel edition.

The user owns both, and they are different books: the light novel rewrites and
merges the web chapters. One number may therefore hold two rows, one per
edition, and only the light novel row owns a Vol. file.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext
from app.handlers.komga_scan import reconcile_volumes
from app.queue import repo
from tests.test_komga_volumes import FakeKomga, _book


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


async def a_series(session) -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('A', 'a', false, '{}'::jsonb, 'prose') returning id"
            )
        )
    ).scalar_one()


async def a_volume(session, series_id: int, edition: str, source: str) -> None:
    await session.execute(
        text(
            "insert into volume (series_id, number, edition, source_volume_id, status)"
            " values (:s, 1, :e, :src, 'owned')"
        ),
        {"s": series_id, "e": edition, "src": source},
    )


async def test_two_editions_of_one_number_coexist():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await a_volume(session, series_id, "web", "import:a")
        await a_volume(session, series_id, "light", "import:b")
        await session.commit()

        count = (await session.execute(text("select count(*) from volume"))).scalar_one()
        assert count == 2


async def test_one_edition_twice_is_rejected():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await a_volume(session, series_id, "light", "import:a")
        with pytest.raises(IntegrityError):
            await a_volume(session, series_id, "light", "import:b")


async def test_an_unknown_edition_is_rejected():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        with pytest.raises(IntegrityError):
            await a_volume(session, series_id, "audio", "import:a")


async def test_a_jnovelclub_volume_is_light_by_default():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await session.execute(
            text(
                "insert into volume (series_id, number, source_volume_id, status)"
                " values (:s, 1, 'VOL-1', 'owned')"
            ),
            {"s": series_id},
        )
        edition = (await session.execute(text("select edition from volume"))).scalar_one()
        assert edition == "light"


async def test_reconcile_volumes_ignores_web_rows():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await a_volume(session, series_id, "web", "import:a")
        await a_volume(session, series_id, "light", "import:b")
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
        await session.commit()
        ctx = JobContext(session=session, job=job)

        matched = await reconcile_volumes(ctx, FakeKomga(), series_id, [_book("B1", "a - Vol.0001.epub")])

        rows = dict((await session.execute(text("select edition, komga_book_id from volume"))).all())
        assert matched == 1
        assert rows == {"light": "B1", "web": None}
