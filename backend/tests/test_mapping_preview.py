"""GET /api/series/{id}/mapping/preview: a move between sources, compared before it is made."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api import routes_series
from app.api.main import app
from app.db import get_sessionmaker
from app.sources.base import ChapterRef

pytestmark = pytest.mark.asyncio


class FakeSource:
    site = "newsite"
    kind = "comic"

    def __init__(self, numbers, fail=False):
        self.numbers = numbers
        self.fail = fail

    async def list_chapters(self, url, *, language="en"):
        if self.fail:
            raise RuntimeError("the title page moved")
        return [ChapterRef(Decimal(n), f"{url}/{n}") for n in self.numbers]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def series_id():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate chapter, list_entry, series restart identity cascade"))
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('S', 's', false, '{}'::jsonb, 'comic') returning id"
                )
            )
        ).scalar_one()
        for number, state in (("1", "downloaded"), ("2", "failed"), ("3", "known"), ("4", "known")):
            await session.execute(
                text("insert into chapter (series_id, number, state) values (:s, :n, :st)"),
                {"s": series_id, "n": Decimal(number), "st": state},
            )
        await session.execute(
            text(
                "insert into list_entry (series_id, provider, provider_media_id, status,"
                " user_progress_chapter, synonyms, raw)"
                " values (:s, 'local', :m, 'reading', 4, '[]'::jsonb, '{}'::jsonb)"
            ),
            {"s": series_id, "m": str(series_id)},
        )
        await session.commit()
    return series_id


async def test_the_preview_compares_the_two_sources(client, series_id, monkeypatch):
    monkeypatch.setattr(routes_series, "source_for_url", lambda url: FakeSource(["2", "3", "5", "6"]))

    body = (
        await client.get(
            f"/api/series/{series_id}/mapping/preview", params={"source_url": "https://n.test/x"}
        )
    ).json()

    assert body == {
        "source_site": "newsite",
        "chapters": 4,
        "last": 6.0,
        "current_last": 4.0,
        "progress": 4,
        "stops_before_progress": False,
        "gained": 2,
        "retried": 1,
        "set_aside": 1,
        "downloaded": 1,
    }


async def test_a_source_that_stops_short_says_so(client, series_id, monkeypatch):
    monkeypatch.setattr(routes_series, "source_for_url", lambda url: FakeSource(["1", "2"]))

    body = (
        await client.get(
            f"/api/series/{series_id}/mapping/preview", params={"source_url": "https://n.test/x"}
        )
    ).json()

    assert body["stops_before_progress"] is True


async def test_a_failing_source_answers_with_its_own_error(client, series_id, monkeypatch):
    monkeypatch.setattr(routes_series, "source_for_url", lambda url: FakeSource([], fail=True))

    response = await client.get(
        f"/api/series/{series_id}/mapping/preview", params={"source_url": "https://n.test/x"}
    )

    assert response.status_code == 502
    assert "the title page moved" in response.json()["detail"]
