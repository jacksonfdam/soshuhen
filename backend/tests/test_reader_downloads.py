"""A chapter the reader touched still downloads when someone asks for it.

`streaming` means the reader's cache will become the archive. That is a reason
to build the archive from the cache, never a reason to leave the chapter out
of a download someone asked for.
"""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.handlers.batching import queue_batches


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, series, list_entry restart identity cascade")
        )
        await session.commit()


async def _series_with(states: list[str]) -> tuple[int, list[int]]:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', 's-downloads', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        ids = []
        for number, state in enumerate(states, start=1):
            ids.append(
                (
                    await session.execute(
                        text(
                            "insert into chapter (series_id, number, state)"
                            " values (:s, :n, :st) returning id"
                        ),
                        {"s": series_id, "n": Decimal(number), "st": state},
                    )
                ).scalar_one()
            )
        await session.commit()
    return int(series_id), [int(i) for i in ids]


async def _jobs() -> list[tuple[str, dict]]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(text("select type, payload from job order by id"))
        return [(row.type, row.payload) for row in rows.all()]


async def _states(ids: list[int]) -> list[str]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text("select state from chapter where id = any(cast(:ids as bigint[])) order by id"),
            {"ids": ids},
        )
        return [row[0] for row in rows.all()]


async def test_a_streaming_chapter_is_assembled_from_the_cache_not_batched():
    series_id, (known, streaming) = await _series_with(["known", "streaming"])
    async with get_sessionmaker()() as session:
        queued = await queue_batches(session, series_id, [known, streaming])
        await session.commit()

    assert queued == 2
    assert await _jobs() == [
        ("download_chapter", {"chapter_id": streaming, "from_cache": True}),
        ("download_batch", {"series_id": series_id, "chapter_ids": [known]}),
    ]
    # Still streaming: the reader keeps filling the cache the job reads from.
    assert await _states([known, streaming]) == ["queued", "streaming"]


async def test_a_requested_range_includes_a_chapter_being_read(client):
    series_id, (_, streaming) = await _series_with(["known", "streaming"])
    body = (await client.post(f"/api/series/{series_id}/download", json={})).json()
    assert body["queued"] == 2
    assert ("download_chapter", {"chapter_id": streaming, "from_cache": True}) in await _jobs()


async def test_turning_auto_download_on_includes_a_chapter_being_read(client):
    series_id, (_, streaming) = await _series_with(["known", "streaming"])
    body = (
        await client.post(f"/api/series/{series_id}/auto-download", json={"enabled": True})
    ).json()
    assert body["queued"] == 2
    assert ("download_chapter", {"chapter_id": streaming, "from_cache": True}) in await _jobs()
