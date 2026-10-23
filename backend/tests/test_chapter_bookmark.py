"""A chapter bookmark: set, cleared, shown on the series, and kept to its series."""

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
        await session.execute(text("truncate chapter, series restart identity cascade"))
        await session.commit()
    yield


async def _series_with_chapter(slug: str) -> tuple[int, int]:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values (:slug, :slug, false, '{}'::jsonb) returning id"
                ),
                {"slug": slug},
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state)"
                    " values (:id, 1, 'known') returning id"
                ),
                {"id": series_id},
            )
        ).scalar_one()
        await session.commit()
    return series_id, chapter_id


async def test_a_bookmark_is_set_shown_and_cleared(client):
    series_id, chapter_id = await _series_with_chapter("one")
    url = f"/api/series/{series_id}/chapters/{chapter_id}/bookmark"

    assert (await client.put(url, json={"bookmarked": True})).status_code == 200
    detail = (await client.get(f"/api/series/{series_id}")).json()
    assert detail["chapters"][0]["bookmarked"] is True

    assert (await client.put(url, json={"bookmarked": False})).status_code == 200
    detail = (await client.get(f"/api/series/{series_id}")).json()
    assert detail["chapters"][0]["bookmarked"] is False


async def test_a_chapter_of_another_series_is_refused(client):
    series_id, _ = await _series_with_chapter("one")
    _, other_chapter = await _series_with_chapter("two")

    response = await client.put(
        f"/api/series/{series_id}/chapters/{other_chapter}/bookmark", json={"bookmarked": True}
    )

    assert response.status_code == 404
