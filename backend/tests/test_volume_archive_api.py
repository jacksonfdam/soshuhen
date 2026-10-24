"""A light novel volume's EPUB as one file, for the app to copy and read offline."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    (tmp_path / "manga").mkdir()
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "manga"))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job, series, list_entry restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _volume(file_path: str | None) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('Tsuki', 'tsuki', false, '{}'::jsonb, 'prose') returning id"
                )
            )
        ).scalar_one()
        volume_id = (
            await session.execute(
                text(
                    "insert into volume (series_id, number, edition, source_volume_id, status,"
                    " state, file_path) values (:s, :n, 'light', 'import:light:1', 'owned',"
                    " 'downloaded', :path) returning id"
                ),
                {"s": series_id, "n": Decimal("1"), "path": file_path},
            )
        ).scalar_one()
        await session.commit()
    return int(volume_id)


def _epub(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PK-a-whole-volume")
    return path


async def test_serves_the_volume_file(client, tmp_path):
    path = _epub(tmp_path / "manga" / "tsuki" / "tsuki - Vol.0001.epub")
    volume_id = await _volume(str(path))
    response = await client.get(f"/api/volumes/{volume_id}/archive")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
    assert response.headers["etag"]
    assert response.content == path.read_bytes()


async def test_a_range_request_resumes(client, tmp_path):
    path = _epub(tmp_path / "manga" / "tsuki" / "v1.epub")
    volume_id = await _volume(str(path))
    response = await client.get(
        f"/api/volumes/{volume_id}/archive", headers={"Range": "bytes=3-"}
    )
    assert response.status_code == 206
    assert response.content == path.read_bytes()[3:]
    assert response.headers["content-range"].endswith(f"/{path.stat().st_size}")


async def test_a_volume_without_a_file_is_404(client):
    volume_id = await _volume(None)
    assert (await client.get(f"/api/volumes/{volume_id}/archive")).status_code == 404


async def test_a_deleted_file_is_404(client, tmp_path):
    path = _epub(tmp_path / "manga" / "tsuki" / "v1.epub")
    volume_id = await _volume(str(path))
    path.unlink()
    assert (await client.get(f"/api/volumes/{volume_id}/archive")).status_code == 404


async def test_a_file_outside_the_library_is_404(client, tmp_path):
    path = _epub(tmp_path / "elsewhere" / "v1.epub")
    volume_id = await _volume(str(path))
    assert (await client.get(f"/api/volumes/{volume_id}/archive")).status_code == 404


async def test_an_unknown_volume_is_404(client):
    assert (await client.get("/api/volumes/999999/archive")).status_code == 404
