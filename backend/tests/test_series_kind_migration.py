"""0019 backfills series.kind from what each entry's provider said.

Run against a real database through alembic itself, so the test exercises the
migration's own SQL rather than a copy of it.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
BEFORE = "0018_reader"


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], check=True, capture_output=True, cwd=BACKEND
    )


@pytest.fixture
async def at_head():
    """Leave the database at head however the test ends, for the modules after it."""
    yield
    alembic("upgrade", "head")


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate list_entry, series, chapter restart identity cascade"))
        await session.commit()
    yield


async def _series(session, slug: str, entries: list[tuple[str, dict]]) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:t, :slug, false, '{}'::jsonb) returning id"
            ),
            {"t": slug, "slug": slug},
        )
    ).scalar_one()
    for index, (provider, raw) in enumerate(entries):
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, raw, updated_at)
                values (:p, :m, :s, '[]'::jsonb, 'reading', 0, cast(:raw as jsonb), now())
                """
            ),
            {"p": provider, "m": f"{slug}-{index}", "s": series_id, "raw": json.dumps(raw)},
        )
    return int(series_id)


async def test_backfill_reads_each_providers_own_kind(at_head):
    alembic("downgrade", BEFORE)
    async with get_sessionmaker()() as session:
        ids = {
            "mal_ln": await _series(
                session, "mal-ln", [("mal", {"node": {"media_type": "light_novel"}})]
            ),
            "anilist_novel": await _series(
                session, "anilist-novel", [("anilist", {"media": {"format": "NOVEL"}})]
            ),
            "baka_novel": await _series(
                session, "baka-novel", [("mangabaka", {"Series": {"type": "Novel"}})]
            ),
            "mixed": await _series(
                session,
                "mixed",
                [
                    ("mal", {"node": {"media_type": "novel"}}),
                    ("anilist", {"media": {"format": "MANGA"}}),
                ],
            ),
            "manhwa": await _series(
                session, "manhwa", [("mal", {"node": {"media_type": "manhwa"}})]
            ),
            "silent": await _series(session, "silent", [("local", {})]),
            "one_shot": await _series(
                session, "one-shot", [("anilist", {"media": {"format": "ONE_SHOT"}})]
            ),
        }
        await session.commit()

    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select id, kind from series"))).all()
    kinds = {row.id: row.kind for row in rows}
    assert kinds[ids["mal_ln"]] == "prose"
    assert kinds[ids["anilist_novel"]] == "prose"
    assert kinds[ids["baka_novel"]] == "prose"
    # Mixed resolves to comic, the safe direction from issue #88.
    assert kinds[ids["mixed"]] == "comic"
    assert kinds[ids["manhwa"]] == "comic"
    assert kinds[ids["silent"]] is None
    # ONE_SHOT is in neither vocabulary, so the series stays unknown.
    assert kinds[ids["one_shot"]] is None


async def test_kind_rejects_values_outside_the_vocabulary():
    async with get_sessionmaker()() as session:
        with pytest.raises(Exception, match="series_kind_check"):
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('x', 'x', false, '{}'::jsonb, 'audio')"
                )
            )
