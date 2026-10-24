"""A series with no source but with files in the library is `local`, not waiting.

It still belongs to its work on the trackers; it only has nothing to download
from, and no screen should ask it for a mapping.
"""

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
        await session.execute(
            text("truncate series, list_entry, source_mapping restart identity cascade")
        )
        await session.commit()


async def _exec(statement: str, params: dict | None = None):
    async with get_sessionmaker()() as session:
        result = await session.execute(text(statement), params or {})
        await session.commit()
        return result


async def _series(slug: str, kind: str = "prose") -> int:
    result = await _exec(
        "insert into series (canonical_title, slug, needs_review, meta, kind)"
        " values (:t, :t, false, '{}'::jsonb, :k) returning id",
        {"t": slug, "k": kind},
    )
    return int(result.scalar_one())


async def _volume(series_id: int, state: str = "downloaded") -> None:
    await _exec(
        "insert into volume (series_id, number, source_volume_id, status, state, edition)"
        " values (:s, 1, :v, 'owned', :st, 'light')",
        {"s": series_id, "v": f"import:{series_id}", "st": state},
    )


async def _chapter(series_id: int, state: str) -> None:
    await _exec(
        "insert into chapter (series_id, number, state) values (:s, 1, :st)",
        {"s": series_id, "st": state},
    )


async def _state(client, series_id: int) -> str:
    return (await client.get(f"/api/series/{series_id}")).json()["series"]["state"]


async def test_unmapped_series_with_a_downloaded_volume_is_local(client):
    series_id = await _series("vol")
    await _volume(series_id)
    assert await _state(client, series_id) == "local"
    listed = {s["id"]: s["state"] for s in (await client.get("/api/series")).json()}
    assert listed[series_id] == "local"


async def test_unmapped_series_with_a_downloaded_chapter_is_local(client):
    series_id = await _series("comic", kind="comic")
    await _chapter(series_id, "downloaded")
    assert await _state(client, series_id) == "local"


async def test_unmapped_series_with_nothing_downloaded_needs_review(client):
    series_id = await _series("empty")
    await _volume(series_id, state="known")
    await _chapter(series_id, "known")
    assert await _state(client, series_id) == "needs_review"


async def test_a_failed_chapter_still_reads_failed(client):
    series_id = await _series("broken", kind="comic")
    await _volume(series_id)
    await _chapter(series_id, "failed")
    assert await _state(client, series_id) == "failed"


async def test_local_series_leave_the_review_queue(client):
    local = await _series("local")
    await _volume(local)
    waiting = await _series("waiting")
    ids = [item["id"] for item in (await client.get("/api/series/review/queue")).json()["items"]]
    assert ids == [waiting]


async def test_local_series_leave_the_dashboard_pending_count(client):
    local = await _series("local")
    await _chapter(local, "downloaded")
    await _series("waiting")
    body = (await client.get("/api/dashboard")).json()
    assert body["mappings"]["pending"] == 1
