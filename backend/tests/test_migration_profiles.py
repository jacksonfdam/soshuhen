"""Migration 0033: profiles, and the per-person tables attached to them.

The upgrade must leave an existing installation exactly as it was, owned by one
managing profile; the downgrade must give that profile's data back.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
BEFORE = "0032_job_rerun_requested"

PER_PERSON = (
    "provider_token",
    "list_entry",
    "reading_position",
    "series_reader_pref",
    "progress_event",
    "removed_entry",
)


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], check=True, capture_output=True, cwd=BACKEND
    )


async def clean() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate series, list_entry, provider_token, removed_entry, notification "
                "restart identity cascade"
            )
        )
        await session.commit()


@pytest.fixture
async def at_head():
    """Leave the database at head and empty, for the modules after this one."""
    await clean()
    yield
    alembic("upgrade", "head")
    await clean()
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from profile where not is_manager"))
        await session.commit()


async def seed_before_profiles() -> dict[str, int]:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Kept', 'kept', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text(
                    """
                    insert into chapter (series_id, number, state, discovered_at, bookmarked)
                    values (:s, 1, 'downloaded', now(), true) returning id
                    """
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, status,
                                        user_progress_chapter, synonyms, raw, updated_at)
                values ('anilist', '42', :s, 'reading', 3, '[]', '{}', now())
                """
            ),
            {"s": series_id},
        )
        await session.execute(
            text("insert into provider_token (provider, access_token) values ('anilist', 't')")
        )
        await session.execute(
            text(
                """
                insert into reading_position (series_id, chapter_id, page, updated_at)
                values (:s, :c, 4, now())
                """
            ),
            {"s": series_id, "c": chapter_id},
        )
        await session.execute(
            text(
                """
                insert into series_reader_pref (series_id, mode, scale, background)
                values (:s, 'paged', 'fit-width', 'black')
                """
            ),
            {"s": series_id},
        )
        await session.execute(
            text(
                """
                insert into progress_event (series_id, chapter, delta, source, created_at)
                values (:s, 3, 1, 'manual', now())
                """
            ),
            {"s": series_id},
        )
        await session.execute(
            text("insert into removed_entry (provider, provider_media_id) values ('mal', '7')")
        )
        notification_id = (
            await session.execute(
                text(
                    """
                    insert into notification (series_id, kind, count, first_number,
                                              last_number, created_at, read_at)
                    values (:s, 'chapters', 1, 1, 1, now(), now()) returning id
                    """
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.commit()
    return {"series": series_id, "chapter": chapter_id, "notification": notification_id}


async def test_upgrade_attaches_existing_rows_to_the_manager(at_head):
    alembic("downgrade", BEFORE)
    ids = await seed_before_profiles()
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        profiles = (await session.execute(text("select id, is_manager from profile"))).all()
        assert len(profiles) == 1
        manager_id, is_manager = profiles[0]
        assert is_manager

        for table in PER_PERSON:
            owners = (
                await session.execute(text(f"select distinct profile_id from {table}"))
            ).scalars().all()
            assert owners == [manager_id], table

        bookmarks = (
            await session.execute(text("select profile_id, chapter_id from chapter_bookmark"))
        ).all()
        assert bookmarks == [(manager_id, ids["chapter"])]

        reads = (
            await session.execute(
                text("select profile_id, notification_id from notification_read")
            )
        ).all()
        assert reads == [(manager_id, ids["notification"])]


async def make_second_profile(session) -> int:
    return (
        await session.execute(
            text("insert into profile (name, avatar) values ('Kid', 'avatar-02') returning id")
        )
    ).scalar_one()


async def test_two_profiles_may_hold_the_same_provider_entry(at_head):
    async with get_sessionmaker()() as session:
        manager_id = (
            await session.execute(text("select id from profile where is_manager"))
        ).scalar_one()
        kid_id = await make_second_profile(session)
        insert = text(
            """
            insert into list_entry (profile_id, provider, provider_media_id, status, user_progress_chapter, synonyms,
                                    raw, updated_at)
            values (:p, 'anilist', '42', 'reading', 0, '[]', '{}', now())
            """
        )
        await session.execute(insert, {"p": manager_id})
        await session.execute(insert, {"p": kid_id})
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(insert, {"p": kid_id})
        await session.rollback()


async def test_only_one_manager(at_head):
    async with get_sessionmaker()() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "insert into profile (name, avatar, is_manager) "
                    "values ('Other', 'avatar-03', true)"
                )
            )
        await session.rollback()


async def test_downgrade_keeps_the_managers_data(at_head):
    async with get_sessionmaker()() as session:
        manager_id = (
            await session.execute(text("select id from profile where is_manager"))
        ).scalar_one()
        kid_id = await make_second_profile(session)
        insert = text(
            """
            insert into list_entry (profile_id, provider, provider_media_id, status, user_progress_chapter, synonyms,
                                    raw, updated_at)
            values (:p, 'anilist', :m, 'reading', 0, '[]', '{}', now())
            """
        )
        await session.execute(insert, {"p": manager_id, "m": "1"})
        await session.execute(insert, {"p": kid_id, "m": "2"})
        await session.commit()

    alembic("downgrade", BEFORE)

    async with get_sessionmaker()() as session:
        left = (
            await session.execute(text("select provider_media_id from list_entry"))
        ).scalars().all()
        assert left == ["1"]
