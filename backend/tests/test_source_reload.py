"""The workers hear about a change to the source registry without a restart.

Each process holds its own registry, built at boot. The API rebuilt its own when
a site was toggled, but the two workers never did, so enabling a site in
Settings or pasting a new MangaFire cookie changed nothing a search or a
download could see until the containers restarted.
"""

import asyncio
import contextlib

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app import settings_store
from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources import all_sources, registry
from app.sources.base import install_registry
from app.worker import sources_watch

pytestmark = pytest.mark.asyncio

WAIT_SECONDS = 5.0


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture
async def heard():
    """Every payload sent on the channel the workers listen to."""
    received: asyncio.Queue[str] = asyncio.Queue()
    connection = await asyncpg.connect(get_settings().dsn)
    await connection.add_listener(
        registry.SOURCES_CHANNEL, lambda _c, _p, _ch, payload: received.put_nowait(payload)
    )
    yield received
    await connection.close()


@pytest.fixture(autouse=True)
async def site():
    """A runnable site of this module's own: test_catalogue_repo.py truncates
    the catalogue, so a seeded row is only there depending on what ran first.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into site_catalogue"
                " (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)"
                " values ('reloadsite', 'Reload Site', 'mangathemesia',"
                " 'https://reload.example', 'en', false, '{}'::jsonb, '1.0.0', true)"
                " on conflict (key) do nothing"
            )
        )
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from source_pref where key = 'reloadsite'"))
        await session.execute(text("delete from site_catalogue where key = 'reloadsite'"))
        await session.execute(
            text("delete from setting where key = any(cast(:keys as text[]))"),
            {
                "keys": [
                    settings_store.MANGAFIRE_WAF_PASS,
                    settings_store.READING_MINUTES_PER_CHAPTER,
                ]
            },
        )
        await session.commit()


@contextlib.asynccontextmanager
async def watching():
    stop = asyncio.Event()
    task = asyncio.create_task(sources_watch.watch_sources(stop))
    try:
        yield
    finally:
        stop.set()
        await asyncio.wait_for(task, WAIT_SECONDS)


async def _until(predicate) -> None:
    async with asyncio.timeout(WAIT_SECONDS):
        while not predicate():
            await asyncio.sleep(0.05)


def _sites() -> set[str]:
    return {source.site for source in all_sources()}


async def test_toggling_a_source_tells_the_workers(client, heard):
    response = await client.put("/api/sources/reloadsite", json={"enabled": True})

    assert response.status_code == 200
    await asyncio.wait_for(heard.get(), WAIT_SECONDS)


async def test_changing_the_mangafire_cookie_tells_the_workers(client, heard):
    response = await client.put(
        "/api/settings", json={"values": {settings_store.MANGAFIRE_WAF_PASS: "pasted"}}
    )

    assert response.status_code == 200
    await asyncio.wait_for(heard.get(), WAIT_SECONDS)


async def test_a_setting_no_source_reads_stays_quiet(client, heard):
    response = await client.put(
        "/api/settings", json={"values": {settings_store.READING_MINUTES_PER_CHAPTER: "9"}}
    )

    assert response.status_code == 200
    # A reload rebuilds every enabled source; doing that in both workers for a
    # setting none of them reads is work for nothing.
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(heard.get(), 0.5)


async def test_a_worker_reloads_when_a_change_is_announced():
    async with watching():
        await _until(lambda: "mangadex" in _sites())

        async with get_sessionmaker()() as session:
            await session.execute(
                text(
                    "insert into source_pref (key, enabled) values ('reloadsite', true)"
                    " on conflict (key) do update set enabled = true"
                )
            )
            await registry.announce_change(session)
            await session.commit()

        await _until(lambda: "reloadsite" in _sites())


async def test_a_worker_catches_up_on_what_it_missed_while_not_listening():
    # A change committed before the listener was in place - during boot, or
    # while the connection was down - sends a notification nobody hears.
    install_registry({})

    async with watching():
        await _until(lambda: "mangadex" in _sites())


async def test_a_worker_listens_again_after_losing_its_connection():
    async with watching():
        await _until(lambda: "mangadex" in _sites())

        # Postgres restarting, or a proxy dropping an idle socket, ends the
        # LISTEN without a word; a listener that never noticed would sit
        # waiting on a connection that will not deliver anything again.
        async with get_sessionmaker()() as session:
            await session.execute(
                text(
                    "select pg_terminate_backend(pid) from pg_stat_activity"
                    " where query ilike :listen"
                ),
                {"listen": f"%LISTEN%{registry.SOURCES_CHANNEL}%"},
            )
            await session.commit()
            await session.execute(
                text(
                    "insert into source_pref (key, enabled) values ('reloadsite', true)"
                    " on conflict (key) do update set enabled = true"
                )
            )
            await session.commit()

        # No announcement: the change landed while nobody was listening, and
        # the reload on reconnecting is what has to find it.
        await _until(lambda: "reloadsite" in _sites())
