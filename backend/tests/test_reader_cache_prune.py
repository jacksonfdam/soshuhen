"""A chapter opened and left half read must not hold its cache forever."""

import os
import time

from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers import reader_cache
from app.reader import cache

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


async def _chapter(state: str) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', :slug, false, '{}'::jsonb) returning id"
                ),
                {"slug": f"s-prune-{state}-{time.time_ns()}"},
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state)"
                    " values (:s, 1, :st) returning id"
                ),
                {"s": series_id, "st": state},
            )
        ).scalar_one()
        await session.commit()
    return int(chapter_id)


def _age(root, chapter_id, days):
    old = time.time() - days * 86400
    directory = root / str(chapter_id)
    for path in [*directory.iterdir(), directory]:
        os.utime(path, (old, old))


async def _state(chapter_id: int) -> str:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text("select state from chapter where id = :id"), {"id": chapter_id}
            )
        ).scalar_one()


async def test_an_old_cache_is_removed_and_its_chapter_is_known_again(tmp_path):
    stale = await _chapter("streaming")
    fresh = await _chapter("streaming")
    cache.write_page(tmp_path, stale, 0, JPEG)
    cache.write_page(tmp_path, fresh, 0, JPEG)
    _age(tmp_path, stale, 8)

    async with get_sessionmaker()() as session:
        removed = await reader_cache.prune(session, tmp_path)
        await session.commit()

    assert removed == 1
    assert not (tmp_path / str(stale)).exists()
    assert (tmp_path / str(fresh)).exists()
    assert await _state(stale) == "known"
    assert await _state(fresh) == "streaming"


async def test_pruning_leaves_a_chapter_that_moved_on_alone(tmp_path):
    downloaded = await _chapter("downloaded")
    cache.write_page(tmp_path, downloaded, 0, JPEG)
    _age(tmp_path, downloaded, 8)
    async with get_sessionmaker()() as session:
        await reader_cache.prune(session, tmp_path)
        await session.commit()
    assert await _state(downloaded) == "downloaded"
    assert not (tmp_path / str(downloaded)).exists()


async def test_pruning_a_missing_cache_root_does_nothing(tmp_path):
    async with get_sessionmaker()() as session:
        assert await reader_cache.prune(session, tmp_path / "absent") == 0
