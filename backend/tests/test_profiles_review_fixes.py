"""Findings from the whole-branch review of profiles, each pinned by a test."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import PermanentError
from app.profiles import of_job
from app.queue import repo
from tests.profiles_fixture import as_profile, drop_other_profiles, make_profile, manager_id

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
                    "truncate list_entry, series, chapter, removed_entry, job, suggestion"
                    " restart identity cascade"
                )
            )
            await drop_other_profiles(session)
            await session.commit()

    await wipe()
    yield
    await wipe()


async def _series(session, slug: str) -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:t, :t, false, '{}'::jsonb) returning id"
            ),
            {"t": slug},
        )
    ).scalar_one()


async def _entry(session, profile_id: int, series_id: int, raw: dict) -> None:
    await session.execute(
        text(
            "insert into list_entry (profile_id, provider, provider_media_id, series_id, status,"
            " user_progress_chapter, synonyms, raw, updated_at)"
            " values (:p, 'anilist', '42', :s, 'reading', 0, '[]', cast(:r as jsonb), now())"
        ),
        {"p": profile_id, "s": series_id, "r": json.dumps(raw)},
    )


async def test_detail_shows_only_the_requesters_personal_list_fields(client):
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        series_id = await _series(session, "shared")
        media = {"description": "A shared synopsis", "title": {"romaji": "Shared"}}
        await _entry(
            session, owner, series_id, {"media": media, "notes": "owner's note", "score": 9}
        )
        await _entry(session, kid, series_id, {"media": media})
        await session.commit()

    kid_meta = (
        await client.get(f"/api/series/{series_id}", headers=as_profile(kid))
    ).json()["metadata"]
    owner_meta = (await client.get(f"/api/series/{series_id}")).json()["metadata"]

    assert kid_meta["synopsis"] == "A shared synopsis"
    assert kid_meta["notes"] is None
    assert kid_meta["user_score"] is None
    assert kid_meta["user_tags"] == []
    assert owner_meta["notes"] == "owner's note"
    assert owner_meta["user_score"] is not None


async def test_a_deleted_profiles_job_fails_permanently():
    with pytest.raises(PermanentError):
        async with get_sessionmaker()() as session:
            await of_job(session, {"profile_id": 999999})


async def test_deleting_a_profile_cancels_its_waiting_jobs(client):
    async with get_sessionmaker()() as session:
        kid = await make_profile(session)
        await repo.enqueue(
            session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": kid},
            dedupe_key=f"list_sync:{kid}:anilist",
        )
        await session.commit()
    assert (await client.delete(f"/api/profiles/{kid}")).status_code == 200
    async with get_sessionmaker()() as session:
        waiting = (
            await session.execute(text("select count(*) from job where state = 'pending'"))
        ).scalar_one()
    assert waiting == 0


async def test_removal_reports_what_left_the_library_and_what_was_skipped(client):
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        shared = await _series(session, "shared")
        hers = await _series(session, "hers")
        await _entry(session, owner, shared, {})
        await _entry(session, kid, shared, {})
        await session.execute(
            text(
                "insert into list_entry (profile_id, provider, provider_media_id, series_id,"
                " status, user_progress_chapter, synonyms, raw, updated_at)"
                " values (:p, 'anilist', '7', :s, 'reading', 0, '[]', '{}', now())"
            ),
            {"p": kid, "s": hers},
        )
        await session.commit()

    body = (
        await client.request("DELETE", "/api/series", json={"ids": [shared, hers]})
    ).json()
    assert body["removed"] == 1  # left the owner's library
    assert body["deleted"] == 0  # the kid still holds it
    assert body["skipped"] == [hers]  # never in the owner's library


async def test_a_profile_cannot_delete_a_series_no_list_holds(client):
    async with get_sessionmaker()() as session:
        kid = await make_profile(session)
        imported = await _series(session, "imported")
        await session.commit()
    body = (
        await client.request(
            "DELETE", "/api/series", json={"ids": [imported]}, headers=as_profile(kid)
        )
    ).json()
    assert body["skipped"] == [imported]
    async with get_sessionmaker()() as session:
        left = (
            await session.execute(text("select count(*) from series where id = :s"), {"s": imported})
        ).scalar_one()
    assert left == 1


async def test_the_manager_still_removes_an_import(client):
    async with get_sessionmaker()() as session:
        imported = await _series(session, "imported")
        await session.commit()
    body = (await client.request("DELETE", "/api/series", json={"ids": [imported]})).json()
    assert body["removed"] == 1 and body["deleted"] == 1


async def test_suggestions_on_the_dashboard_are_the_managers_alone(client):
    async with get_sessionmaker()() as session:
        kid = await make_profile(session)
        await session.execute(
            text(
                "insert into suggestion (provider, provider_media_id, title, state, rank_score,"
                " meta, alt_ids) values ('anilist', '5', 'From an anime', 'new', 1, '{}', '{}')"
            )
        )
        await session.commit()
    owner_view = (await client.get("/api/dashboard")).json()
    kid_view = (await client.get("/api/dashboard", headers=as_profile(kid))).json()
    assert len(owner_view["suggestions"]) == 1
    assert kid_view["suggestions"] == []
