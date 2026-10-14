"""Continue reading follows reading, not list syncs.

`list_entry.updated_at` moves whenever a sync rewrites the row, so ordering by
it put whatever MyAnimeList or AniList touched last at the front. Reading is
recorded in two places that only reading moves: a page turned in the reader,
and progress moving forward.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

TABLES = (
    "job, job_event, chapter, source_mapping, list_entry, progress_event, "
    "series, provider_token, setting"
)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text(f"truncate {TABLES} restart identity cascade"))
        await session.commit()


async def _exec(statement: str, params: dict | None = None) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(text(statement), params or {})
        await session.commit()


async def _series(title: str, *, synced: str) -> int:
    """A series on one list, last rewritten by a sync at `synced`."""
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values (:t, :slug, false, '{}'::jsonb) returning id"
                ),
                {"t": title, "slug": title.lower()},
            )
        ).scalar_one()
        await session.execute(
            text(
                f"""
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, raw, updated_at)
                values ('anilist', :m, :s, '[]'::jsonb, 'reading', 1, '{{}}'::jsonb, {synced})
                """
            ),
            {"m": str(series_id), "s": series_id},
        )
        await session.execute(
            text(
                "insert into chapter (series_id, number, state) values (:s, 1, 'known')"
            ),
            {"s": series_id},
        )
        await session.commit()
    return int(series_id)


async def _progressed(series_id: int, when: str) -> None:
    await _exec(
        f"insert into progress_event (series_id, chapter, delta, source, created_at)"
        f" values (:s, 2, 1, 'manual', {when})",
        {"s": series_id},
    )


async def _turned_a_page(series_id: int, when: str) -> None:
    await _exec(
        f"""
        insert into reading_position (series_id, chapter_id, page, updated_at)
        select :s, id, 3, {when} from chapter where series_id = :s limit 1
        """,
        {"s": series_id},
    )


async def _home(client) -> list[str]:
    body = (await client.get("/api/dashboard")).json()
    return [item["title"] for item in body["continue_reading"]]


async def test_a_page_turned_in_the_reader_puts_the_series_first(client):
    read = await _series("Read", synced="now() - interval '3 days'")
    await _series("Synced", synced="now() - interval '1 hour'")
    await _turned_a_page(read, "now() - interval '5 minutes'")

    assert await _home(client) == ["Read", "Synced"]


async def test_progress_moving_forward_puts_the_series_first(client):
    read = await _series("Read", synced="now() - interval '3 days'")
    await _series("Synced", synced="now() - interval '1 hour'")
    await _progressed(read, "now() - interval '10 minutes'")

    assert await _home(client) == ["Read", "Synced"]


async def test_a_sync_rewriting_the_entry_does_not_reorder_reading(client):
    """MAL rewrote Older's entry a minute ago; Newer was actually read later."""
    older = await _series("Older", synced="now() - interval '1 minute'")
    newer = await _series("Newer", synced="now() - interval '2 days'")
    await _progressed(older, "now() - interval '3 days'")
    await _turned_a_page(newer, "now() - interval '1 day'")

    assert await _home(client) == ["Newer", "Older"]


async def test_a_series_never_read_here_comes_after_ones_that_were(client):
    """History only fills forward, so a series with none falls back to the sync
    time, behind everything with a reading record."""
    await _series("No History", synced="now()")
    read = await _series("Read Yesterday", synced="now() - interval '5 days'")
    await _progressed(read, "now() - interval '1 day'")

    assert await _home(client) == ["Read Yesterday", "No History"]


async def test_the_library_list_carries_when_each_series_was_last_read(client):
    read = await _series("Read", synced="now() - interval '3 days'")
    await _series("Never", synced="now()")
    await _turned_a_page(read, "now() - interval '5 minutes'")

    rows = {row["title"]: row for row in (await client.get("/api/series")).json()}

    assert rows["Read"]["last_read_at"] is not None
    assert rows["Never"]["last_read_at"] is None
