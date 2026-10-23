"""GET /api/updates: chapters found after a series was followed, never its backlog."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate chapter, source_mapping, series restart identity cascade")
        )
        await session.commit()
    yield


async def _series(session, slug: str) -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:slug, :slug, false, '{}'::jsonb) returning id"
            ),
            {"slug": slug},
        )
    ).scalar_one()


async def _mapping(session, series_id: int, days_ago: int, *, active=True) -> None:
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active, discovered_at)"
            " values (:id, 'site', :url, :active, now() - make_interval(days => :ago))"
        ),
        {"id": series_id, "url": f"https://site.test/{series_id}/{days_ago}", "active": active,
         "ago": days_ago},
    )


async def _chapter(session, series_id: int, number: float, days_ago: int) -> None:
    await session.execute(
        text(
            "insert into chapter (series_id, number, state, discovered_at)"
            " values (:id, :n, 'known', now() - make_interval(days => :ago))"
        ),
        {"id": series_id, "n": number, "ago": days_ago},
    )


async def test_the_first_discovery_is_backlog_and_later_chapters_are_new(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "followed")
        await _mapping(session, series_id, 10)
        await _chapter(session, series_id, 1, 10)
        await _chapter(session, series_id, 2, 10)
        await _chapter(session, series_id, 3, 2)
        await session.commit()

    body = (await client.get("/api/updates")).json()

    assert [c["number"] for c in body["chapters"]] == [3]
    assert body["chapters"][0]["series_title"] == "followed"
    assert body["truncated"] is False


async def test_a_change_of_source_does_not_announce_the_new_source_backlog(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "moved")
        await _mapping(session, series_id, 20, active=False)
        await _chapter(session, series_id, 1, 20)
        await _chapter(session, series_id, 2, 15)
        await _mapping(session, series_id, 5)
        await _chapter(session, series_id, 3, 5)
        await _chapter(session, series_id, 4, 5)
        await _chapter(session, series_id, 5, 1)
        await session.commit()

    body = (await client.get("/api/updates")).json()

    assert [c["number"] for c in body["chapters"]] == [5, 2]


async def test_a_series_never_discovered_announces_nothing(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "unmapped")
        await _chapter(session, series_id, 1, 1)
        await session.commit()

    assert (await client.get("/api/updates")).json()["chapters"] == []


async def test_the_window_is_bounded_by_days(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "old")
        await _mapping(session, series_id, 60)
        await _chapter(session, series_id, 1, 60)
        await _chapter(session, series_id, 2, 40)
        await _chapter(session, series_id, 3, 3)
        await session.commit()

    assert [c["number"] for c in (await client.get("/api/updates?days=30")).json()["chapters"]] == [3]
    assert [c["number"] for c in (await client.get("/api/updates?days=90")).json()["chapters"]] == [3, 2]
