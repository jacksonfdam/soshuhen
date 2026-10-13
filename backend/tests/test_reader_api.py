"""The reader's HTTP surface against a real database and a stub source."""

import asyncio
import zipfile
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources.base import PageRef, RegisteredSource, install_registry
from tests.test_download_chapter_handler import FakeSource, Stub, _catalogue

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    (tmp_path / "manga").mkdir()
    (tmp_path / "cache").mkdir()
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "manga"))
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, series, list_entry, setting restart identity cascade")
        )
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from site_catalogue where key like 'stub-%'"))
        await session.execute(text("delete from source_pref where key like 'stub-%'"))
        await session.commit()
    get_settings.cache_clear()


async def _series(session, *, site: str | None = None, slug: str = "teto") -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values ('Teto X Egen', :slug, false, '{}'::jsonb) returning id"
            ),
            {"slug": slug},
        )
    ).scalar_one()
    if site is not None:
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:s, :site, 'https://stubsite.test/manga/1', true)"
            ),
            {"s": series_id, "site": site},
        )
    await session.commit()
    return int(series_id)


async def _chapter(
    session,
    series_id: int,
    number: str,
    *,
    url: str | None = None,
    file_path: str | None = None,
    state: str = "known",
    book: str | None = None,
) -> int:
    chapter_id = (
        await session.execute(
            text(
                "insert into chapter (series_id, number, title, source_url, state, file_path,"
                " komga_book_id) values (:s, :n, :t, :url, :state, :path, :book) returning id"
            ),
            {
                "s": series_id,
                "n": Decimal(number),
                "t": f"Chapter {number}",
                "url": url,
                "state": state,
                "path": file_path,
                "book": book,
            },
        )
    ).scalar_one()
    await session.commit()
    return int(chapter_id)


def _cbz(path, pages: list[bytes]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for index, data in enumerate(pages, start=1):
            zf.writestr(f"{index:03d}.jpg", data)
        zf.writestr("ComicInfo.xml", b"<ComicInfo/>")
    return str(path)


async def _state(chapter_id: int) -> str:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text("select state from chapter where id = :id"), {"id": chapter_id}
            )
        ).scalar_one()


async def _assembly_jobs(chapter_id: int) -> int:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text(
                    "select count(*) from job where type = 'download_chapter'"
                    " and (payload->>'chapter_id')::bigint = :id"
                    " and (payload->>'from_cache')::boolean"
                ),
                {"id": chapter_id},
            )
        ).scalar_one()


class Streamed:
    """A stub site and a fake source wired into the registry and catalogue."""

    def __init__(self, router, pages_for):
        self.hits: list[str] = []

        def counting(path):
            self.hits.append(path)
            return router(path)

        self.stub = Stub(counting)
        self.chapter_url = f"{self.stub.base_url}/manga/1/chapter/1"
        self.source = FakeSource(self.stub.key, pages={self.chapter_url: pages_for})
        install_registry(
            {self.stub.key: RegisteredSource(source=self.source, base_url=self.stub.base_url)}
        )

    async def seed(self, session) -> tuple[int, int]:
        await _catalogue(session, self.stub.key, self.stub.base_url)
        series_id = await _series(session, site=self.stub.key)
        chapter_id = await _chapter(session, series_id, "1", url=self.chapter_url)
        return series_id, chapter_id

    def close(self):
        self.stub.close()


def _always(status: int, body: bytes = JPEG):
    return lambda path: (status, "image/jpeg" if status == 200 else "text/plain", body)


async def test_an_archived_chapter_serves_its_pages(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG + b"1", JPEG + b"2"])
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", file_path=path, state="downloaded")

    manifest = (await client.get(f"/api/reader/chapters/{chapter_id}")).json()
    assert manifest["origin"] == "archive"
    assert manifest["page_count"] == 2

    response = await client.get(f"/api/reader/chapters/{chapter_id}/pages/1")
    assert response.status_code == 200
    assert response.content == JPEG + b"2"
    assert response.headers["content-type"] == "image/jpeg"
    assert "immutable" in response.headers["cache-control"]


async def test_a_page_past_the_end_is_404(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG])
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", file_path=path, state="downloaded")
    assert (await client.get(f"/api/reader/chapters/{chapter_id}/pages/1")).status_code == 404
    assert (await client.get(f"/api/reader/chapters/{chapter_id}/pages/-1")).status_code == 404


async def test_an_unknown_chapter_is_404(client):
    assert (await client.get("/api/reader/chapters/999999")).status_code == 404


async def test_a_streamed_page_is_fetched_once_then_served_from_the_cache(client):
    streamed = Streamed(_always(200), [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)

        manifest = (await client.get(f"/api/reader/chapters/{chapter_id}")).json()
        assert manifest["origin"] == "stream"
        assert manifest["page_count"] == 2

        first = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        second = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert first.content == second.content == JPEG
        assert streamed.hits.count("/p1.jpg") == 1
        assert await _state(chapter_id) == "streaming"
    finally:
        streamed.close()


async def test_the_last_cached_page_queues_exactly_one_assembly(client):
    streamed = Streamed(_always(200), [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert await _assembly_jobs(chapter_id) == 0

        await asyncio.gather(
            client.get(f"/api/reader/chapters/{chapter_id}/pages/1"),
            client.get(f"/api/reader/chapters/{chapter_id}/pages/1"),
        )
        assert await _assembly_jobs(chapter_id) == 1
    finally:
        streamed.close()


async def test_a_stale_page_list_is_fetched_again_once(client):
    """A list stored an hour ago can name pages the CDN no longer serves."""

    def router(path):
        return (404, "text/plain", b"gone") if path == "/old.jpg" else (200, "image/jpeg", JPEG)

    streamed = Streamed(router, [PageRef(url="/old.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        await client.get(f"/api/reader/chapters/{chapter_id}")  # stores the old list

        streamed.source._pages[streamed.chapter_url] = [PageRef(url="/new.jpg")]
        response = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")

        assert response.status_code == 200
        assert "/new.jpg" in streamed.hits
    finally:
        streamed.close()


async def test_a_page_the_source_will_not_serve_is_502(client):
    streamed = Streamed(_always(403, b"no"), [PageRef(url="/p1.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        response = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert response.status_code == 502
    finally:
        streamed.close()


async def test_a_chapter_the_source_refuses_is_410(client):
    streamed = Streamed(_always(200), [])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        streamed.source._unavailable = {streamed.chapter_url}
        assert (await client.get(f"/api/reader/chapters/{chapter_id}")).status_code == 410
    finally:
        streamed.close()


async def test_a_chapter_with_no_mapping_and_no_file_is_409(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", url="https://nowhere.test/c/1")
    assert (await client.get(f"/api/reader/chapters/{chapter_id}")).status_code == 409


async def test_a_chapter_that_reaches_the_library_is_served_from_the_archive(client, tmp_path):
    streamed = Streamed(_always(200), [PageRef(url="/p1.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")

        path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG + b"archived"])
        async with get_sessionmaker()() as session:
            await session.execute(
                text("update chapter set state = 'downloaded', file_path = :p where id = :id"),
                {"p": path, "id": chapter_id},
            )
            await session.commit()

        manifest = (await client.get(f"/api/reader/chapters/{chapter_id}")).json()
        assert manifest["origin"] == "archive"
        page = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert page.content == JPEG + b"archived"
    finally:
        streamed.close()


async def test_a_file_path_outside_the_library_is_not_served(client, tmp_path):
    path = _cbz(tmp_path / "elsewhere" / "c1.cbz", [JPEG])
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", file_path=path, state="downloaded")
    # Not in the library and no source to stream from.
    assert (await client.get(f"/api/reader/chapters/{chapter_id}")).status_code == 409


async def _three_archived_chapters(tmp_path) -> tuple[int, list[int]]:
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ids = []
        for number in ("1", "2", "3"):
            path = _cbz(tmp_path / "manga" / "teto" / f"c{number}.cbz", [JPEG, JPEG])
            ids.append(
                await _chapter(session, series_id, number, file_path=path, state="downloaded")
            )
    return series_id, ids


async def test_manifest_names_the_chapters_either_side(client, tmp_path):
    _, (first, middle, last) = await _three_archived_chapters(tmp_path)
    body = (await client.get(f"/api/reader/chapters/{middle}")).json()
    assert body["previous"]["id"] == first
    assert body["next"]["id"] == last
    edge = (await client.get(f"/api/reader/chapters/{first}")).json()
    assert edge["previous"] is None


async def test_position_round_trips_and_only_applies_to_its_chapter(client, tmp_path):
    series_id, (first, middle, _) = await _three_archived_chapters(tmp_path)
    saved = await client.put(
        f"/api/reader/series/{series_id}/position", json={"chapter_id": middle, "page": 1}
    )
    assert saved.status_code == 200
    assert (await client.get(f"/api/reader/chapters/{middle}")).json()["position"] == 1
    assert (await client.get(f"/api/reader/chapters/{first}")).json()["position"] is None


async def test_a_position_for_another_series_chapter_is_refused(client, tmp_path):
    _, (first, _, _) = await _three_archived_chapters(tmp_path)
    async with get_sessionmaker()() as session:
        other = await _series(session, slug="other")
    response = await client.put(
        f"/api/reader/series/{other}/position", json={"chapter_id": first, "page": 0}
    )
    assert response.status_code == 404


async def test_prefs_fall_back_to_the_defaults_then_stick_per_series(client, tmp_path):
    series_id, (first, _, _) = await _three_archived_chapters(tmp_path)
    prefs = (await client.get(f"/api/reader/series/{series_id}/prefs")).json()
    assert prefs == {
        "mode": "paged_rtl",
        "scale": "fit_screen",
        "background": "black",
        "custom": False,
    }

    stored = await client.put(
        f"/api/reader/series/{series_id}/prefs",
        json={"mode": "long_strip", "scale": "fit_width", "background": "white"},
    )
    assert stored.json()["custom"] is True
    manifest = (await client.get(f"/api/reader/chapters/{first}")).json()
    assert manifest["prefs"]["mode"] == "long_strip"


async def test_an_unknown_mode_is_refused(client, tmp_path):
    series_id, _ = await _three_archived_chapters(tmp_path)
    response = await client.put(
        f"/api/reader/series/{series_id}/prefs",
        json={"mode": "sideways", "scale": "fit_width", "background": "white"},
    )
    assert response.status_code == 422


async def test_prefs_for_an_unknown_series_are_404(client):
    response = await client.put(
        "/api/reader/series/999999/prefs",
        json={"mode": "long_strip", "scale": "fit_width", "background": "white"},
    )
    assert response.status_code == 404


async def test_defaults_change_what_an_uncustomised_series_gets(client, tmp_path):
    series_id, _ = await _three_archived_chapters(tmp_path)
    await client.put(
        "/api/reader/defaults",
        json={"mode": "long_strip", "scale": "fit_width", "background": "gray"},
    )
    prefs = (await client.get(f"/api/reader/series/{series_id}/prefs")).json()
    assert prefs["mode"] == "long_strip"
    assert prefs["custom"] is False


async def test_resume_opens_the_saved_position(client, tmp_path):
    series_id, (_, middle, _) = await _three_archived_chapters(tmp_path)
    await client.put(
        f"/api/reader/series/{series_id}/position", json={"chapter_id": middle, "page": 1}
    )
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).json() == {
        "chapter_id": middle,
        "page": 1,
    }


async def test_resume_without_a_position_opens_the_first_unread_chapter(client, tmp_path):
    series_id, (_, middle, _) = await _three_archived_chapters(tmp_path)
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into list_entry (provider, provider_media_id, series_id, title_romaji,"
                " synonyms, raw, status, user_progress_chapter)"
                " values ('local', :m, :s, 'Teto', '[]'::jsonb, '{}'::jsonb, 'reading', 1)"
            ),
            {"m": str(series_id), "s": series_id},
        )
        await session.commit()
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).json() == {
        "chapter_id": middle,
        "page": 0,
    }


async def test_resume_of_a_series_with_no_chapters_is_404(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).status_code == 404


async def test_series_detail_chapters_carry_their_id(client, tmp_path):
    series_id, ids = await _three_archived_chapters(tmp_path)
    detail = (await client.get(f"/api/series/{series_id}")).json()
    assert [chapter["id"] for chapter in detail["chapters"]] == ids
