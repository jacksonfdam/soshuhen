"""Each profile's lists sync into one shared library."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, ListStatus, Provider
from app.providers import get_source
from app.providers.base import ListEntryDTO
from app.providers.tokens import store_token
from app.worker.main import enqueue_list_sync
from tests.profiles_fixture import drop_other_profiles, make_profile, manager_id, run_one

pytestmark = pytest.mark.asyncio


def entry(media_id: str, title: str, progress: int) -> ListEntryDTO:
    return ListEntryDTO(
        provider=Provider.ANILIST,
        media_id=media_id,
        status=ListStatus.READING,
        title_romaji=title,
        title_english=title,
        progress_chapter=progress,
        raw={},
    )


@pytest.fixture(autouse=True)
async def clean():
    async def wipe():
        async with get_sessionmaker()() as session:
            await session.execute(
                text(
                    "truncate list_entry, series, removed_entry, provider_token, job"
                    " restart identity cascade"
                )
            )
            await drop_other_profiles(session)
            await session.commit()

    await wipe()
    yield
    await wipe()


@pytest.fixture
async def owner_and_kid():
    async with get_sessionmaker()() as session:
        owner = await manager_id(session)
        kid = await make_profile(session)
        for profile_id, token in ((owner, "owner-token"), (kid, "kid-token")):
            await store_token(
                session, profile_id, Provider.ANILIST,
                access_token=token, refresh_token=None, expires_in=None,
            )
        await session.commit()
    return owner, kid


@pytest.fixture
def anilist_lists(monkeypatch):
    """What each token's AniList list holds."""
    lists: dict[str, list[ListEntryDTO]] = {}

    async def fetch_list(self, token):
        return lists[token]

    monkeypatch.setattr(type(get_source(Provider.ANILIST)), "fetch_list", fetch_list)
    return lists


async def test_same_title_on_two_profiles_shares_one_series(owner_and_kid, anilist_lists):
    owner, kid = owner_and_kid
    anilist_lists["owner-token"] = [entry("42", "Frieren", 10)]
    anilist_lists["kid-token"] = [entry("42", "Frieren", 2)]

    async with get_sessionmaker()() as session:
        await run_one(session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": owner})
        await run_one(session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": kid})
        series = (await session.execute(text("select count(*) from series"))).scalar_one()
        rows = dict(
            (
                await session.execute(
                    text("select profile_id, user_progress_chapter from list_entry")
                )
            ).all()
        )
        series_ids = (
            await session.execute(text("select distinct series_id from list_entry"))
        ).scalars().all()
    assert series == 1
    assert len(series_ids) == 1
    assert rows == {owner: 10, kid: 2}


async def test_a_removal_tombstone_is_per_profile(owner_and_kid, anilist_lists):
    owner, kid = owner_and_kid
    anilist_lists["owner-token"] = [entry("42", "Frieren", 10)]
    anilist_lists["kid-token"] = [entry("42", "Frieren", 2)]
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into removed_entry (profile_id, provider, provider_media_id)"
                " values (:p, 'anilist', '42')"
            ),
            {"p": owner},
        )
        await session.commit()
        await run_one(session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": owner})
        await run_one(session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": kid})
        holders = (
            await session.execute(text("select profile_id from list_entry"))
        ).scalars().all()
    assert holders == [kid]


async def test_cron_enqueues_per_connected_profile(owner_and_kid):
    owner, kid = owner_and_kid
    await enqueue_list_sync()
    async with get_sessionmaker()() as session:
        queued = {
            (row.payload["profile_id"], row.payload["provider"])
            for row in (
                await session.execute(text("select payload from job where type = 'list_sync'"))
            ).all()
        }
    assert (owner, "anilist") in queued
    assert (kid, "anilist") in queued
    assert (kid, "mal") not in queued
    assert (owner, "mal") not in queued


async def test_local_progress_carries_within_a_profile_only(owner_and_kid, anilist_lists):
    owner, kid = owner_and_kid
    anilist_lists["kid-token"] = [entry("42", "Frieren", 3)]
    async with get_sessionmaker()() as session:
        await run_one(session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": kid})
        series_id = (await session.execute(text("select id from series"))).scalar_one()
        await session.execute(
            text(
                "insert into list_entry (profile_id, provider, provider_media_id, series_id,"
                " status, user_progress_chapter, synonyms, raw, updated_at)"
                " values (:p, 'local', :m, :s, 'reading', 10, '[]', '{}', now())"
            ),
            {"p": owner, "m": str(series_id), "s": series_id},
        )
        await session.commit()
        await run_one(session, JobType.LIST_SYNC, {"provider": "anilist", "profile_id": kid})
        writes = (
            await session.execute(text("select count(*) from job where type = 'progress_write'"))
        ).scalar_one()
    assert writes == 0
