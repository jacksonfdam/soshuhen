"""What a client scanning the LAN is told about this installation."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app import settings_store
from app.api.main import app
from app.db import get_sessionmaker


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate setting"))
        await session.commit()


async def test_identity_names_the_app(client):
    body = (await client.get("/api/identity")).json()
    assert body["app"] == "soshuhen"
    assert body["name"] == "Soshuhen"
    assert body["version"]


async def test_instance_id_is_a_uuid_and_stable(client):
    first = (await client.get("/api/identity")).json()["instance_id"]
    second = (await client.get("/api/identity")).json()["instance_id"]
    assert uuid.UUID(first)
    assert first == second


async def test_instance_id_survives_in_the_setting_table(client):
    first = (await client.get("/api/identity")).json()["instance_id"]
    async with get_sessionmaker()() as session:
        assert await settings_store.stored(session, settings_store.INSTANCE_ID) == first


async def test_instance_id_is_not_listed_with_the_settings(client):
    # all_settings() feeds GET /api/settings "values"; called directly because that
    # route also probes Comick over the network.
    await client.get("/api/identity")
    async with get_sessionmaker()() as session:
        assert "instance_id" not in await settings_store.all_settings(session)
