"""The novel reader: a prose EPUB already in the library, served to the web reader."""

from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.downloader.epub import EpubChapter, write_epub

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
def library(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "manga"
    root.mkdir()
    monkeypatch.setenv("LIBRARY_PATH", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate series, list_entry, setting restart identity cascade")
        )
        await session.commit()


async def _exec(statement: str, params: dict | None = None):
    async with get_sessionmaker()() as session:
        result = await session.execute(text(statement), params or {})
        await session.commit()
        return result


async def _series(kind: str = "prose") -> int:
    result = await _exec(
        "insert into series (canonical_title, slug, needs_review, meta, kind)"
        " values ('Moon', 'moon', false, '{}'::jsonb, :k) returning id",
        {"k": kind},
    )
    return int(result.scalar_one())


async def _epub(library: Path, name: str, body: str = "<p>Once.</p>{{img:0}}") -> Path:
    path = library / "moon" / name
    await write_epub(
        EpubChapter(series="Moon", number=Decimal(1), identifier=name, title="Volume",
                    body=body, images=[PNG], cover=None),
        path,
    )
    return path


async def _volume(series_id: int, number: int, path: Path | None, edition: str = "light",
                  book: str | None = None) -> int:
    result = await _exec(
        "insert into volume (series_id, number, source_volume_id, status, state, edition,"
        " file_path, title, komga_book_id)"
        " values (:s, :n, :v, 'owned', 'downloaded', :e, :f, :t, :b) returning id",
        {"s": series_id, "n": number, "v": f"import:{number}{edition}", "e": edition,
         "f": str(path) if path else None, "t": f"Volume {number}", "b": book},
    )
    return int(result.scalar_one())


async def test_a_light_volume_opens_with_its_sections_and_neighbours(client, library):
    series_id = await _series()
    first = await _volume(series_id, 1, await _epub(library, "v1.epub"))
    await _volume(series_id, 2, library / "moon" / "missing.epub")
    third = await _volume(series_id, 3, await _epub(library, "v3.epub"))

    body = (await client.get(f"/api/reader/prose/volume/{first}")).json()
    assert body["kind"] == "volume"
    assert body["series"] == {"id": series_id, "title": "Moon"}
    assert body["edition"] == "light"
    assert [s["index"] for s in body["sections"]] == [0]
    assert body["previous"] is None
    # Volume 2's file is gone, so "next" skips to the next one that opens.
    assert body["next"] == {"kind": "volume", "id": third, "number": 3.0, "title": "Volume 3"}
    assert body["position"] is None
    assert body["prefs"] == {"font_size": 3, "theme": "dark"}


async def test_a_saved_position_comes_back_with_the_manifest(client, library):
    series_id = await _series()
    volume_id = await _volume(series_id, 1, await _epub(library, "v1.epub"))
    await client.put(
        f"/api/reader/series/{series_id}/position",
        json={"volume_id": volume_id, "page": 0, "fraction": 0.4},
    )
    body = (await client.get(f"/api/reader/prose/volume/{volume_id}")).json()
    assert body["position"] == {"section": 0, "fraction": pytest.approx(0.4)}


async def test_a_section_is_sanitised_html_with_images_through_the_api(client, library):
    series_id = await _series()
    volume_id = await _volume(series_id, 1, await _epub(library, "v1.epub"))
    body = (await client.get(f"/api/reader/prose/volume/{volume_id}/sections/0")).json()
    assert "<p>Once.</p>" in body["html"]
    src = f"/api/reader/prose/volume/{volume_id}/resources/OEBPS/images/001.png"
    assert f'<img src="{src}"' in body["html"]
    image = await client.get(src)
    assert image.status_code == 200
    assert image.content == PNG
    assert image.headers["content-type"] == "image/png"


async def test_resources_outside_the_package_are_not_served(client, library):
    series_id = await _series()
    volume_id = await _volume(series_id, 1, await _epub(library, "v1.epub"))
    for href in ("OEBPS/content.opf", "META-INF/container.xml", "OEBPS/../mimetype"):
        response = await client.get(f"/api/reader/prose/volume/{volume_id}/resources/{href}")
        assert response.status_code == 404


async def test_a_prose_chapter_opens_in_the_novel_reader(client, library):
    series_id = await _series()
    path = await _epub(library, "c1.epub")
    chapter_id = (
        await _exec(
            "insert into chapter (series_id, number, state, file_path)"
            " values (:s, 1, 'downloaded', :f) returning id",
            {"s": series_id, "f": str(path)},
        )
    ).scalar_one()
    body = (await client.get(f"/api/reader/prose/chapter/{chapter_id}")).json()
    assert body["kind"] == "chapter"
    assert body["edition"] is None
    comic = await client.get(f"/api/reader/chapters/{chapter_id}")
    assert comic.status_code == 409
    assert "novel reader" in comic.json()["detail"]


async def test_a_web_volume_is_read_through_its_chapters(client, library):
    series_id = await _series()
    volume_id = await _volume(series_id, 1, None, edition="web")
    assert (await client.get(f"/api/reader/prose/volume/{volume_id}")).status_code == 409


async def test_a_comic_chapter_is_not_a_novel(client, library):
    series_id = await _series(kind="comic")
    chapter_id = (
        await _exec(
            "insert into chapter (series_id, number, state) values (:s, 1, 'known') returning id",
            {"s": series_id},
        )
    ).scalar_one()
    assert (await client.get(f"/api/reader/prose/chapter/{chapter_id}")).status_code == 409


async def test_a_volume_without_its_file_is_not_found(client, library):
    series_id = await _series()
    volume_id = await _volume(series_id, 1, library / "moon" / "gone.epub")
    assert (await client.get(f"/api/reader/prose/volume/{volume_id}")).status_code == 404
    assert (await client.get("/api/reader/prose/volume/999")).status_code == 404


async def test_a_broken_epub_is_unprocessable(client, library):
    series_id = await _series()
    path = library / "moon" / "broken.epub"
    path.parent.mkdir()
    path.write_bytes(b"not a zip")
    volume_id = await _volume(series_id, 1, path)
    assert (await client.get(f"/api/reader/prose/volume/{volume_id}")).status_code == 422


async def test_prefs_default_then_saved(client):
    assert (await client.get("/api/reader/prose/prefs")).json() == {
        "font_size": 3, "theme": "dark"
    }
    saved = await client.put("/api/reader/prose/prefs", json={"font_size": 5, "theme": "sepia"})
    assert saved.json() == {"font_size": 5, "theme": "sepia"}
    assert (await client.get("/api/reader/prose/prefs")).json()["theme"] == "sepia"
    bad = await client.put("/api/reader/prose/prefs", json={"font_size": 9, "theme": "sepia"})
    assert bad.status_code == 422


async def test_resume_opens_the_saved_place_else_the_first_unread_volume(client, library):
    series_id = await _series()
    first = await _volume(series_id, 1, await _epub(library, "v1.epub"))
    second = await _volume(series_id, 2, await _epub(library, "v2.epub"))
    await _exec(
        "insert into list_entry (provider, provider_media_id, series_id, title_romaji, synonyms,"
        " raw, status, user_progress_chapter, user_progress_volume)"
        " values ('mal', '1', :s, 'Moon', '[]'::jsonb, '{}'::jsonb, 'reading', 2, 1)",
        {"s": series_id},
    )
    resume = f"/api/reader/prose/series/{series_id}/resume"
    assert (await client.get(resume)).json() == {
        "kind": "volume", "id": second, "section": 0, "fraction": 0.0
    }
    await client.put(
        f"/api/reader/series/{series_id}/position",
        json={"volume_id": first, "page": 0, "fraction": 0.5},
    )
    assert (await client.get(resume)).json() == {
        "kind": "volume", "id": first, "section": 0, "fraction": 0.5
    }


async def test_resume_with_nothing_readable_is_not_found(client, library):
    series_id = await _series()
    await _volume(series_id, 1, None, edition="web")
    resume = f"/api/reader/prose/series/{series_id}/resume"
    assert (await client.get(resume)).status_code == 404
