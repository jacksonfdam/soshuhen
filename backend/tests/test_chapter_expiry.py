"""Parts that expire are recorded, and the ones about to are called out."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.chapter_discover import expiring_soon, upsert_chapters
from app.sources.base import ChapterRef

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        await session.commit()


async def _series(session) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('N', 'n', false, '{}'::jsonb, 'prose') returning id"
            )
        )
    ).scalar_one()
    return int(series_id)


async def test_discovery_stores_and_updates_when_a_chapter_expires():
    first = datetime(2026, 11, 16, 10, tzinfo=UTC)
    moved = datetime(2026, 12, 15, 10, tzinfo=UTC)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(
            session, series_id, [ChapterRef(Decimal(1), "https://x/1", available_until=first)]
        )
        await upsert_chapters(
            session, series_id, [ChapterRef(Decimal(1), "https://x/1", available_until=moved)]
        )
        await upsert_chapters(session, series_id, [ChapterRef(Decimal(2), "https://x/2")])
        rows = dict(
            (
                await session.execute(
                    text("select number, available_until from chapter order by number")
                )
            ).all()
        )
    assert rows[Decimal("1.00")] == moved
    assert rows[Decimal("2.00")] is None


async def test_only_undownloaded_parts_within_a_week_are_called_out():
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(
            session,
            series_id,
            [
                ChapterRef(Decimal(1), "https://x/1", available_until=now + timedelta(days=3)),
                ChapterRef(Decimal(2), "https://x/2", available_until=now + timedelta(days=5)),
                ChapterRef(Decimal(3), "https://x/3", available_until=now + timedelta(days=30)),
                ChapterRef(Decimal(4), "https://x/4", available_until=now - timedelta(days=1)),
                ChapterRef(Decimal(5), "https://x/5", available_until=now + timedelta(days=2)),
            ],
        )
        await session.execute(
            text("update chapter set state = 'downloaded' where number = 5")
        )
        count, earliest = await expiring_soon(session, series_id)
    assert count == 2
    assert abs(earliest - (now + timedelta(days=3))) < timedelta(seconds=1)


async def test_nothing_expiring_is_nothing_to_report():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(session, series_id, [ChapterRef(Decimal(1), "https://x/1")])
        assert await expiring_soon(session, series_id) == (0, None)
