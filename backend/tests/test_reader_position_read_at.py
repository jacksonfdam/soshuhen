"""A reading position replayed late must not overwrite one recorded since."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job, series, list_entry restart identity cascade"))
        await session.commit()


@pytest.fixture
async def series():
    """A series and two of its chapters: (series_id, first, second)."""
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('Teto', 'teto', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        ids = []
        for number in ("1", "2"):
            ids.append(
                (
                    await session.execute(
                        text(
                            "insert into chapter (series_id, number, title, state)"
                            " values (:s, :n, 'C', 'downloaded') returning id"
                        ),
                        {"s": series_id, "n": Decimal(number)},
                    )
                ).scalar_one()
            )
        await session.commit()
    return int(series_id), int(ids[0]), int(ids[1])


async def _put(client, series_id: int, chapter_id: int, page: int, read_at=None) -> dict:
    body: dict = {"chapter_id": chapter_id, "page": page}
    if read_at is not None:
        body["read_at"] = read_at.isoformat()
    response = await client.put(f"/api/reader/series/{series_id}/position", json=body)
    assert response.status_code == 200
    return response.json()


async def _stored(series_id: int):
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text(
                    "select chapter_id, page, updated_at, now() as db_now"
                    " from reading_position where series_id = :s"
                ),
                {"s": series_id},
            )
        ).one()


async def test_without_read_at_it_always_applies(client, series):
    series_id, first, second = series
    assert (await _put(client, series_id, second, 5))["applied"] is True
    assert (await _put(client, series_id, first, 3))["applied"] is True
    row = await _stored(series_id)
    assert (row.chapter_id, row.page) == (first, 3)


async def test_an_older_read_at_does_not_overwrite_a_newer_position(client, series):
    series_id, first, second = series
    await _put(client, series_id, second, 5)
    body = await _put(client, series_id, first, 3, datetime.now(UTC) - timedelta(hours=1))
    assert body == {"ok": True, "applied": False}
    row = await _stored(series_id)
    assert (row.chapter_id, row.page) == (second, 5)


async def test_a_newer_read_at_applies_and_becomes_updated_at(client, series):
    series_id, first, _ = series
    at = datetime.now(UTC) - timedelta(minutes=1)
    assert (await _put(client, series_id, first, 3, at))["applied"] is True
    assert (await _stored(series_id)).updated_at == at


async def test_a_future_read_at_is_clamped_to_now(client, series):
    series_id, first, second = series
    await _put(client, series_id, first, 3, datetime.now(UTC) + timedelta(days=1))
    row = await _stored(series_id)
    assert row.updated_at <= row.db_now
    # A replay from an honest clock, made after it, must still win.
    later = await _put(client, series_id, second, 1, datetime.now(UTC))
    assert later["applied"] is True
