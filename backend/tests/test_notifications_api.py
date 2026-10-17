"""The bell's routes: what is new, how much of it is unread, and marking it read."""

import asyncio
import json

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.queue.repo import NOTIFY_CHANNEL

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate notification, series restart identity cascade"))
        await session.commit()


async def _series(title: str = "Frieren", cover: str | None = "https://img/frieren.jpg") -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values (:t, :slug, false,"
                    "         jsonb_strip_nulls(jsonb_build_object('cover_url', cast(:c as text))))"
                    " returning id"
                ),
                {"t": title, "slug": title.lower(), "c": cover},
            )
        ).scalar_one()
        await session.commit()
    return int(series_id)


async def _notification(
    series_id: int,
    *,
    first: str = "128",
    last: str = "130",
    count: int = 3,
    age_minutes: int = 0,
    read: bool = False,
) -> int:
    async with get_sessionmaker()() as session:
        nid = (
            await session.execute(
                text(
                    "insert into notification"
                    " (series_id, kind, count, first_number, last_number, created_at, read_at)"
                    " values (:s, 'chapters', :count, cast(:first as numeric),"
                    "         cast(:last as numeric), now() - make_interval(mins => :age),"
                    "         case when :read then now() - interval '1 day' end)"
                    " returning id"
                ),
                {
                    "s": series_id,
                    "count": count,
                    "first": first,
                    "last": last,
                    "age": age_minutes,
                    "read": read,
                },
            )
        ).scalar_one()
        await session.commit()
    return int(nid)


async def test_lists_newest_first_with_series_title_and_cover(client):
    frieren = await _series()
    dandadan = await _series("Dandadan", None)
    older = await _notification(frieren, age_minutes=60)
    newer = await _notification(dandadan, age_minutes=1)

    body = (await client.get("/api/notifications")).json()

    assert [item["id"] for item in body["items"]] == [newer, older]
    first = body["items"][0]
    assert first["series_id"] == dandadan
    assert first["series_title"] == "Dandadan"
    assert first["cover_url"] is None
    assert body["items"][1]["cover_url"] == "https://img/frieren.jpg"
    assert first["kind"] == "chapters"
    assert first["count"] == 3
    assert first["volume_number"] is None
    assert first["read_at"] is None
    assert isinstance(first["created_at"], str)
    assert body["unread_count"] == 2


async def test_fractional_numbers_are_plain_numbers(client):
    series_id = await _series()
    await _notification(series_id, first="128.5", last="128.5", count=1)

    item = (await client.get("/api/notifications")).json()["items"][0]

    assert item["first_number"] == 128.5
    assert item["last_number"] == 128.5


async def test_unread_count_is_not_capped_by_the_page(client):
    series_id = await _series()
    for minutes in range(45):
        await _notification(series_id, age_minutes=minutes)

    body = (await client.get("/api/notifications?limit=30")).json()

    assert len(body["items"]) == 30
    assert body["unread_count"] == 45


async def test_limit_is_capped_at_100(client):
    assert (await client.get("/api/notifications?limit=500")).status_code == 422


async def test_marking_one_read_keeps_its_first_time(client):
    series_id = await _series()
    nid = await _notification(series_id)

    assert (await client.post(f"/api/notifications/{nid}/read")).json() == {"ok": True}
    first = (await client.get("/api/notifications")).json()["items"][0]["read_at"]
    assert first is not None
    assert (await client.post(f"/api/notifications/{nid}/read")).json() == {"ok": True}

    body = (await client.get("/api/notifications")).json()
    assert body["items"][0]["read_at"] == first
    assert body["unread_count"] == 0


async def test_unknown_id_is_404(client):
    assert (await client.post("/api/notifications/999/read")).status_code == 404


async def test_read_all_marks_every_unread_row(client):
    series_id = await _series()
    await _notification(series_id)
    await _notification(series_id)
    await _notification(series_id, read=True)

    assert (await client.post("/api/notifications/read-all")).json() == {"marked": 2}
    assert (await client.get("/api/notifications")).json()["unread_count"] == 0


@pytest.fixture
async def heard():
    received: asyncio.Queue[str] = asyncio.Queue()
    connection = await asyncpg.connect(get_settings().dsn)
    await connection.add_listener(
        NOTIFY_CHANNEL, lambda _c, _p, _ch, payload: received.put_nowait(payload)
    )
    yield received
    await connection.close()


async def test_marking_read_tells_every_open_tab(client, heard):
    series_id = await _series()
    nid = await _notification(series_id)

    await client.post(f"/api/notifications/{nid}/read")
    one = json.loads(await asyncio.wait_for(heard.get(), 2))
    await client.post("/api/notifications/read-all")
    every = json.loads(await asyncio.wait_for(heard.get(), 2))

    assert one["event"] == "notification.read"
    assert one["notification_id"] == nid
    assert every["event"] == "notification.read"
    assert every["notification_id"] is None
