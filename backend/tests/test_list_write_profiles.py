"""Progress, status and notes go to the lists of the profile that made the change."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import JobType, Provider
from app.providers import get_source
from app.providers.tokens import store_token
from tests.profiles_fixture import (
    as_profile,
    drop_other_profiles,
    make_profile,
    manager_id,
    run_one,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async def wipe():
        async with get_sessionmaker()() as session:
            await session.execute(
                text(
                    "truncate list_entry, series, provider_token, job, progress_event"
                    " restart identity cascade"
                )
            )
            await drop_other_profiles(session)
            await session.commit()

    await wipe()
    yield
    await wipe()


@pytest.fixture
async def shared_series():
    """One series both profiles hold on AniList: the owner at 10, the kid at 2."""
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('Frieren', 'frieren', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        for profile_id, progress, token in ((owner, 10, "owner-token"), (kid, 2, "kid-token")):
            await session.execute(
                text(
                    "insert into list_entry (profile_id, provider, provider_media_id, series_id,"
                    " status, user_progress_chapter, synonyms, raw, updated_at)"
                    " values (:p, 'anilist', '42', :s, 'reading', :n, '[]', '{}', now())"
                ),
                {"p": profile_id, "s": series_id, "n": progress},
            )
            await store_token(
                session, profile_id, Provider.ANILIST,
                access_token=token, refresh_token=None, expires_in=None,
            )
        await session.commit()
    return {"owner": owner, "kid": kid, "series": series_id}


@pytest.fixture
def anilist_writes(monkeypatch):
    calls: list[tuple] = []
    source_type = type(get_source(Provider.ANILIST))

    async def push_progress(self, token, media_id, chapter, volume=None):
        calls.append(("progress", token, chapter))

    async def set_status(self, token, media_id, status):
        calls.append(("status", token, str(status)))

    monkeypatch.setattr(source_type, "push_progress", push_progress)
    monkeypatch.setattr(source_type, "set_status", set_status)
    return calls


async def pending(session, job_type: JobType) -> list[dict]:
    return [
        row.payload
        for row in (
            await session.execute(
                text("select payload from job where type = :t and state = 'pending'"),
                {"t": str(job_type)},
            )
        ).all()
    ]


async def progress_of(session, profile_id: int) -> int:
    return (
        await session.execute(
            text("select user_progress_chapter from list_entry where profile_id = :p"),
            {"p": profile_id},
        )
    ).scalar_one()


async def test_kid_progress_reaches_kid_lists_only(client, shared_series, anilist_writes):
    s = shared_series
    response = await client.post(
        f"/api/series/{s['series']}/progress", json={"chapter": 5}, headers=as_profile(s["kid"])
    )
    assert response.status_code == 200

    async with get_sessionmaker()() as session:
        [payload] = await pending(session, JobType.PROGRESS_WRITE)
        assert payload["profile_id"] == s["kid"]
        await run_one(session, JobType.PROGRESS_WRITE, payload)
        assert await progress_of(session, s["kid"]) == 5
        assert await progress_of(session, s["owner"]) == 10
        events = (
            await session.execute(text("select profile_id from progress_event"))
        ).scalars().all()
    assert anilist_writes == [("progress", "kid-token", 5)]
    assert events == [s["kid"]]


async def test_the_forward_only_guard_reads_the_requesters_lists(client, shared_series):
    s = shared_series
    # 5 is behind the owner's 10 but ahead of the kid's 2.
    kid = await client.post(
        f"/api/series/{s['series']}/progress", json={"chapter": 5}, headers=as_profile(s["kid"])
    )
    owner = await client.post(f"/api/series/{s['series']}/progress", json={"chapter": 5})
    assert kid.status_code == 200
    assert owner.status_code != 200


async def test_two_profiles_queue_separate_writes(client, shared_series):
    s = shared_series
    await client.post(
        f"/api/series/{s['series']}/progress", json={"chapter": 5}, headers=as_profile(s["kid"])
    )
    await client.post(f"/api/series/{s['series']}/progress", json={"chapter": 11})
    async with get_sessionmaker()() as session:
        payloads = await pending(session, JobType.PROGRESS_WRITE)
    assert sorted((p["profile_id"], p["chapter"]) for p in payloads) == sorted(
        [(s["kid"], 5), (s["owner"], 11)]
    )


async def test_a_job_from_before_the_upgrade_runs_as_the_manager(shared_series, anilist_writes):
    s = shared_series
    async with get_sessionmaker()() as session:
        await run_one(
            session, JobType.PROGRESS_WRITE, {"series_id": s["series"], "chapter": 12}
        )
        assert await progress_of(session, s["owner"]) == 12
        assert await progress_of(session, s["kid"]) == 2
    assert anilist_writes == [("progress", "owner-token", 12)]


async def test_status_write_is_per_profile(client, shared_series, anilist_writes):
    s = shared_series
    response = await client.post(
        f"/api/series/{s['series']}/status",
        json={"status": "on_hold"},
        headers=as_profile(s["kid"]),
    )
    assert response.status_code == 200
    async with get_sessionmaker()() as session:
        [payload] = await pending(session, JobType.STATUS_WRITE)
        assert payload["profile_id"] == s["kid"]
        await run_one(session, JobType.STATUS_WRITE, payload)
        statuses = dict(
            (await session.execute(text("select profile_id, status from list_entry"))).all()
        )
    assert anilist_writes == [("status", "kid-token", "on_hold")]
    assert statuses == {s["kid"]: "on_hold", s["owner"]: "reading"}


async def test_tracking_locally_is_per_profile(client):
    async with get_sessionmaker()() as session:
        kid = await make_profile(session)
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('Solo', 'solo', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        await session.commit()
    response = await client.post(f"/api/series/{series_id}/track-local", headers=as_profile(kid))
    assert response.status_code == 200
    async with get_sessionmaker()() as session:
        holders = (
            await session.execute(
                text("select profile_id from list_entry where provider = 'local'")
            )
        ).scalars().all()
    assert holders == [kid]
