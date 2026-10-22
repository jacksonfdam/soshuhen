"""Covers served from this installation, so a client never leaves the LAN."""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.reader import covers

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
FIRST = "https://cdn.test/c.jpg"
SECOND = "https://cdn.test/d.jpg"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job, series, list_entry restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


@pytest.fixture
def cdn(monkeypatch):
    """Answers in turn from `replies`; each is bytes, a status code or an exception."""
    state = {"calls": 0, "replies": [JPEG]}

    def handler(request: httpx.Request) -> httpx.Response:
        reply = state["replies"][min(state["calls"], len(state["replies"]) - 1)]
        state["calls"] += 1
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply)
        return httpx.Response(200, content=reply)

    monkeypatch.setattr(covers, "TRANSPORT", httpx.MockTransport(handler))
    return state


async def _series(cover_url: str | None) -> int:
    meta = "{}" if cover_url is None else f'{{"cover_url": "{cover_url}"}}'
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('Teto', 'teto', false, cast(:meta as jsonb)) returning id"
                ),
                {"meta": meta},
            )
        ).scalar_one()
        await session.commit()
    return int(series_id)


async def test_first_request_fetches_and_caches(client, cdn, tmp_path):
    series_id = await _series(FIRST)
    response = await client.get(f"/api/series/{series_id}/cover")
    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert len(list((tmp_path / "cache" / "covers").glob("*.jpg"))) == 1


async def test_second_request_does_not_refetch(client, cdn):
    series_id = await _series(FIRST)
    await client.get(f"/api/series/{series_id}/cover")
    await client.get(f"/api/series/{series_id}/cover")
    assert cdn["calls"] == 1


async def test_matching_etag_is_304(client, cdn):
    series_id = await _series(FIRST)
    etag = (await client.get(f"/api/series/{series_id}/cover")).headers["etag"]
    response = await client.get(f"/api/series/{series_id}/cover", headers={"If-None-Match": etag})
    assert response.status_code == 304


async def test_a_failed_fetch_is_404_and_retried_later(client, cdn):
    cdn["replies"] = [404, JPEG]
    series_id = await _series(FIRST)
    assert (await client.get(f"/api/series/{series_id}/cover")).status_code == 404
    assert (await client.get(f"/api/series/{series_id}/cover")).status_code == 200


async def test_a_timeout_is_404(client, cdn):
    cdn["replies"] = [httpx.ReadTimeout("slow")]
    series_id = await _series(FIRST)
    assert (await client.get(f"/api/series/{series_id}/cover")).status_code == 404


async def test_a_non_image_body_is_404(client, cdn):
    cdn["replies"] = [b"<html>not a cover</html>"]
    series_id = await _series(FIRST)
    assert (await client.get(f"/api/series/{series_id}/cover")).status_code == 404


async def test_no_cover_url_is_404(client, cdn):
    series_id = await _series(None)
    assert (await client.get(f"/api/series/{series_id}/cover")).status_code == 404
    assert cdn["calls"] == 0


async def test_an_unknown_series_is_404(client, cdn):
    assert (await client.get("/api/series/999999/cover")).status_code == 404


async def test_a_changed_cover_url_fetches_the_new_one(client, cdn, tmp_path):
    series_id = await _series(FIRST)
    await client.get(f"/api/series/{series_id}/cover")
    async with get_sessionmaker()() as session:
        await session.execute(
            text("update series set meta = jsonb_build_object('cover_url', cast(:u as text)) where id = :s"),
            {"u": SECOND, "s": series_id},
        )
        await session.commit()
    await client.get(f"/api/series/{series_id}/cover")
    assert cdn["calls"] == 2
    assert len(list((tmp_path / "cache" / "covers").iterdir())) == 2


async def test_no_database_connection_is_held_while_the_cdn_answers(client, monkeypatch):
    """A slow CDN must not pin one of the pool's connections for its whole timeout."""
    from app.db import get_engine

    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(get_engine().pool.checkedout())
        return httpx.Response(200, content=JPEG)

    monkeypatch.setattr(covers, "TRANSPORT", httpx.MockTransport(handler))
    series_id = await _series(FIRST)
    assert (await client.get(f"/api/series/{series_id}/cover")).status_code == 200
    assert seen == [0]
