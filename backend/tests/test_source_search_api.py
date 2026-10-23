"""GET /api/sources/search: every source at once, ranked, partial, and stored nowhere."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.sources import base
from app.sources.base import Candidate

pytestmark = pytest.mark.asyncio


class FakeSource:
    kind = "comic"

    def __init__(self, site, *, score=0.5, fail=False, delay=0.0):
        self.site = site
        self.domains = ()
        self._score = score
        self._fail = fail
        self._delay = delay

    async def search(self, titles, *, limit=8):
        await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("the site answered with nonsense")
        return [
            Candidate(
                source_site=self.site,
                source_url=f"https://{self.site}.test/title/1",
                title=titles[0],
                score=self._score,
            )
        ]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    # Restored afterwards: the registry is module state, and a later test that
    # resolves a real site would otherwise find only these fakes.
    before = dict(base._REGISTRY)
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate source_mapping, series restart identity cascade"))
        await session.commit()
    yield
    base.install_registry(before)
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from setting where key = 'source_search_timeout'"))
        await session.commit()


def install(*sources):
    base.install_registry(
        {source.site: base.RegisteredSource(source, f"https://{source.site}.test") for source in sources}
    )


async def test_results_are_ranked_by_score_across_sources(client):
    install(FakeSource("low", score=0.2), FakeSource("high", score=0.9))

    response = await client.get("/api/sources/search", params={"q": "Solo Leveling"})

    assert response.status_code == 200
    body = response.json()
    assert body["searched"] == 2
    assert [r["source_site"] for r in body["results"]] == ["high", "low"]
    assert body["results"][0]["title"] == "Solo Leveling"
    assert body["errors"] == []


async def test_a_broken_source_is_reported_and_the_rest_still_answer(client):
    install(FakeSource("works"), FakeSource("broken", fail=True))

    body = (await client.get("/api/sources/search", params={"q": "x"})).json()

    assert [r["source_site"] for r in body["results"]] == ["works"]
    assert body["errors"] == [{"site": "broken", "detail": "the site answered with nonsense"}]


async def test_a_slow_source_times_out_without_holding_the_others(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into setting (key, value) values ('source_search_timeout', '1')"
                " on conflict (key) do update set value = excluded.value"
            )
        )
        await session.commit()
    install(FakeSource("quick"), FakeSource("slow", delay=5))

    body = (await client.get("/api/sources/search", params={"q": "x"})).json()

    assert [r["source_site"] for r in body["results"]] == ["quick"]
    assert body["errors"] == [{"site": "slow", "detail": "no answer in 1s"}]


async def test_a_mapped_result_points_at_its_series(client):
    install(FakeSource("site"))
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('Mapped', 'mapped', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:id, 'site', 'https://site.test/title/1', true)"
            ),
            {"id": series_id},
        )
        await session.commit()

    body = (await client.get("/api/sources/search", params={"q": "Mapped"})).json()

    assert body["results"][0]["series_id"] == series_id


async def test_a_blank_query_is_refused(client):
    install(FakeSource("site"))
    response = await client.get("/api/sources/search", params={"q": "   "})
    assert response.status_code == 400
