"""Each profile sees its own library; the web console sees every series."""

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
                    "truncate list_entry, series, chapter, notification, source_mapping, job"
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


async def _entry(session, profile_id: int, series_id: int, media_id: str, progress: int) -> None:
    await session.execute(
        text(
            "insert into list_entry (profile_id, provider, provider_media_id, series_id, status,"
            " user_progress_chapter, synonyms, raw, updated_at)"
            " values (:p, 'anilist', :m, :s, 'reading', :n, '[]', '{}', now())"
        ),
        {"p": profile_id, "m": media_id, "s": series_id, "n": progress},
    )


@pytest.fixture
async def library():
    """A: owner only. B: both. C: kid only. D: no list at all (an import)."""
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        ids = {name: await _series(session, name) for name in "ABCD"}
        await _entry(session, owner, ids["A"], "1", 4)
        await _entry(session, owner, ids["B"], "2", 10)
        await _entry(session, kid, ids["B"], "2", 2)
        await _entry(session, kid, ids["C"], "3", 1)
        await session.commit()
    return {"owner": owner, "kid": kid, **ids}


def titles(rows) -> set[str]:
    return {row["title"] for row in rows}


async def test_kid_sees_only_her_lists(client, library):
    kid_rows = (await client.get("/api/series", headers=as_profile(library["kid"]))).json()
    owner_rows = (await client.get("/api/series")).json()
    every = (await client.get("/api/series?scope=all")).json()

    assert titles(kid_rows) == {"B", "C"}
    assert titles(owner_rows) == {"A", "B", "D"}
    assert titles(every) == {"A", "B", "C", "D"}
    c = next(row for row in every if row["title"] == "C")
    assert c["held_by"] == [library["kid"]]


async def test_progress_shown_is_the_requesters(client, library):
    def progress_of_b(rows):
        return next(row["progress"] for row in rows if row["title"] == "B")

    kid_rows = (await client.get("/api/series", headers=as_profile(library["kid"]))).json()
    owner_rows = (await client.get("/api/series")).json()
    assert progress_of_b(kid_rows) == 2
    assert progress_of_b(owner_rows) == 10


async def _notify(series_id: int) -> int:
    async with get_sessionmaker()() as session:
        nid = (
            await session.execute(
                text(
                    "insert into notification (series_id, kind, count, first_number,"
                    " last_number) values (:s, 'chapters', 1, 5, 5) returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.commit()
    return nid


async def test_kid_gets_no_notification_for_an_owner_only_series(client, library):
    await _notify(library["A"])
    kid = (await client.get("/api/notifications", headers=as_profile(library["kid"]))).json()
    owner = (await client.get("/api/notifications")).json()
    assert kid["items"] == [] and kid["unread_count"] == 0
    assert len(owner["items"]) == 1 and owner["unread_count"] == 1


async def test_reading_a_notification_is_per_profile(client, library):
    nid = await _notify(library["B"])
    await client.post(f"/api/notifications/{nid}/read")
    kid = (await client.get("/api/notifications", headers=as_profile(library["kid"]))).json()
    owner = (await client.get("/api/notifications")).json()
    assert owner["unread_count"] == 0
    assert kid["unread_count"] == 1
    assert kid["items"][0]["read_at"] is None


async def test_updates_screen_is_scoped(client, library):
    async with get_sessionmaker()() as session:
        for name in ("A", "C"):
            await session.execute(
                text(
                    "insert into source_mapping (series_id, source_site, source_url, active,"
                    " discovered_at) values (:s, 'mangadex', :u, true, now() - interval '2 days')"
                ),
                {"s": library[name], "u": f"https://x.test/{name}"},
            )
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, discovered_at)"
                    " values (:s, 9, 'known', now())"
                ),
                {"s": library[name]},
            )
        await session.commit()
    kid = (await client.get("/api/updates", headers=as_profile(library["kid"]))).json()
    assert {c["series_title"] for c in kid["chapters"]} == {"C"}
