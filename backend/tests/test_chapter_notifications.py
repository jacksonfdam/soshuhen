"""A discovery announces the chapters it inserted, never a series' whole backlog."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.chapter_discover import announce_new_chapters, upsert_chapters
from app.sources.base import ChapterRef

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, notification restart identity cascade"))
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
            session, series_id, had_chapters=False, inserted=[Decimal(1), Decimal(2)]
        )
        assert result is None
        assert await _rows(session) == []


async def test_later_discovery_records_one_row_per_run():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await announce_new_chapters(
            session,
            series_id,
            had_chapters=True,
            inserted=[Decimal(128), Decimal(129), Decimal(130)],
        )
        assert await _rows(session) == [("chapters", 3, Decimal("128.00"), Decimal("130.00"))]


async def test_fractional_numbers_survive():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await announce_new_chapters(
            session, series_id, had_chapters=True, inserted=[Decimal("128.5")]
        )
        assert await _rows(session) == [("chapters", 1, Decimal("128.50"), Decimal("128.50"))]
