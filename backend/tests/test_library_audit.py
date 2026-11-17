"""A downloaded row whose archive is gone from disk goes back to needing a download."""

from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.cron import CRON_JOBS
from app.db import get_sessionmaker
from app.enums import JobType, Lane, lane_of
from app.handlers.library_audit import forget_missing
from app.worker.main import ENQUEUERS


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _series(session, slug: str) -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values (:t, :s, false, '{}'::jsonb, 'comic') returning id"
            ),
            {"t": slug.title(), "s": slug},
        )
    ).scalar_one()


def _file(root: Path, slug: str, name: str) -> Path:
    (root / slug).mkdir(parents=True, exist_ok=True)
    path = root / slug / name
    path.write_bytes(b"PK-archive")
    return path


async def _chapter(session, series_id, number, path, state="downloaded") -> int:
    return (
        await session.execute(
            text(
                "insert into chapter (series_id, number, state, file_path, komga_book_id)"
                " values (:s, :n, :st, cast(:f as text), 'book') returning id"
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


async def _chapter_row(session, chapter_id):
    return (
        await session.execute(
            text("select state, file_path, komga_book_id from chapter where id = :id"),
            {"id": chapter_id},
        )
    ).one()


async def test_a_chapter_whose_file_is_gone_needs_downloading_again(tmp_path):
    async with get_sessionmaker()() as session:
        kept = await _series(session, "frieren")
        gone = await _series(session, "gin-tama")
        present = await _chapter(session, kept, 1, _file(tmp_path, "frieren", "c1.cbz"))
        # The whole series folder went, as Gin Tama's did on a real server.
        missing = await _chapter(session, gone, 1, tmp_path / "gin-tama" / "c1.cbz")
        await session.commit()

        result = await forget_missing(session, tmp_path)
        await session.commit()

        assert result == (1, 0)
        assert (await _chapter_row(session, present)).state == "downloaded"
        row = await _chapter_row(session, missing)
        assert (row.state, row.file_path, row.komga_book_id) == ("known", None, None)


async def test_a_volume_whose_file_is_gone_needs_downloading_again(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "ascendance")
        _file(tmp_path, "ascendance", "v1.epub")
        volume_id = await _volume(session, series_id, 2, tmp_path / "ascendance" / "v2.epub")
        await session.commit()

        assert await forget_missing(session, tmp_path) == (0, 1)
        await session.commit()
        row = (
            await session.execute(
                text("select state, file_path from volume where id = :id"), {"id": volume_id}
            )
        ).one()
        assert (row.state, row.file_path) == ("known", None)


async def test_offloaded_and_other_states_are_left_alone(tmp_path):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "frieren")
        _file(tmp_path, "frieren", "c1.cbz")
        offloaded = await _chapter(session, series_id, 2, tmp_path / "frieren" / "c2.cbz", "offloaded")
        await session.commit()

        assert await forget_missing(session, tmp_path) == (0, 0)
        assert (await _chapter_row(session, offloaded)).state == "offloaded"


async def test_an_empty_library_resets_nothing(tmp_path):
    # An unmounted volume shows up as an empty folder. Taking that at its word
    # would mark the whole library as needing a download.
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "frieren")
        chapter_id = await _chapter(session, series_id, 1, tmp_path / "frieren" / "c1.cbz")
        await session.commit()

        assert await forget_missing(session, tmp_path) is None
        assert (await _chapter_row(session, chapter_id)).state == "downloaded"


def test_the_audit_is_scheduled_and_runs_where_it_can_see_the_library():
    assert "library_audit" in {job.id for job in CRON_JOBS}
    assert "library_audit" in ENQUEUERS
    assert lane_of(JobType.LIBRARY_AUDIT) == Lane.FETCH
