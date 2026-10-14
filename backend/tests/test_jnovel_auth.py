"""J-Novel Club sign-in and the token keeper, against a mocked API."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.sources.base import NotConfigured
from app.sources.jnovel_auth import JncAuthError, JncSession, TokenKeeper, login

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_login_sends_the_body_the_web_app_sends_and_reads_the_token():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(201, json={"id": "tok-1", "ttl": "1209600s", "created": "x"})

    async with _client(handler) as client:
        # A protobuf Duration renders as "1209600s" in JSON.
        session = await login(client, "me@example.test", "pw", now=lambda: NOW)

    assert seen[0].url.path == "/app/v2/auth/login"
    assert seen[0].url.params["format"] == "json"
    assert json.loads(seen[0].content) == {
        "login": "me@example.test", "password": "pw", "slim": True, "ttl": 1209600,
    }
    assert session == JncSession("tok-1", NOW + timedelta(seconds=1209600))


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "wrong email or password"), (429, "too many sign-in attempts")],
)
async def test_login_refusals_say_why(status, message):
    async with _client(lambda request: httpx.Response(status)) as client:
        with pytest.raises(JncAuthError, match=message):
            await login(client, "me@example.test", "pw")


async def test_env_credentials_sign_in_once_for_concurrent_callers():
    logins = 0

    async def handler(request):
        nonlocal logins
        logins += 1
        await asyncio.sleep(0.01)
        return httpx.Response(201, json={"id": f"tok-{logins}", "ttl": 1209600})

    async with _client(handler) as client:
        keeper = TokenKeeper(client, login_name="me", password="pw", now=lambda: NOW)
        tokens = await asyncio.gather(*(keeper.token() for _ in range(5)))

    assert logins == 1
    assert set(tokens) == {"tok-1"}


async def test_env_credentials_renew_an_hour_before_expiry_and_after_a_refusal():
    clock = [NOW]
    logins = 0

    def handler(request):
        nonlocal logins
        logins += 1
        return httpx.Response(201, json={"id": f"tok-{logins}", "ttl": 7200})

    async with _client(handler) as client:
        keeper = TokenKeeper(client, login_name="me", password="pw", now=lambda: clock[0])
        assert await keeper.token() == "tok-1"
        clock[0] = NOW + timedelta(minutes=59)
        assert await keeper.token() == "tok-1"
        clock[0] = NOW + timedelta(minutes=61)
        assert await keeper.token() == "tok-2"
        await keeper.invalidate("tok-2")
        assert await keeper.token() == "tok-3"


async def test_a_stored_token_is_used_until_it_expires_then_asks_for_a_sign_in():
    clock = [NOW]

    async def load():
        return JncSession("saved", NOW + timedelta(days=3))

    async with _client(lambda request: httpx.Response(500)) as client:
        keeper = TokenKeeper(client, load_stored=load, now=lambda: clock[0])
        assert keeper.via == "settings"
        assert await keeper.token() == "saved"
        clock[0] = NOW + timedelta(days=4)
        with pytest.raises(NotConfigured, match="expired"):
            await keeper.token()


async def test_a_stored_token_the_server_refused_is_not_offered_again():
    async def load():
        return JncSession("saved", NOW + timedelta(days=3))

    async with _client(lambda request: httpx.Response(500)) as client:
        keeper = TokenKeeper(client, load_stored=load, now=lambda: NOW)
        await keeper.invalidate("saved")
        with pytest.raises(NotConfigured, match="sign in again"):
            await keeper.token()


async def test_no_credentials_and_nothing_stored_is_not_configured():
    async def load():
        return None

    async with _client(lambda request: httpx.Response(500)) as client:
        assert TokenKeeper(client).via == "none"
        with pytest.raises(NotConfigured, match="not signed in"):
            await TokenKeeper(client).token()
        with pytest.raises(NotConfigured, match="not signed in"):
            await TokenKeeper(client, load_stored=load).token()
