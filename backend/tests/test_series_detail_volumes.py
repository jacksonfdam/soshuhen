"""Series detail says which volume is which, and whether its file can be opened."""

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
        await session.execute(text("truncate series, list_entry restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _exec(statement: str, params: dict | None = None):
    async with get_sessionmaker()() as session:
        result = await session.execute(text(statement), params or {})
        await session.commit()
        return result


async def _series() -> int:
    result = await _exec(
        "insert into series (canonical_title, slug, needs_review, meta, kind)"
        " values ('N', 'n', false, '{}'::jsonb, 'prose') returning id"
    )
    return int(result.scalar_one())


async def _volume(series_id: int, number: int, edition: str, **columns) -> int:
    result = await _exec(
        "insert into volume (series_id, number, source_volume_id, status, state, edition,"
        " file_path, first_part, last_part)"
        " values (:s, :n, :v, 'owned', 'downloaded', :e, :f, :fp, :lp) returning id",
        {
            "s": series_id,
            "n": number,
            "v": f"import:{number}{edition}",
            "e": edition,
            "f": columns.get("file_path"),
            "fp": columns.get("first_part"),
            "lp": columns.get("last_part"),
        },
    )
    return int(result.scalar_one())


async def _detail(client, series_id: int) -> dict:
    return (await client.get(f"/api/series/{series_id}")).json()


async def test_a_volume_on_disk_carries_its_id_file_and_readable(client, tmp_path):
    path = tmp_path / "manga" / "n" / "n - Vol.0001.epub"
    path.parent.mkdir()
    path.write_bytes(b"PK")
    series_id = await _series()
    volume_id = await _volume(series_id, 1, "light", file_path=str(path))
    [volume] = (await _detail(client, series_id))["volumes"]
    assert volume["id"] == volume_id
    assert volume["file_path"] == str(path)
    assert volume["readable"] is True
    assert volume["first_part"] is None and volume["last_part"] is None


async def test_a_missing_file_is_not_readable(client, tmp_path):
    series_id = await _series()
    await _volume(series_id, 1, "light", file_path=str(tmp_path / "manga" / "gone.epub"))
    [volume] = (await _detail(client, series_id))["volumes"]
    assert volume["readable"] is False


async def test_a_file_outside_the_library_is_not_readable(client, tmp_path):
    outside = tmp_path / "elsewhere.epub"
    outside.write_bytes(b"PK")
    series_id = await _series()
    await _volume(series_id, 1, "light", file_path=str(outside))
    [volume] = (await _detail(client, series_id))["volumes"]
    assert volume["readable"] is False


async def test_a_web_volume_exposes_its_chapter_range(client):
    series_id = await _series()
    await _volume(series_id, 15, "web", first_part=213, last_part=231)
    [volume] = (await _detail(client, series_id))["volumes"]
    assert volume["first_part"] == 213.0
    assert volume["last_part"] == 231.0
    assert volume["readable"] is False


async def test_a_chapter_says_whether_it_can_be_opened(client, tmp_path):
    path = tmp_path / "manga" / "n - Ch.0001.epub"
    path.write_bytes(b"PK")
    series_id = await _series()
    await _exec(
        "insert into chapter (series_id, number, state, file_path) values"
        " (:s, 1, 'downloaded', :f), (:s, 2, 'known', null)",
        {"s": series_id, "f": str(path)},
    )
    chapters = (await _detail(client, series_id))["chapters"]
    assert [c["readable"] for c in chapters] == [True, False]
