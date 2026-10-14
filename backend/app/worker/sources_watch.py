"""Keeps this worker's source registry in step with Settings.

The registry is built in memory at boot (app/sources/registry.py). The API
rebuilds its own when a site is toggled or the MangaFire cookie changes, but a
worker never sees that request, and until this existed enabling a site changed
nothing a search or a download could reach until the containers restarted.
"""

import asyncio
import contextlib
import logging

import asyncpg

from app.config import get_settings
from app.db import get_sessionmaker
from app.sources import registry

log = logging.getLogger(__name__)
RECONNECT_SECONDS = 3.0


async def _reload() -> None:
    try:
        async with get_sessionmaker()() as session:
            await registry.reload(session)
    except Exception as exc:  # noqa: BLE001
        # The registry already installed keeps serving. A worker that died here
        # would stop every job for a change that only affects which sites exist.
        log.warning("source registry not reloaded, keeping the current one: %s", exc)
        return
    log.info("source registry reloaded")


async def watch_sources(stop: asyncio.Event) -> None:
    """LISTEN for changes and reload on each, until `stop` is set."""
    while not stop.is_set():
        try:
            connection = await asyncpg.connect(get_settings().dsn)
        except Exception as exc:  # noqa: BLE001
            log.warning("cannot listen for source changes, retrying: %s", exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), RECONNECT_SECONDS)
            continue
        try:
            await _follow(connection, stop)
        finally:
            with contextlib.suppress(Exception):
                await connection.close()


async def _follow(connection: asyncpg.Connection, stop: asyncio.Event) -> None:
    """Reload on every notification until `stop` is set or the connection drops."""
    changed = asyncio.Event()
    lost = asyncio.Event()
    connection.add_termination_listener(lambda _c: lost.set())
    await connection.add_listener(
        registry.SOURCES_CHANNEL, lambda _c, _p, _ch, _payload: changed.set()
    )
    # Reloaded once the listener is in place, not before: a change committed
    # between the boot load and here, or while a lost connection was being
    # replaced, sent a notification nobody heard.
    changed.set()
    while not stop.is_set() and not lost.is_set():
        waits = [asyncio.ensure_future(event.wait()) for event in (changed, stop, lost)]
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiting in waits:
                waiting.cancel()
        if changed.is_set() and not stop.is_set():
            # Cleared before the reload, so a change committed during it sets
            # the flag again and is picked up on the next pass.
            changed.clear()
            await _reload()
    if lost.is_set() and not stop.is_set():
        log.warning("source change listener lost, reconnecting")
