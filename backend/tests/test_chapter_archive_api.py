"""A chapter's whole archive, for a client that keeps its own copy."""

import zipfile
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


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


async def _chapter(file_path: str | None, *, kind: str = "comic") -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('Teto', 'teto', false, '{}'::jsonb, :kind) returning id"
                ),
                {"kind": kind},
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, title, state, file_path)"
                    " values (:s, :n, 'Chapter 1', 'downloaded', :path) returning id"
                ),
                {"s": series_id, "n": Decimal("1"), "path": file_path},
            )
        ).scalar_one()
        await session.commit()
    return int(chapter_id)


def _cbz(path, pages: list[bytes]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for index, data in enumerate(pages, start=1):
            zf.writestr(f"{index:03d}.jpg", data)
    return path


async def test_serves_the_whole_archive(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG, JPEG + b"2"])
    chapter_id = await _chapter(str(path))
    response = await client.get(f"/api/chapters/{chapter_id}/archive")
    assert response.status_code == 200
    assert response.content == path.read_bytes()
    assert response.headers["content-length"] == str(path.stat().st_size)
    assert response.headers["etag"]
    assert 'filename="c1.cbz"' in response.headers["content-disposition"]


async def test_a_range_request_resumes(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG, JPEG + b"2"])
    chapter_id = await _chapter(str(path))
    response = await client.get(
        f"/api/chapters/{chapter_id}/archive", headers={"Range": "bytes=10-"}
    )
    assert response.status_code == 206
    assert response.content == path.read_bytes()[10:]


async def test_a_chapter_without_a_file_is_404(client):
    chapter_id = await _chapter(None)
    assert (await client.get(f"/api/chapters/{chapter_id}/archive")).status_code == 404


async def test_a_deleted_file_is_404(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG])
    chapter_id = await _chapter(str(path))
    path.unlink()
    assert (await client.get(f"/api/chapters/{chapter_id}/archive")).status_code == 404


async def test_a_file_outside_the_library_is_404(client, tmp_path):
    path = _cbz(tmp_path / "elsewhere" / "x.cbz", [JPEG])
    chapter_id = await _chapter(str(path))
    assert (await client.get(f"/api/chapters/{chapter_id}/archive")).status_code == 404


async def test_an_unknown_chapter_is_404(client):
    assert (await client.get("/api/chapters/999999/archive")).status_code == 404


async def test_a_prose_chapter_is_served_as_epub(client, tmp_path):
    path = tmp_path / "manga" / "teto" / "c1.epub"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"PK-epub-bytes")
    chapter_id = await _chapter(str(path), kind="prose")
    response = await client.get(f"/api/chapters/{chapter_id}/archive")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
    assert response.content == path.read_bytes()


async def test_a_prose_chapter_resumes_with_range(client, tmp_path):
    path = tmp_path / "manga" / "teto" / "c1.epub"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"PK-epub-bytes")
    chapter_id = await _chapter(str(path), kind="prose")
    response = await client.get(
        f"/api/chapters/{chapter_id}/archive", headers={"Range": "bytes=2-"}
    )
    assert response.status_code == 206
    assert response.content == b"-epub-bytes"


async def test_a_comic_archive_is_still_a_cbz(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG])
    chapter_id = await _chapter(str(path))
    response = await client.get(f"/api/chapters/{chapter_id}/archive")
    assert response.headers["content-type"] == "application/vnd.comicbook+zip"


async def test_no_database_connection_is_held_while_the_file_streams(client, tmp_path, monkeypatch):
    """A copy over weak Wi-Fi can take minutes; the pool must not lose a connection to it."""
    from fastapi.responses import FileResponse

    from app.api import routes_chapters
    from app.db import get_engine

    seen: list[int] = []

    class Watched(FileResponse):
        async def __call__(self, scope, receive, send):
            seen.append(get_engine().pool.checkedout())
            await super().__call__(scope, receive, send)

    monkeypatch.setattr(routes_chapters, "FileResponse", Watched)
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG])
    chapter_id = await _chapter(str(path))
    assert (await client.get(f"/api/chapters/{chapter_id}/archive")).status_code == 200
    assert seen == [0]
