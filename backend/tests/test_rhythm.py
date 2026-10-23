"""The release rhythm rule: what a series' recent release days say about today."""

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.rhythm import is_due, release_days, rhythm_days

TODAY = date(2026, 10, 23)


def weekly(count: int, last: date) -> list[date]:
    return [last - timedelta(days=7 * n) for n in range(count)]


def test_too_few_release_days_have_no_rhythm_and_are_always_due():
    days = weekly(2, TODAY - timedelta(days=3))
    assert rhythm_days(days) is None
    assert is_due(days, TODAY)


def test_a_weekly_series_reads_as_weekly():
    assert rhythm_days(weekly(6, TODAY)) == 7


def test_the_median_ignores_one_odd_gap():
    days = weekly(5, TODAY) + [TODAY - timedelta(days=1)]
    assert rhythm_days(days) == 7


def test_the_rhythm_is_clamped_to_four_weeks():
    days = [TODAY - timedelta(days=60 * n) for n in range(4)]
    assert rhythm_days(days) == 28


def test_a_weekly_series_is_left_alone_until_the_day_before_it_is_expected():
    last = TODAY - timedelta(days=3)
    assert not is_due(weekly(6, last), TODAY)


def test_a_weekly_series_is_asked_from_the_day_before_to_the_day_after():
    for since in (6, 7, 8):
        assert is_due(weekly(6, TODAY - timedelta(days=since)), TODAY)


def test_a_late_series_is_asked_once_per_rhythm():
    due = [
        since for since in range(9, 30) if is_due(weekly(6, TODAY - timedelta(days=since)), TODAY)
    ]
    assert due == [15, 22, 29]


def test_a_series_on_a_long_break_is_asked_every_four_weeks():
    # Ten weeks without a chapter: past the misses that count as late.
    due = [
        since
        for since in range(70, 140)
        if is_due(weekly(6, TODAY - timedelta(days=since)), TODAY)
    ]
    assert due == [x for x in range(70, 140) if (x - 8) % 28 == 0]


# --- release_days: what the rule is fed, read from the chapter table.


@pytest.fixture
async def seeded():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate chapter, source_mapping, series restart identity cascade")
        )
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('weekly', 'weekly', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active,"
                " discovered_at) values (:id, 'site', 'https://site.test/1', true,"
                " now() - interval '40 days')"
            ),
            {"id": series_id},
        )
        # The backlog, found with the mapping, and then four weekly releases.
        await session.execute(
            text(
                "insert into chapter (series_id, number, state, discovered_at)"
                " select :id, n, 'known', now() - interval '40 days' from generate_series(1, 9) n"
            ),
            {"id": series_id},
        )
        for number, ago in ((10, 28), (11, 21), (12, 14), (13, 7)):
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, discovered_at)"
                    " values (:id, :n, 'known', now() - make_interval(days => :ago))"
                ),
                {"id": series_id, "n": number, "ago": ago},
            )
        await session.commit()
    return series_id


@pytest.mark.asyncio
async def test_release_days_leave_the_backlog_out(seeded):
    async with get_sessionmaker()() as session:
        days = await release_days(session, [seeded])
    assert len(days[seeded]) == 4
    assert rhythm_days(days[seeded]) == 7


@pytest.mark.asyncio
async def test_the_series_detail_states_its_rhythm(seeded):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{seeded}")).json()
    assert detail["rhythm_days"] == 7


async def _queued_discoveries() -> int:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text("select count(*) from job where type = 'chapter_discover'")
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_the_schedule_skips_a_series_that_is_not_due_only_when_asked_to(seeded):
    from app.worker.main import enqueue_chapter_discover

    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job restart identity cascade"))
        # The latest weekly chapter arrived two days ago: the next is five off.
        await session.execute(
            text(
                "update chapter set discovered_at = discovered_at + interval '5 days'"
                " where series_id = :id and number >= 10"
            ),
            {"id": seeded},
        )
        await session.commit()

    await enqueue_chapter_discover()
    assert await _queued_discoveries() == 1

    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job restart identity cascade"))
        await session.execute(
            text(
                "insert into setting (key, value) values ('discover_by_rhythm', 'true')"
                " on conflict (key) do update set value = excluded.value"
            )
        )
        await session.commit()
    try:
        await enqueue_chapter_discover()
        assert await _queued_discoveries() == 0
    finally:
        async with get_sessionmaker()() as session:
            await session.execute(text("delete from setting where key = 'discover_by_rhythm'"))
            await session.commit()
