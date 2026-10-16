"""The API keeps a series and its source on the same side of comic/prose."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.sources import base

pytestmark = pytest.mark.asyncio


class ProseFake(base.ProseSource):
    site = "prose-fake"
    domains = ("prose.test",)

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotImplementedError


class ComicFake(base.Source):
    site = "comic-fake"
    domains = ("comic.test",)

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def list_pages(self, chapter_url, *, language="en"):
        return []


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    base.install_registry(
        {
            "prose-fake": base.RegisteredSource(ProseFake(), "https://prose.test"),
            "comic-fake": base.RegisteredSource(ComicFake(), "https://comic.test"),
        }
    )
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _series(kind: str | None) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('t', 't', true, '{}'::jsonb, cast(:kind as text)) returning id"
                ),
                {"kind": kind},
            )
        ).scalar_one()
        await session.commit()
        return int(series_id)


async def test_a_prose_series_refuses_a_comic_source(client):
    series_id = await _series("prose")
    response = await client.post(
        f"/api/series/{series_id}/mapping", json={"source_url": "https://comic.test/m/1"}
    )
    assert response.status_code == 422
    assert "prose" in response.json()["detail"]


async def test_an_unknown_kind_series_refuses_a_prose_source(client):
    series_id = await _series(None)
    response = await client.post(
        f"/api/series/{series_id}/mapping", json={"source_url": "https://prose.test/n/1"}
    )
    assert response.status_code == 422


async def test_a_prose_series_accepts_a_prose_source(client):
    series_id = await _series("prose")
    response = await client.post(
        f"/api/series/{series_id}/mapping", json={"source_url": "https://prose.test/n/1"}
    )
    assert response.status_code == 200


async def test_series_payloads_carry_the_kind(client):
    series_id = await _series("prose")
    rows = (await client.get("/api/series")).json()
    assert next(row for row in rows if row["id"] == series_id)["kind"] == "prose"
    detail = (await client.get(f"/api/series/{series_id}")).json()
    assert detail["series"]["kind"] == "prose"


async def test_setting_the_kind_by_hand_locks_it(client):
    series_id = await _series(None)
    response = await client.post(f"/api/series/{series_id}/kind", json={"kind": "prose"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "kind": "prose"}
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text("select kind, meta from series where id = :id"), {"id": series_id}
            )
        ).one()
    assert row.kind == "prose"
    assert row.meta["kind_locked"] is True


async def test_an_unknown_kind_value_is_rejected(client):
    series_id = await _series(None)
    response = await client.post(f"/api/series/{series_id}/kind", json={"kind": "audio"})
    assert response.status_code == 422


async def test_setting_the_kind_of_a_missing_series_is_404(client):
    response = await client.post("/api/series/999999/kind", json={"kind": "prose"})
    assert response.status_code == 404


async def _match_searches(series_id: int) -> int:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text("select count(*) from job where type = 'match_search' and series_id = :id"),
                {"id": series_id},
            )
        ).scalar_one()


async def test_setting_the_kind_of_an_unmapped_series_searches_again(client):
    series_id = await _series(None)
    await client.post(f"/api/series/{series_id}/kind", json={"kind": "prose"})
    assert await _match_searches(series_id) == 1


async def test_setting_the_kind_of_a_mapped_series_does_not_search_again(client):
    series_id = await _series("comic")
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:id, 'comic-fake', 'https://comic.test/m/1', true)"
            ),
            {"id": series_id},
        )
        await session.commit()
    await client.post(f"/api/series/{series_id}/kind", json={"kind": "prose"})
    assert await _match_searches(series_id) == 0
