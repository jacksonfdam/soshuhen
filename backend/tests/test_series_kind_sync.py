"""list_sync keeps series.kind in step with the entries a series holds."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.list_sync import refresh_series_kind, series_kind_column


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate list_entry, series restart identity cascade"))
        await session.commit()
    yield


async def _series(session, *, meta: dict | None = None, kind: str | None = None) -> int:
    return int(
        (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('t', 't', false, cast(:meta as jsonb), cast(:kind as text))"
                    " returning id"
                ),
                {"meta": json.dumps(meta or {}), "kind": kind},
            )
        ).scalar_one()
    )


async def _entry(session, series_id: int, provider: str, media_id: str, raw: dict) -> None:
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, status, raw,
                                    synonyms, user_progress_chapter, updated_at)
            values (:p, :m, :s, 'reading', cast(:raw as jsonb), '[]'::jsonb, 0, now())
            """
        ),
        {"p": provider, "m": media_id, "s": series_id, "raw": json.dumps(raw)},
    )


async def _kind(session, series_id: int) -> str | None:
    return (
        await session.execute(text("select kind from series where id = :id"), {"id": series_id})
    ).scalar_one()


def test_series_kind_column_speaks_the_column_vocabulary():
    assert series_kind_column({"NOVEL"}) == "prose"
    assert series_kind_column({"MANGA", "NOVEL"}) == "comic"
    assert series_kind_column({None}) is None
    assert series_kind_column(set()) is None


async def test_a_novel_entry_makes_its_series_prose():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _entry(session, series_id, "anilist", "1", {"media": {"format": "NOVEL"}})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) == "prose"


async def test_a_comic_entry_joining_turns_the_series_comic():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, kind="prose")
        await _entry(session, series_id, "anilist", "1", {"media": {"format": "NOVEL"}})
        await _entry(session, series_id, "mal", "2", {"node": {"media_type": "manga"}})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) == "comic"


async def test_a_kind_the_user_locked_is_left_alone():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, meta={"kind_locked": True}, kind="prose")
        await _entry(session, series_id, "mal", "1", {"node": {"media_type": "manga"}})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) == "prose"


async def test_entries_that_say_nothing_leave_the_kind_unknown():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _entry(session, series_id, "local", "1", {})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) is None
