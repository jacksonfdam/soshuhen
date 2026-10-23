"""Dropping PDFs on a series: the preview, and the confirmation that queues the write.

api never writes the library. It keeps the upload where worker-download can
read it and answers with the plan; nothing lands in /manga until the user has
seen that plan and pressed Import.
"""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from tests.pdf_fixture import make_pdf

WEB_15 = ("WN - Tsukimichi - Volume 15.pdf", [("Chapter 213 A", ["One."]), ("Chapter 214 B", ["Two."])])
LIGHT_19 = ("LN - Tsukimichi - Volume 19.pdf", [("Chapter 1", ["One."]), ("Chapter 2", ["Two."])])


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
            text("truncate job, series, list_entry, chapter, volume restart identity cascade")
        )
        await session.commit()
    yield
    get_settings.cache_clear()


async def a_series(kind: str = "prose") -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('Tsukimichi', 'tsukimichi', false, '{}'::jsonb, :kind) returning id"
                ),
                {"kind": kind},
            )
        ).scalar_one()
        await session.commit()
    return int(series_id)


def upload(*books):
    return [("files", (name, make_pdf(entries), "application/pdf")) for name, entries in books]


async def preview(client, series_id: int, *books):
    return await client.post(f"/api/series/{series_id}/import", files=upload(*books))


async def test_preview_returns_a_plan_and_writes_nothing(client, tmp_path):
    series_id = await a_series()

    response = await preview(client, series_id, WEB_15, LIGHT_19)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token"]
    assert [(f["edition"], f["status"]) for f in body["files"]] == [("web", "ready"), ("light", "ready")]
    assert body["files"][0]["chapters"] == ["213", "214"]
    assert list((tmp_path / "manga").iterdir()) == []
    async with get_sessionmaker()() as session:
        assert (await session.execute(text("select count(*) from chapter"))).scalar_one() == 0
        assert (await session.execute(text("select count(*) from job"))).scalar_one() == 0


async def test_preview_stages_the_upload_on_the_shared_cache(client, tmp_path):
    series_id = await a_series()

    token = (await preview(client, series_id, WEB_15)).json()["token"]

    staged = tmp_path / "cache" / "imports" / token
    assert (staged / "manifest.json").exists()
    assert len(list(staged.glob("*.pdf"))) == 1


async def test_preview_on_a_comic_series_is_409(client):
    series_id = await a_series(kind="comic")

    response = await preview(client, series_id, WEB_15)

    assert response.status_code == 409


async def test_preview_on_a_missing_series_is_404(client):
    response = await preview(client, 999, WEB_15)

    assert response.status_code == 404


async def test_non_pdf_is_415(client):
    series_id = await a_series()

    response = await client.post(
        f"/api/series/{series_id}/import", files=[("files", ("notes.txt", b"hello", "text/plain"))]
    )

    assert response.status_code == 415


async def test_existing_chapters_show_as_exists(client):
    series_id = await a_series()
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into chapter (series_id, number, title, state)"
                " values (:s, :n, 'x', 'downloaded')"
            ),
            {"s": series_id, "n": Decimal(213)},
        )
        await session.commit()

    response = await preview(client, series_id, WEB_15)

    assert response.json()["files"][0]["status"] == "exists"


async def test_a_light_volume_after_known_web_chapters_reads_as_light(client):
    # No LN/WN prefix: the restart at chapter 1 after 295 known chapters is what tells.
    series_id = await a_series()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("insert into chapter (series_id, number, title, state) values (:s, 295, 'x', 'downloaded')"),
            {"s": series_id},
        )
        await session.commit()

    response = await preview(client, series_id, ("Tsukimichi - Volume 19.pdf", LIGHT_19[1]))

    assert response.json()["files"][0]["edition"] == "light"


async def confirm(client, series_id: int, token: str, files: dict | None = None):
    return await client.post(f"/api/series/{series_id}/import/{token}", json={"files": files or {}})


async def test_confirm_enqueues_one_import_job_on_the_download_lane(client):
    series_id = await a_series()
    token = (await preview(client, series_id, WEB_15, LIGHT_19)).json()["token"]

    response = await confirm(client, series_id, token)

    assert response.status_code == 202, response.text
    async with get_sessionmaker()() as session:
        jobs = (await session.execute(text("select type, payload from job"))).all()
    assert [job.type for job in jobs] == ["import_files"]
    assert jobs[0].payload["token"] == token
    assert jobs[0].payload["series_id"] == series_id


async def test_confirming_twice_queues_one_job(client):
    series_id = await a_series()
    token = (await preview(client, series_id, WEB_15)).json()["token"]

    await confirm(client, series_id, token)
    await confirm(client, series_id, token)

    async with get_sessionmaker()() as session:
        assert (await session.execute(text("select count(*) from job"))).scalar_one() == 1


async def test_confirm_applies_overrides_to_the_plan(client):
    series_id = await a_series()
    body = (await preview(client, series_id, ("odd.pdf", WEB_15[1]))).json()
    sha = body["files"][0]["sha256"]

    response = await confirm(
        client, series_id, body["token"], {sha: {"volume": "20", "edition": "light", "replace": False}}
    )

    assert response.json()["files"][0]["edition"] == "light"
    assert response.json()["files"][0]["volume"] == "20"


async def test_confirm_after_staging_vanished_is_410(client):
    series_id = await a_series()

    response = await confirm(client, series_id, "gone-token")

    assert response.status_code == 410


async def test_a_token_that_walks_out_of_staging_is_410(client):
    series_id = await a_series()

    response = await client.post(f"/api/series/{series_id}/import/..", json={"files": {}})

    assert response.status_code in (404, 405, 410)


async def test_confirm_with_nothing_ready_is_409(client):
    series_id = await a_series()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("insert into chapter (series_id, number, title, state) values (:s, 213, 'x', 'downloaded')"),
            {"s": series_id},
        )
        await session.commit()
    token = (await preview(client, series_id, WEB_15)).json()["token"]

    response = await confirm(client, series_id, token)

    assert response.status_code == 409
