"""The profile API, and how a request says which profile it comes from."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.db import get_sessionmaker
from tests.profiles_fixture import as_profile, drop_other_profiles, make_profile, manager_id

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await drop_other_profiles(session)
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await drop_other_profiles(session)
        await session.commit()


async def test_list_never_exposes_the_pin_hash(client):
    created = await client.post(
        "/api/profiles", json={"name": "Kid", "avatar": "avatar-02", "pin": "1234"}
    )
    assert created.status_code == 201

    listed = (await client.get("/api/profiles")).json()
    kid = next(p for p in listed if p["name"] == "Kid")
    assert kid["has_pin"] is True
    assert kid["is_manager"] is False
    assert not any("hash" in key for profile in listed for key in profile)
    assert "pin" not in created.json() and "pin_hash" not in created.json()


async def test_unlock_accepts_the_right_pin_only(client):
    kid = (
        await client.post("/api/profiles", json={"name": "Kid", "avatar": "avatar-02", "pin": "1234"})
    ).json()["id"]
    right = await client.post(f"/api/profiles/{kid}/unlock", json={"pin": "1234"})
    wrong = await client.post(f"/api/profiles/{kid}/unlock", json={"pin": "4321"})
    assert right.json() == {"ok": True}
    assert wrong.json() == {"ok": False}


async def test_a_profile_without_a_pin_always_unlocks(client):
    kid = (await client.post("/api/profiles", json={"name": "Kid", "avatar": "avatar-02"})).json()
    assert kid["has_pin"] is False
    unlocked = await client.post(f"/api/profiles/{kid['id']}/unlock", json={"pin": "0000"})
    assert unlocked.json() == {"ok": True}


@pytest.mark.parametrize("pin", ["123", "1234567", "12a4", ""])
async def test_pin_must_be_four_to_six_digits(client, pin):
    response = await client.post(
        "/api/profiles", json={"name": "Kid", "avatar": "avatar-02", "pin": pin}
    )
    assert response.status_code == 422


async def test_a_six_digit_pin_is_accepted(client):
    response = await client.post(
        "/api/profiles", json={"name": "Kid", "avatar": "avatar-02", "pin": "123456"}
    )
    assert response.status_code == 201


async def test_avatar_must_be_a_known_key(client):
    response = await client.post("/api/profiles", json={"name": "Kid", "avatar": "avatar-99"})
    assert response.status_code == 422


async def test_patch_changes_name_and_clears_the_pin(client):
    kid = (
        await client.post("/api/profiles", json={"name": "Kid", "avatar": "avatar-02", "pin": "1234"})
    ).json()["id"]
    patched = await client.patch(f"/api/profiles/{kid}", json={"name": "Ana", "pin": None})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Ana"
    assert patched.json()["has_pin"] is False


async def test_patch_leaves_the_pin_when_not_named(client):
    kid = (
        await client.post("/api/profiles", json={"name": "Kid", "avatar": "avatar-02", "pin": "1234"})
    ).json()["id"]
    patched = await client.patch(f"/api/profiles/{kid}", json={"avatar": "avatar-05"})
    assert patched.json()["has_pin"] is True
    assert patched.json()["avatar"] == "avatar-05"


async def test_manager_cannot_be_deleted(client):
    async with get_sessionmaker()() as session:
        manager = await manager_id(session)
    assert (await client.delete(f"/api/profiles/{manager}")).status_code == 409


@pytest.mark.parametrize("value", ["999999", "abc"])
async def test_unknown_profile_header_is_refused(client, value):
    assert (
        await client.get("/api/series", headers={"X-Soshuhen-Profile": value})
    ).status_code == 400
    assert (
        await client.get("/api/reader/chapters/1/pages/0", headers={"X-Soshuhen-Profile": value})
    ).status_code == 400


async def test_no_header_is_the_manager(client):
    async with get_sessionmaker()() as session:
        manager = await manager_id(session)
    assert (await client.get("/api/profiles/current")).json() == {
        "id": manager,
        "is_manager": True,
    }


async def test_the_header_names_the_profile(client):
    async with get_sessionmaker()() as session:
        kid = await make_profile(session)
        await session.commit()
    current = await client.get("/api/profiles/current", headers=as_profile(kid))
    assert current.json() == {"id": kid, "is_manager": False}
