"""A Mihon backup through the API: exported, read back, and imported against the library."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.mihon.backup import (
    TRACKER_ANILIST,
    MihonBackup,
    MihonChapter,
    MihonManga,
    MihonTracking,
    read_backup,
    source_id,
    write_backup,
)
from app.sources import base

pytestmark = pytest.mark.asyncio

FAKE_ID = source_id("Fake Scans", "en")


class FakeSource:
    site = "fakescans"
    kind = "comic"
    domains = ()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def world():
    before = dict(base._REGISTRY)
    base.install_registry(
        {"fakescans": base.RegisteredSource(FakeSource(), "https://fake.test")}
    )
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, chapter, list_entry, source_mapping, series restart identity cascade")
        )
        await session.execute(
            text(
                "insert into site_catalogue (key, name, template, base_url, lang, nsfw, overrides,"
                " version, hand_ported) values ('fakescans', 'Fake Scans', 'native',"
                " 'https://fake.test', 'en', false, '{}'::jsonb, '1', true)"
                " on conflict (key) do nothing"
            )
        )
        await session.commit()
    yield
    base.install_registry(before)
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from site_catalogue where key = 'fakescans'"))
        await session.commit()


async def _series(session, title: str, anilist_id: int | None = None) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values (:t, :t, true, '{}'::jsonb, 'comic') returning id"
            ),
            {"t": title},
        )
    ).scalar_one()
    if anilist_id is not None:
        await session.execute(
            text(
                "insert into list_entry (series_id, provider, provider_media_id, status,"
                " user_progress_chapter, synonyms, raw)"
                " values (:s, 'anilist', :m, 'reading', 2, '[]'::jsonb, '{}'::jsonb)"
            ),
            {"s": series_id, "m": str(anilist_id)},
        )
    return series_id


async def test_the_export_is_a_backup_mihon_reads(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Frieren", anilist_id=118586)
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:s, 'fakescans', 'https://fake.test/manga/frieren/', true)"
            ),
            {"s": series_id},
        )
        for number, bookmarked in ((1, False), (2, True), (3, False)):
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, source_url, bookmarked)"
                    " values (:s, :n, 'known', :u, :b)"
                ),
                {"s": series_id, "n": number, "u": f"https://fake.test/manga/frieren/{number}/",
                 "b": bookmarked},
            )
        await session.commit()

    response = await client.get("/api/backup/mihon")

    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.tachibk"')
    backup = read_backup(response.content)
    assert backup.sources == {FAKE_ID: "Fake Scans"}
    manga = backup.mangas[0]
    assert (manga.source_id, manga.url, manga.title) == (FAKE_ID, "/manga/frieren/", "Frieren")
    assert [(c.number, c.read, c.bookmark) for c in manga.chapters] == [
        (1.0, True, False),
        (2.0, True, True),
        (3.0, False, False),
    ]
    assert manga.chapters[0].url == "/manga/frieren/1/"
    track = manga.tracking[0]
    assert (track.tracker, track.media_id, track.status, track.last_chapter_read) == (
        TRACKER_ANILIST,
        118586,
        1,
        2.0,
    )


def _backup(*mangas: MihonManga) -> bytes:
    return write_backup(MihonBackup(mangas=list(mangas), sources={FAKE_ID: "Fake Scans"}))


async def test_an_import_previews_then_maps_and_bookmarks(client):
    async with get_sessionmaker()() as session:
        by_tracker = await _series(session, "Sousou no Frieren", anilist_id=118586)
        by_title = await _series(session, "Dandadan")
        await session.execute(
            text("insert into chapter (series_id, number, state) values (:s, 4, 'known')"),
            {"s": by_tracker},
        )
        await session.commit()
    data = _backup(
        MihonManga(
            source_id=FAKE_ID,
            url="/manga/frieren/",
            title="Frieren: Beyond Journey's End",
            chapters=[MihonChapter(url="/c/4", name="4", number=4.0, bookmark=True)],
            tracking=[MihonTracking(tracker=TRACKER_ANILIST, media_id=118586)],
        ),
        MihonManga(source_id=FAKE_ID, url="/manga/dandadan/", title="Dandadan"),
        MihonManga(source_id=FAKE_ID, url="/manga/x/", title="Not In The Library"),
        MihonManga(source_id=999, url="/y", title="Dandadan"),
    )

    preview = (await client.post("/api/backup/mihon", content=data)).json()

    assert preview["applied"] is False
    actions = [(i["title"], i["action"]) for i in preview["items"]]
    assert actions == [
        ("Frieren: Beyond Journey's End", "map"),
        ("Dandadan", "map"),
        ("Not In The Library", "unmatched"),
        ("Dandadan", "kept"),
    ]
    assert preview["items"][0]["matched_by"] == "linked to the same anilist entry"
    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from source_mapping"))).scalar_one()
    assert count == 0

    applied = (await client.post("/api/backup/mihon?apply=true", content=data)).json()

    assert applied["counts"] == {"map": 2, "unmatched": 1, "kept": 1}
    async with get_sessionmaker()() as session:
        mappings = dict(
            (
                await session.execute(
                    text("select series_id, source_url from source_mapping where active")
                )
            ).all()
        )
        bookmarked = (
            await session.execute(
                text("select bookmarked from chapter where series_id = :s"), {"s": by_tracker}
            )
        ).scalar_one()
        jobs = (
            await session.execute(text("select count(*) from job where type = 'chapter_discover'"))
        ).scalar_one()
    assert mappings == {
        by_tracker: "https://fake.test/manga/frieren/",
        by_title: "https://fake.test/manga/dandadan/",
    }
    assert bookmarked is True
    assert jobs == 2


async def test_a_mapped_series_keeps_its_source(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Dandadan")
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:s, 'fakescans', 'https://fake.test/manga/other/', true)"
            ),
            {"s": series_id},
        )
        await session.commit()

    body = (
        await client.post(
            "/api/backup/mihon?apply=true",
            content=_backup(MihonManga(source_id=FAKE_ID, url="/manga/dandadan/", title="Dandadan")),
        )
    ).json()

    assert body["items"][0]["action"] == "kept"


async def test_a_file_that_is_not_a_backup_is_refused(client):
    response = await client.post("/api/backup/mihon", content=b"\x1f\x8bnot really gzip")
    assert response.status_code == 400
