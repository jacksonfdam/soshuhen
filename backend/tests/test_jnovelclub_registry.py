"""J-Novel Club is built by the registry, and finds its token wherever it lives."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import settings_store
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources import registry
from app.sources.base import NotConfigured, get_prose_source


@pytest.fixture(autouse=True)
async def clean(monkeypatch):
    monkeypatch.delenv("JNC_LOGIN", raising=False)
    monkeypatch.delenv("JNC_PASSWORD", raising=False)
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("delete from setting where key in ('jnc_token', 'jnc_token_expires_at')")
        )
        await session.commit()
    yield
    get_settings.cache_clear()


async def test_the_catalogue_row_is_seeded_and_enabled():
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text(
                    """
                    select c.template, c.base_url, c.rate_limit, p.enabled
                      from site_catalogue c join source_pref p on p.key = c.key
                     where c.key = 'jnovelclub'
                    """
                )
            )
        ).one()
    assert (row.template, row.base_url, row.enabled) == (
        "native", "https://labs.j-novel.club", True,
    )
    assert row.rate_limit == {"permits": 1, "period_seconds": 1}


async def test_env_credentials_make_an_env_keeper(monkeypatch):
    monkeypatch.setenv("JNC_LOGIN", "me@example.test")
    monkeypatch.setenv("JNC_PASSWORD", "pw")
    get_settings.cache_clear()
    assert registry.build_jnovelclub().keeper.via == "env"


async def test_without_env_the_keeper_reads_settings():
    assert registry.build_jnovelclub().keeper.via == "settings"
    with pytest.raises(NotConfigured, match="not signed in"):
        await registry.build_jnovelclub().keeper.token()


async def test_a_token_saved_after_the_registry_loaded_is_used():
    async with get_sessionmaker()() as session:
        await registry.reload(session)
    source = get_prose_source("jnovelclub")

    async with get_sessionmaker()() as session:
        await settings_store.set_value(session, settings_store.JNC_TOKEN, "late-token")
        await settings_store.set_value(
            session,
            settings_store.JNC_TOKEN_EXPIRES_AT,
            (datetime.now(UTC) + timedelta(days=5)).isoformat(),
        )
        await session.commit()

    assert await source.keeper.token() == "late-token"
