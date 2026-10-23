"""A reading position can stand inside a light novel volume, which has no chapters."""

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
        await session.execute(text("truncate series, list_entry restart identity cascade"))
        await session.commit()


async def _exec(statement: str, params: dict | None = None):
    async with get_sessionmaker()() as session:
        result = await session.execute(text(statement), params or {})
        await session.commit()
        return result


async def _series(slug: str) -> int:
    result = await _exec(
        "insert into series (canonical_title, slug, needs_review, meta, kind)"
        " values (:t, :t, false, '{}'::jsonb, 'prose') returning id",
        {"t": slug},
    )
    return int(result.scalar_one())


async def _volume(series_id: int, number: int = 1) -> int:
    result = await _exec(
        "insert into volume (series_id, number, source_volume_id, status, state, edition)"
        " values (:s, :n, :v, 'owned', 'downloaded', 'light') returning id",
        {"s": series_id, "n": number, "v": f"import:{series_id}:{number}"},
    )
    return int(result.scalar_one())


async def _stored(series_id: int):
    result = await _exec(
        "select chapter_id, volume_id, page, fraction from reading_position where series_id = :s",
        {"s": series_id},
    )
    return result.first()


async def test_a_volume_position_is_stored_without_a_chapter(client):
    series_id = await _series("n")
    volume_id = await _volume(series_id)
    response = await client.put(
        f"/api/reader/series/{series_id}/position",
        json={"volume_id": volume_id, "page": 3, "fraction": 0.25},
    )
    assert response.status_code == 200
    row = await _stored(series_id)
    assert (row.chapter_id, row.volume_id, row.page, row.fraction) == (None, volume_id, 3, 0.25)


async def test_a_chapter_position_replaces_a_volume_one(client):
    series_id = await _series("n")
    volume_id = await _volume(series_id)
    chapter_id = (
        await _exec(
            "insert into chapter (series_id, number, state) values (:s, 1, 'known') returning id",
            {"s": series_id},
        )
    ).scalar_one()
    await client.put(
        f"/api/reader/series/{series_id}/position", json={"volume_id": volume_id, "page": 1}
    )
    await client.put(
        f"/api/reader/series/{series_id}/position", json={"chapter_id": chapter_id, "page": 4}
    )
    row = await _stored(series_id)
    assert (row.chapter_id, row.volume_id, row.page, row.fraction) == (chapter_id, None, 4, None)


async def test_a_volume_of_another_series_is_refused(client):
    series_id = await _series("n")
    other = await _volume(await _series("other"))
    response = await client.put(
        f"/api/reader/series/{series_id}/position", json={"volume_id": other, "page": 0}
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"page": 0},
        {"chapter_id": 1, "volume_id": 1, "page": 0},
        {"volume_id": 1, "page": 0, "fraction": 1.5},
    ],
)
async def test_a_position_names_exactly_one_book(client, body):
    series_id = await _series("n")
    response = await client.put(f"/api/reader/series/{series_id}/position", json=body)
    assert response.status_code == 422


async def test_comic_resume_ignores_a_volume_position(client):
    series_id = await _series("n")
    volume_id = await _volume(series_id)
    await client.put(
        f"/api/reader/series/{series_id}/position", json={"volume_id": volume_id, "page": 2}
    )
    # Its shape is decoded by the Android app and the web resume screen, so a
    # volume position never reaches it; a series with no chapters is a 404.
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).status_code == 404


async def test_a_volume_position_counts_as_reading_in_the_library(client):
    series_id = await _series("n")
    volume_id = await _volume(series_id)
    await client.put(
        f"/api/reader/series/{series_id}/position", json={"volume_id": volume_id, "page": 0}
    )
    [series] = [s for s in (await client.get("/api/series")).json() if s["id"] == series_id]
    assert series["last_read_at"] is not None
