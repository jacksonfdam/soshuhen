"""Server copies leave only when the device holds the very same file."""

from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext
from app.handlers.offload import handle, served_etag
from app.queue import repo


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _series(session, slug="frieren", kind="comic") -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values (:t, :s, false, '{}'::jsonb, :k) returning id"
            ),
            {"t": slug.title(), "s": slug, "k": kind},
        )
    ).scalar_one()


def _file(root: Path, slug: str, name: str, body: bytes = b"PK-archive") -> Path:
    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(body)
    return path


async def _chapter(session, series_id, number, path, state="downloaded") -> int:
    return (
        await session.execute(
            text(
                "insert into chapter (series_id, number, state, file_path)"
                " values (:s, :n, :st, cast(:f as text)) returning id"
            ),
            {"s": series_id, "n": number, "st": state, "f": str(path) if path else None},
        )
    ).scalar_one()


async def _volume(session, series_id, number, path) -> int:
    return (
        await session.execute(
            text(
                "insert into volume (series_id, number, source_volume_id, status, state, file_path)"
                " values (:s, :n, :src, 'owned', 'downloaded', :f) returning id"
            ),
            {"s": series_id, "n": number, "src": f"V{number}", "f": str(path)},
        )
    ).scalar_one()


def _item(row_id: int, path: Path) -> dict:
    return {"id": row_id, "etag": served_etag(path), "size": path.stat().st_size}


async def _run(session, *, chapters=(), volumes=()):
    await repo.enqueue(
        session, JobType.OFFLOAD, {"chapters": list(chapters), "volumes": list(volumes)}
    )
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.OFFLOAD)])
    await session.commit()
    await handle(JobContext(session=session, job=job))
    await session.commit()


async def _chapter_row(session, chapter_id):
    return (
        await session.execute(
            text("select state, file_path from chapter where id = :id"), {"id": chapter_id}
        )
    ).one()


async def test_offload_deletes_matching_chapter_and_marks_it(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        await _run(session, chapters=[_item(chapter_id, path)])
        row = await _chapter_row(session, chapter_id)
    assert not path.exists()
    assert row.state == "offloaded"
    assert row.file_path is None


async def test_offload_skips_rebuilt_file(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        stale = _item(chapter_id, path)
        path.write_bytes(b"PK-rebuilt-with-more-pages")
        await _run(session, chapters=[stale])
        row = await _chapter_row(session, chapter_id)
    assert path.exists()
    assert row.state == "downloaded"


async def test_offload_skips_size_mismatch(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        item = _item(chapter_id, path) | {"size": 1}
        await _run(session, chapters=[item])
        row = await _chapter_row(session, chapter_id)
    assert path.exists()
    assert row.state == "downloaded"


async def test_offload_skips_row_not_downloaded(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path, state="queued")
        await session.commit()
        await _run(session, chapters=[_item(chapter_id, path)])
        row = await _chapter_row(session, chapter_id)
    assert path.exists()
    assert row.state == "queued"


async def test_offload_refuses_path_outside_library(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.cbz"
    outside.write_bytes(b"not ours")
    try:
        async with get_sessionmaker()() as session:
            series_id = await _series(session)
            chapter_id = await _chapter(session, series_id, 1, outside)
            await session.commit()
            await _run(session, chapters=[_item(chapter_id, outside)])
            row = await _chapter_row(session, chapter_id)
        assert outside.exists()
        assert row.state == "downloaded"
    finally:
        outside.unlink(missing_ok=True)


async def test_offload_marks_missing_file_offloaded(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        item = _item(chapter_id, path)
        path.unlink()
        await _run(session, chapters=[item])
        row = await _chapter_row(session, chapter_id)
    assert row.state == "offloaded"
    assert row.file_path is None


async def test_offload_deletes_volume(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "apothecary", "prose")
        path = _file(tmp_path, "apothecary", "apothecary - Vol.0001.epub")
        volume_id = await _volume(session, series_id, 1, path)
        await session.commit()
        await _run(session, volumes=[_item(volume_id, path)])
        row = (
            await session.execute(
                text("select state, file_path from volume where id = :id"), {"id": volume_id}
            )
        ).one()
    assert not path.exists()
    assert row.state == "offloaded"
    assert row.file_path is None


async def test_offload_removes_empty_series_folder(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        await _run(session, chapters=[_item(chapter_id, path)])
    assert not (tmp_path / "frieren").exists()
    assert tmp_path.exists()


async def test_offload_keeps_folder_with_other_files(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        _file(tmp_path, "frieren", "Frieren Ch.2.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        await _run(session, chapters=[_item(chapter_id, path)])
    assert (tmp_path / "frieren" / "Frieren Ch.2.cbz").exists()


async def test_offload_twice_is_harmless(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path)
        await session.commit()
        item = _item(chapter_id, path)
        await _run(session, chapters=[item])
        await _run(session, chapters=[item])
        row = await _chapter_row(session, chapter_id)
    assert row.state == "offloaded"


async def test_offload_queues_one_komga_scan_per_series(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        one = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        two = _file(tmp_path, "frieren", "Frieren Ch.2.cbz", b"PK-two")
        first = await _chapter(session, series_id, 1, one)
        second = await _chapter(session, series_id, 2, two)
        await session.commit()
        await _run(session, chapters=[_item(first, one), _item(second, two)])
        types = (
            await session.execute(text("select type from job where state = 'pending'"))
        ).scalars().all()
    assert types == ["komga_scan"]


async def test_offload_skips_unknown_id(tmp_path):
    async with get_sessionmaker()() as session:
        await _run(session, chapters=[{"id": 999, "etag": '"x"', "size": 1}])
        types = (
            await session.execute(text("select type from job where state = 'pending'"))
        ).scalars().all()
    assert types == []


async def test_offload_finishes_a_row_the_api_marked(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path, state="offloaded")
        await session.commit()
        await _run(session, chapters=[_item(chapter_id, path)])
        row = await _chapter_row(session, chapter_id)
    assert not path.exists()
    assert row.state == "offloaded" and row.file_path is None


async def test_a_rebuilt_file_returns_a_marked_row_to_downloaded(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        path = _file(tmp_path, "frieren", "Frieren Ch.1.cbz")
        chapter_id = await _chapter(session, series_id, 1, path, state="offloaded")
        await session.commit()
        stale = _item(chapter_id, path)
        path.write_bytes(b"PK-rebuilt-with-more-pages")
        await _run(session, chapters=[stale])
        row = await _chapter_row(session, chapter_id)
    assert path.exists()
    assert row.state == "downloaded" and row.file_path == str(path)
