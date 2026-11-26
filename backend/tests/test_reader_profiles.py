"""Reading state belongs to the profile reading; Komga only hears from the manager."""

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
                text("truncate list_entry, series, chapter, volume, job restart identity cascade")
            )
            await drop_other_profiles(session)
            await session.commit()

    await wipe()
    yield
    await wipe()


@pytest.fixture
async def library():
    """A series both profiles hold, with two chapters; the second is in Komga."""
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
        chapters = []
        for number, book in ((1, None), (2, "book-2")):
            chapters.append(
                (
                    await session.execute(
                        text(
                            "insert into chapter (series_id, number, state, komga_book_id)"
                            " values (:s, :n, 'downloaded', :b) returning id"
                        ),
                        {"s": series_id, "n": number, "b": book},
                    )
                ).scalar_one()
            )
        for profile_id in (owner, kid):
            await session.execute(
                text(
                    "insert into list_entry (profile_id, provider, provider_media_id, series_id,"
                    " status, user_progress_chapter, synonyms, raw, updated_at)"
                    " values (:p, 'anilist', '42', :s, 'reading', 1, '[]', '{}', now())"
                ),
                {"p": profile_id, "s": series_id},
            )
        volume_id = (
            await session.execute(
                text(
                    "insert into volume (series_id, number, edition, source_volume_id, state,"
                    " komga_book_id, status)"
                    " values (:s, 1, 'light', 'v1', 'downloaded', 'book-v1', 'owned')"
                    " returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.commit()
    return {
        "owner": owner,
        "kid": kid,
        "series": series_id,
        "chapters": chapters,
        "volume": volume_id,
    }


async def jobs_of(type_: str) -> list[dict]:
    async with get_sessionmaker()() as session:
        return [
            row.payload
            for row in (
                await session.execute(
                    text("select payload from job where type = :t"), {"t": type_}
                )
            ).all()
        ]


async def test_positions_are_kept_apart(client, library):
    s = library
    first, _ = s["chapters"]
    url = f"/api/reader/series/{s['series']}/position"
    await client.put(url, json={"chapter_id": first, "page": 3})
    await client.put(url, json={"chapter_id": first, "page": 9}, headers=as_profile(s["kid"]))

    resume = f"/api/reader/series/{s['series']}/resume"
    assert (await client.get(resume)).json() == {"chapter_id": first, "page": 3}
    assert (await client.get(resume, headers=as_profile(s["kid"]))).json() == {
        "chapter_id": first,
        "page": 9,
    }


async def test_reader_prefs_are_kept_apart(client, library):
    s = library
    url = f"/api/reader/series/{s['series']}/prefs"
    kid_prefs = {"mode": "long_strip", "scale": "fit_width", "background": "white"}
    await client.put(url, json=kid_prefs, headers=as_profile(s["kid"]))
    assert (await client.get(url, headers=as_profile(s["kid"]))).json()["mode"] == "long_strip"
    assert (await client.get(url)).json()["mode"] != "long_strip"


async def test_bookmarks_are_kept_apart(client, library):
    s = library
    first, _ = s["chapters"]
    response = await client.put(
        f"/api/series/{s['series']}/chapters/{first}/bookmark",
        json={"bookmarked": True},
        headers=as_profile(s["kid"]),
    )
    assert response.status_code == 200

    def flag(detail):
        return next(c["bookmarked"] for c in detail["chapters"] if c["id"] == first)

    owner_view = (await client.get(f"/api/series/{s['series']}")).json()
    kid_view = (
        await client.get(f"/api/series/{s['series']}", headers=as_profile(s["kid"]))
    ).json()
    assert flag(owner_view) is False
    assert flag(kid_view) is True


async def test_kid_finishing_a_chapter_never_marks_komga(client, library):
    s = library
    _, second = s["chapters"]
    kid = await client.post(
        f"/api/reader/chapters/{second}/complete", headers=as_profile(s["kid"])
    )
    assert kid.json() == {"progress_queued": True, "komga_queued": False}
    assert await jobs_of("komga_read_progress") == []
    [write] = await jobs_of("progress_write")
    assert write["profile_id"] == s["kid"]

    owner = await client.post(f"/api/reader/chapters/{second}/complete")
    assert owner.json()["komga_queued"] is True


async def test_kid_finishing_a_volume_queues_nothing(client, library):
    s = library
    response = await client.post(
        f"/api/reader/volumes/{s['volume']}/complete", headers=as_profile(s["kid"])
    )
    assert response.json() == {"progress_queued": False, "komga_queued": False}
    assert await jobs_of("komga_read_progress") == []
