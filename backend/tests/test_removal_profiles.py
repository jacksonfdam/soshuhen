"""Removing a series, or a profile, never takes another profile's series with it."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
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
                    "truncate list_entry, series, chapter, source_mapping, removed_entry,"
                    " provider_token restart identity cascade"
                )
            )
            await drop_other_profiles(session)
            await session.commit()

    await wipe()
    yield
    await wipe()


async def _series(session, slug: str, holders: list[int]) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:t, :t, false, '{}'::jsonb) returning id"
            ),
            {"t": slug},
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active)"
            " values (:s, 'mangadex', :u, true)"
        ),
        {"s": series_id, "u": f"https://x.test/{slug}"},
    )
    await session.execute(
        text("insert into chapter (series_id, number, state) values (:s, 1, 'known')"),
        {"s": series_id},
    )
    for profile_id in holders:
        await session.execute(
            text(
                "insert into list_entry (profile_id, provider, provider_media_id, series_id,"
                " status, user_progress_chapter, synonyms, raw, updated_at)"
                " values (:p, 'anilist', :m, :s, 'reading', 0, '[]', '{}', now())"
            ),
            {"p": profile_id, "m": slug, "s": series_id},
        )
    return series_id


async def count(session, sql: str, **params) -> int:
    return (await session.execute(text(sql), params)).scalar_one()


@pytest.fixture
async def people():
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        await session.commit()
    return owner, kid


async def test_owner_removing_a_shared_series_keeps_it_for_the_kid(client, people):
    owner, kid = people
    async with get_sessionmaker()() as session:
        shared = await _series(session, "shared", [owner, kid])
        await session.commit()

    response = await client.request("DELETE", "/api/series", json={"ids": [shared]})
    assert response.status_code == 200
    assert response.json()["removed"] == 0

    async with get_sessionmaker()() as session:
        assert await count(session, "select count(*) from series where id = :s", s=shared) == 1
        assert await count(session, "select count(*) from source_mapping") == 1
        assert await count(session, "select count(*) from chapter") == 1
        holders = (
            await session.execute(text("select profile_id from list_entry"))
        ).scalars().all()
        assert holders == [kid]
        tombstones = (
            await session.execute(text("select profile_id from removed_entry"))
        ).scalars().all()
        assert tombstones == [owner]

    owner_rows = (await client.get("/api/series")).json()
    kid_rows = (await client.get("/api/series", headers=as_profile(kid))).json()
    assert owner_rows == []
    assert [row["id"] for row in kid_rows] == [shared]


async def test_removing_a_series_nobody_else_holds_deletes_it(client, people):
    owner, _ = people
    async with get_sessionmaker()() as session:
        alone = await _series(session, "alone", [owner])
        await session.commit()
    response = await client.request("DELETE", "/api/series", json={"ids": [alone]})
    assert response.json()["removed"] == 1
    async with get_sessionmaker()() as session:
        assert await count(session, "select count(*) from series") == 0


async def test_deleting_a_profile_removes_her_series_only(client, people):
    owner, kid = people
    async with get_sessionmaker()() as session:
        mine = await _series(session, "mine", [owner])
        shared = await _series(session, "shared", [owner, kid])
        hers = await _series(session, "hers", [kid])
        await session.execute(
            text(
                "insert into provider_token (profile_id, provider, access_token)"
                " values (:p, 'anilist', 't')"
            ),
            {"p": kid},
        )
        await session.commit()

    response = await client.delete(f"/api/profiles/{kid}")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "series_removed": 1}

    async with get_sessionmaker()() as session:
        left = set((await session.execute(text("select id from series"))).scalars().all())
        assert left == {mine, shared}
        assert hers not in left
        assert await count(session, "select count(*) from provider_token") == 0
        assert await count(session, "select count(*) from profile where id = :k", k=kid) == 0
