"""Komga and anime suggestions belong to the managing profile alone."""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import Provider
from app.handlers import komga_scan, progress_push, suggest_build
from app.providers.tokens import store_token
from app.worker.main import enqueue_progress_push
from tests.profiles_fixture import drop_other_profiles, make_profile, manager_id

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async def wipe():
        async with get_sessionmaker()() as session:
            await session.execute(
                text(
                    "truncate list_entry, series, chapter, provider_token, job"
                    " restart identity cascade"
                )
            )
            await drop_other_profiles(session)
            await session.commit()

    await wipe()
    yield
    await wipe()


async def _series(session, slug: str) -> int:
    return (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, komga_series_id)"
                " values (:t, :t, false, '{}'::jsonb, :t) returning id"
            ),
            {"t": slug},
        )
    ).scalar_one()


async def _entry(session, profile_id: int, series_id: int, media_id: str, progress: int):
    await session.execute(
        text(
            "insert into list_entry (profile_id, provider, provider_media_id, series_id, status,"
            " user_progress_chapter, synonyms, raw, updated_at)"
            " values (:p, 'anilist', :m, :s, 'reading', :n, '[]', '{}', now())"
        ),
        {"p": profile_id, "m": media_id, "s": series_id, "n": progress},
    )


@pytest.fixture
async def people():
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        for profile_id in (owner, kid):
            await store_token(
                session, profile_id, Provider.ANILIST,
                access_token="t", refresh_token=None, expires_in=None,
            )
        await session.commit()
    return owner, kid


async def test_progress_push_moves_only_the_managers_lists(people):
    owner, kid = people
    async with get_sessionmaker()() as session:
        shared = await _series(session, "shared")
        await _entry(session, owner, shared, "1", 3)
        await _entry(session, kid, shared, "1", 2)
        await session.commit()
        entries = await progress_push.entries_of(session, shared)
    assert [e.user_progress_chapter for e in entries] == [3]


async def test_komga_scan_marks_read_from_the_managers_progress(people):
    owner, kid = people
    async with get_sessionmaker()() as session:
        shared = await _series(session, "shared")
        await _entry(session, owner, shared, "1", 3)
        await _entry(session, kid, shared, "1", 20)
        for number in (3, 20):
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, komga_book_id)"
                    " values (:s, :n, 'downloaded', :b)"
                ),
                {"s": shared, "n": number, "b": f"book-{number}"},
            )
        await session.commit()

        marked: list[str] = []

        class Client:
            async def set_read_progress(self, book_id, page, completed):
                marked.append(book_id)

        async def log(*args, **kwargs):
            return None

        books = [
            SimpleNamespace(id=f"book-{n}", completed=False, filename=f"{n}.cbz") for n in (3, 20)
        ]
        ctx = SimpleNamespace(session=session, log=log)
        await komga_scan.mark_read_up_to_lists(ctx, Client(), shared, books)
    assert marked == ["book-3"]


async def test_progress_push_cron_ignores_kid_only_series(people):
    _, kid = people
    async with get_sessionmaker()() as session:
        hers = await _series(session, "hers")
        await _entry(session, kid, hers, "9", 1)
        await session.commit()
    await enqueue_progress_push()
    async with get_sessionmaker()() as session:
        queued = (
            await session.execute(text("select count(*) from job where type = 'progress_push'"))
        ).scalar_one()
    assert queued == 0


async def test_suggestions_skip_only_the_managers_known_titles(people):
    _, kid = people
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "s")
        await _entry(session, kid, series_id, "77", 0)
        await session.commit()
        known = await suggest_build.already_known(session)
    assert ("anilist", "77") not in known
