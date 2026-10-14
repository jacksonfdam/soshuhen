"""The J-Novel Club sign-in keeps the token and nothing else."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api import routes_sources
from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources.jnovel_auth import JncAuthError, JncSession
from tests.jnovelclub_seed import seed_jnovelclub

pytestmark = pytest.mark.asyncio
EXPIRES = datetime(2026, 10, 28, 12, tzinfo=UTC)


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
    await seed_jnovelclub()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
def accepted(monkeypatch):
    async def fake_login(client, login_name, password, **kwargs):
        logging.getLogger("test").info("login called")
        return JncSession("tok-abc", EXPIRES)

    monkeypatch.setattr(routes_sources.jnovel_auth, "login", fake_login)


async def _stored() -> dict[str, str]:
    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select key, value from setting"))).all()
    return dict(rows)


async def test_signing_in_stores_the_token_and_its_expiry(client, accepted):
    response = await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    assert response.status_code == 200
    assert response.json() == {"signed_in": True, "expires_at": EXPIRES.isoformat()}
    stored = await _stored()
    assert stored["jnc_token"] == "tok-abc"
    assert datetime.fromisoformat(stored["jnc_token_expires_at"]) == EXPIRES


async def test_the_password_is_neither_stored_nor_logged(client, accepted, caplog):
    caplog.set_level(logging.DEBUG)
    await client.post(
        "/api/sources/jnovelclub/sign-in",
        json={"login": "me@example.test", "password": "s3cret-pass"},
    )
    assert "s3cret-pass" not in (await _stored()).values()
    assert "s3cret-pass" not in caplog.text


async def test_the_token_never_reaches_get_settings(client, accepted):
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    body = (await client.get("/api/settings")).text
    assert "tok-abc" not in body
    assert "jnc_token" not in body


async def test_a_refused_sign_in_says_why(client, monkeypatch):
    async def refuse(*args, **kwargs):
        raise JncAuthError("wrong email or password")

    monkeypatch.setattr(routes_sources.jnovel_auth, "login", refuse)
    response = await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "x", "password": "y"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "wrong email or password"


async def test_signing_in_is_refused_when_env_signs_in(client, accepted, monkeypatch):
    monkeypatch.setenv("JNC_LOGIN", "me@example.test")
    monkeypatch.setenv("JNC_PASSWORD", "pw")
    get_settings.cache_clear()
    response = await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "x", "password": "y"}
    )
    assert response.status_code == 409


async def test_signing_out_clears_the_token(client, accepted, monkeypatch):
    async def fake_logout(client, token):
        return None

    monkeypatch.setattr(routes_sources.jnovel_auth, "logout", fake_logout)
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    response = await client.delete("/api/sources/jnovelclub/sign-in")
    assert response.json() == {"signed_in": False}
    assert "jnc_token" not in await _stored()


async def test_the_session_says_where_the_sign_in_comes_from(client, accepted, monkeypatch):
    async def level(self):
        return "PREMIUM_MEMBER"

    monkeypatch.setattr(routes_sources.JNovelClubSource, "account_level", level)
    assert (await client.get("/api/sources/jnovelclub/session")).json() == {
        "via": "none", "expires_at": None, "level": None,
    }
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    assert (await client.get("/api/sources/jnovelclub/session")).json() == {
        "via": "settings", "expires_at": EXPIRES.isoformat(), "level": "PREMIUM_MEMBER",
    }
    monkeypatch.setenv("JNC_LOGIN", "me@example.test")
    monkeypatch.setenv("JNC_PASSWORD", "pw")
    get_settings.cache_clear()
    session = (await client.get("/api/sources/jnovelclub/session")).json()
    assert session["via"] == "env"


async def test_an_expired_saved_token_reads_as_signed_out(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into setting (key, value) values ('jnc_token', 'old'),"
                " ('jnc_token_expires_at', :at)"
            ),
            {"at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        )
        await session.commit()
    session_info = (await client.get("/api/sources/jnovelclub/session")).json()
    assert session_info["via"] == "none"
