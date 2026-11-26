"""List credentials belong to a profile: one person's sign-in never answers for another."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import Provider
from app.profiles import Profile, manager
from app.providers import get_source
from app.providers import tokens as token_store
from app.providers.base import TokenSet
from tests.profiles_fixture import as_profile, drop_other_profiles, make_profile

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from provider_token"))
        await session.execute(text("delete from setting where key like 'oauth_state:%'"))
        await drop_other_profiles(session)
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from provider_token"))
        await drop_other_profiles(session)
        await session.commit()


@pytest.fixture
async def kid() -> Profile:
    async with get_sessionmaker()() as session:
        kid_id = await make_profile(session)
        await session.commit()
    return Profile(id=kid_id, is_manager=False)


@pytest.fixture
def mangabaka_key(monkeypatch):
    monkeypatch.setenv("MANGABAKA_TOKEN", "owner-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_static_key_answers_for_the_manager_only(client, kid, mangabaka_key):
    async with get_sessionmaker()() as session:
        owner = await manager(session)
        assert await token_store.access_token_for(session, owner, Provider.MANGABAKA) == (
            "owner-key"
        )
        with pytest.raises(token_store.NotConnected):
            await token_store.access_token_for(session, kid, Provider.MANGABAKA)

    stored = await client.put(
        f"/api/profiles/{kid.id}/credentials/mangabaka", json={"key": "kid-key"}
    )
    assert stored.status_code == 200

    async with get_sessionmaker()() as session:
        assert await token_store.access_token_for(session, kid, Provider.MANGABAKA) == "kid-key"
        assert await token_store.access_token_for(session, owner, Provider.MANGABAKA) == (
            "owner-key"
        )


async def test_keyed_providers_are_the_managers_only(kid, mangabaka_key):
    async with get_sessionmaker()() as session:
        owner = await manager(session)
    assert "mangabaka" in token_store.keyed_providers(owner)
    assert token_store.keyed_providers(kid) == []


async def test_a_key_cannot_be_stored_for_an_oauth_provider(client, kid):
    response = await client.put(
        f"/api/profiles/{kid.id}/credentials/anilist", json={"key": "nope"}
    )
    assert response.status_code == 400


async def test_the_managers_key_lives_in_the_environment(client):
    async with get_sessionmaker()() as session:
        owner = await manager(session)
    response = await client.put(
        f"/api/profiles/{owner.id}/credentials/mangabaka", json={"key": "nope"}
    )
    assert response.status_code == 400


async def test_tokens_are_kept_apart(kid):
    async with get_sessionmaker()() as session:
        owner = await manager(session)
        for profile, token in ((owner, "owner-token"), (kid, "kid-token")):
            await token_store.store_token(
                session,
                profile.id,
                Provider.ANILIST,
                access_token=token,
                refresh_token=None,
                expires_in=None,
            )
        await session.commit()
        assert await token_store.access_token_for(session, owner, Provider.ANILIST) == (
            "owner-token"
        )
        assert await token_store.access_token_for(session, kid, Provider.ANILIST) == "kid-token"


async def test_oauth_state_carries_the_profile(client, kid, monkeypatch):
    monkeypatch.setenv("ANILIST_CLIENT_ID", "client")
    get_settings.cache_clear()
    try:
        started = await client.get(f"/api/auth/anilist/start?profile_id={kid.id}")
        assert started.status_code == 200
        async with get_sessionmaker()() as session:
            key, value = (
                await session.execute(
                    text("select key, value from setting where key like 'oauth_state:%'")
                )
            ).one()
        assert json.loads(value)["profile_id"] == kid.id

        async def exchange(self, code, redirect_uri, verifier):
            return TokenSet(
                access_token="kid-token", refresh_token=None, expires_in=None, account_name="ana"
            )

        monkeypatch.setattr(type(get_source(Provider.ANILIST)), "exchange_code", exchange)
        state = key.removeprefix("oauth_state:")
        callback = await client.get(f"/api/auth/anilist/callback?code=c&state={state}")
        assert callback.status_code == 303
        assert f"profile={kid.id}" in callback.headers["location"]
    finally:
        get_settings.cache_clear()

    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(text("select profile_id, access_token from provider_token"))
        ).all()
    assert rows == [(kid.id, "kid-token")]


async def test_disconnect_is_per_profile(client, kid):
    async with get_sessionmaker()() as session:
        owner = await manager(session)
        for profile in (owner, kid):
            await token_store.store_token(
                session, profile.id, Provider.ANILIST,
                access_token="t", refresh_token=None, expires_in=None,
            )
        await session.commit()

    assert (await client.delete("/api/auth/anilist", headers=as_profile(kid.id))).status_code == 200

    async with get_sessionmaker()() as session:
        left = (await session.execute(text("select profile_id from provider_token"))).scalars().all()
    assert left == [owner.id]


async def test_connections_report_each_profiles_own(client, kid):
    async with get_sessionmaker()() as session:
        await token_store.store_token(
            session, kid.id, Provider.ANILIST,
            access_token="t", refresh_token=None, expires_in=None, account_name="ana",
        )
        await session.commit()
    connections = (await client.get(f"/api/profiles/{kid.id}/connections")).json()
    anilist = next(c for c in connections if c["provider"] == "anilist")
    mal = next(c for c in connections if c["provider"] == "mal")
    assert anilist == {
        "provider": "anilist", "connected": True, "account_name": "ana", "uses_oauth": True,
    }
    assert mal["connected"] is False
    assert all(c["provider"] != "local" for c in connections)
