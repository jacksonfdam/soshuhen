"""Offloading and downloading back, as the API exposes them."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.handlers.offload import served_etag


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _exec(statement: str, params: dict | None = None):
    async with get_sessionmaker()() as session:
        result = await session.execute(text(statement), params or {})
        await session.commit()
        return result


async def _series(kind="comic") -> int:
    return (
        await _exec(
            "insert into series (canonical_title, slug, needs_review, meta, kind)"
            " values ('A', 'a', false, '{}'::jsonb, :k) returning id",
            {"k": kind},
        )
    ).scalar_one()


async def _chapter(series_id, number, state, file_path=None) -> int:
    return (
        await _exec(
            "insert into chapter (series_id, number, state, file_path)"
            " values (:s, :n, :st, cast(:f as text)) returning id",
            {"s": series_id, "n": number, "st": state, "f": file_path},
        )
    ).scalar_one()


async def _volume(series_id, number, state) -> int:
    return (
        await _exec(
            "insert into volume (series_id, number, source_volume_id, status, state)"
            " values (:s, :n, :src, 'owned', :st) returning id",
            {"s": series_id, "n": number, "src": f"V{number}", "st": state},
        )
    ).scalar_one()


async def _jobs() -> list[str]:
    return list((await _exec("select type from job order by id")).scalars().all())


def _file(root: Path) -> Path:
    path = root / "a" / "a Ch.1.cbz"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PK-archive")
    return path


async def test_offload_endpoint_queues_one_job_and_reports_skips(client, tmp_path):
    series_id = await _series()
    path = _file(tmp_path)
    ok = await _chapter(series_id, 1, "downloaded", str(path))
    queued = await _chapter(series_id, 2, "queued")
    item = {"id": ok, "etag": served_etag(path), "size": path.stat().st_size}
    r = await client.post(
        "/api/offload", json={"chapters": [item, {"id": queued, "etag": '"x"', "size": 1}]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["queued"] == 1
    assert body["skipped"] == [{"id": queued, "kind": "chapter", "reason": "not downloaded"}]
    assert await _jobs() == ["offload"]


async def test_offload_endpoint_never_touches_files(client, tmp_path):
    series_id = await _series()
    path = _file(tmp_path)
    ok = await _chapter(series_id, 1, "downloaded", str(path))
    item = {"id": ok, "etag": served_etag(path), "size": path.stat().st_size}
    await client.post("/api/offload", json={"chapters": [item]})
    assert path.exists()


async def test_offload_endpoint_rejects_empty_body(client):
    r = await client.post("/api/offload", json={"chapters": [], "volumes": []})
    assert r.status_code == 422


async def test_offload_endpoint_nothing_acceptable_queues_nothing(client):
    r = await client.post("/api/offload", json={"chapters": [{"id": 9, "etag": '"x"', "size": 1}]})
    assert r.json() == {"queued": 0, "skipped": [{"id": 9, "kind": "chapter", "reason": "unknown"}]}
    assert await _jobs() == []


async def test_download_range_picks_offloaded_chapters(client):
    series_id = await _series()
    await _chapter(series_id, 1, "offloaded")
    r = await client.post(f"/api/series/{series_id}/download", json={})
    assert r.json()["queued"] >= 1
    state = (await _exec("select state from chapter")).scalar_one()
    assert state == "queued"


async def test_volume_download_queues_once(client):
    series_id = await _series("prose")
    volume_id = await _volume(series_id, 1, "offloaded")
    first = await client.post(f"/api/volumes/{volume_id}/download")
    second = await client.post(f"/api/volumes/{volume_id}/download")
    assert first.json() == {"queued": True}
    assert second.status_code == 409  # now queued, not offloaded
    assert await _jobs() == ["volume_download"]
    state = (await _exec("select state from volume")).scalar_one()
    assert state == "queued"


async def test_volume_download_refuses_downloaded_and_unknown(client):
    series_id = await _series("prose")
    volume_id = await _volume(series_id, 1, "downloaded")
    assert (await client.post(f"/api/volumes/{volume_id}/download")).status_code == 409
    assert (await client.post("/api/volumes/999/download")).status_code == 404


async def test_series_detail_reports_offloaded(client):
    series_id = await _series("prose")
    await _chapter(series_id, 1, "offloaded")
    await _chapter(series_id, 2, "downloaded", "/nowhere")
    await _volume(series_id, 1, "offloaded")
    body = (await client.get(f"/api/series/{series_id}")).json()
    assert body["series"]["offloaded"] == 2
    listed = (await client.get("/api/series")).json()
    assert listed[0]["offloaded"] == 2


async def test_fully_offloaded_series_counts_as_holding_files():
    from app.api.library_content import HOLDS_FILES

    series_id = await _series()
    await _chapter(series_id, 1, "offloaded")
    held = (
        await _exec(f"select {HOLDS_FILES} from series s where s.id = :id", {"id": series_id})
    ).scalar_one()
    assert held is True
