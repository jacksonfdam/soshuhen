"""One discovery run of one series becomes one notification, announced on commit."""

import asyncio
import json
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import NotificationKind
from app.notifications import EVENT, record
from app.queue.repo import NOTIFY_CHANNEL

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, notification restart identity cascade"))
        await session.commit()


@pytest.fixture
async def heard():
    """Every payload sent on the channel the browser's stream is fed from."""
    received: asyncio.Queue[str] = asyncio.Queue()
    connection = await asyncpg.connect(get_settings().dsn)
    await connection.add_listener(
        NOTIFY_CHANNEL, lambda _c, _p, _ch, payload: received.put_nowait(payload)
    )
    yield received
    await connection.close()


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


async def _rows(session):
    return (
        await session.execute(
            text(
                "select kind, count, first_number, last_number, volume_number, read_at"
                " from notification order by id"
            )
        )
    ).all()


async def test_nothing_new_records_nothing():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        assert await record(session, series_id, NotificationKind.CHAPTERS, []) is None
        assert await _rows(session) == []


async def test_a_run_is_one_row_with_its_range():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        nid = await record(
            session,
            series_id,
            NotificationKind.CHAPTERS,
            [Decimal(130), Decimal(128), Decimal(129)],
        )
        assert isinstance(nid, int)
        assert await _rows(session) == [
            ("chapters", 3, Decimal("128.00"), Decimal("130.00"), None, None)
        ]


async def test_parts_carry_their_volume():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await record(
            session,
            series_id,
            NotificationKind.PARTS,
            [Decimal(5), Decimal(6)],
            volume_number=Decimal(3),
        )
        rows = await _rows(session)
        assert rows[0].kind == "parts"
        assert rows[0].volume_number == Decimal("3.00")


async def test_the_event_leaves_only_on_commit(heard):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        nid = await record(session, series_id, NotificationKind.CHAPTERS, [Decimal(1)])
        await asyncio.sleep(0.2)
        assert heard.empty()
        await session.commit()
    payload = json.loads(await asyncio.wait_for(heard.get(), 2))
    assert payload["event"] == EVENT == "notification.new"
    assert payload["notification_id"] == nid
    assert payload["series_id"] == series_id
    assert payload["kind"] == "chapters"


async def test_old_read_rows_are_pruned_and_unread_kept():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        seed = text(
            "insert into notification"
            " (series_id, kind, count, first_number, last_number, created_at, read_at)"
            " values (:s, 'chapters', 1, :n, :n, now() - make_interval(days => :created),"
            "         now() - make_interval(days => :read))"
        )
        await session.execute(seed, {"s": series_id, "n": 1, "created": 40, "read": 31})
        await session.execute(seed, {"s": series_id, "n": 2, "created": 3, "read": 2})
        await session.execute(
            text(
                "insert into notification"
                " (series_id, kind, count, first_number, last_number, created_at)"
                " values (:s, 'chapters', 1, 3, 3, now() - interval '400 days')"
            ),
            {"s": series_id},
        )
        await record(session, series_id, NotificationKind.CHAPTERS, [Decimal(4)])
        numbers = [r.first_number for r in await _rows(session)]
    assert numbers == [Decimal("2.00"), Decimal("3.00"), Decimal("4.00")]
