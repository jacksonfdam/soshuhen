"""Profiles: the picker's list, and managing who uses this installation."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentProfile, db_session
from app.enums import Provider
from app.profiles import AVATAR_KEYS, hash_pin, valid_pin, verify_pin
from app.providers import get_source, syncing_providers
from app.providers.tokens import store_token
from app.series_removal import delete_profile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

Session = Annotated[AsyncSession, Depends(db_session)]

COLUMNS = "id, name, avatar, pin_hash is not null as has_pin, is_manager, position"


def _avatar(value: str | None) -> str | None:
    if value is not None and value not in AVATAR_KEYS:
        raise ValueError(f"unknown avatar {value!r}")
    return value


def _pin(value: str | None) -> str | None:
    if value is not None and not valid_pin(value):
        raise ValueError("a PIN is 4 to 6 digits")
    return value


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    avatar: str
    pin: str | None = None

    _check_avatar = field_validator("avatar")(_avatar)
    _check_pin = field_validator("pin")(_pin)


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    avatar: str | None = None
    pin: str | None = None
    position: int | None = None

    _check_avatar = field_validator("avatar")(_avatar)
    _check_pin = field_validator("pin")(_pin)


class UnlockIn(BaseModel):
    pin: str


class CredentialIn(BaseModel):
    key: str = Field(min_length=1)


def _out(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "avatar": row.avatar,
        "has_pin": row.has_pin,
        "is_manager": row.is_manager,
        "position": row.position,
    }


async def _one(session: AsyncSession, profile_id: int) -> Any:
    row = (
        await session.execute(
            text(f"select {COLUMNS} from profile where id = :id"), {"id": profile_id}
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no such profile")
    return row


@router.get("")
async def list_profiles(session: Session) -> list[dict[str, Any]]:
    rows = (
        await session.execute(text(f"select {COLUMNS} from profile order by position, id"))
    ).all()
    return [_out(r) for r in rows]


@router.get("/current")
async def current(profile: CurrentProfile) -> dict[str, Any]:
    return {"id": profile.id, "is_manager": profile.is_manager}


@router.post("", status_code=201)
async def create(body: ProfileIn, session: Session) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                f"""
                insert into profile (name, avatar, pin_hash, position)
                values (:name, :avatar, :pin_hash,
                        (select coalesce(max(position), 0) + 1 from profile))
                returning {COLUMNS}
                """
            ),
            {
                "name": body.name,
                "avatar": body.avatar,
                "pin_hash": hash_pin(body.pin) if body.pin else None,
            },
        )
    ).first()
    await session.commit()
    return _out(row)


@router.patch("/{profile_id}")
async def update(profile_id: int, body: ProfilePatch, session: Session) -> dict[str, Any]:
    await _one(session, profile_id)
    given = body.model_fields_set
    changes: dict[str, Any] = {}
    for field in ("name", "avatar", "position"):
        if field in given and getattr(body, field) is not None:
            changes[field] = getattr(body, field)
    # `pin: null` clears it; a PIN left out of the body is left alone.
    if "pin" in given:
        changes["pin_hash"] = hash_pin(body.pin) if body.pin else None
    if changes:
        assignments = ", ".join(f"{column} = :{column}" for column in changes)
        await session.execute(
            text(f"update profile set {assignments} where id = :id"),
            {**changes, "id": profile_id},
        )
        await session.commit()
    return _out(await _one(session, profile_id))


@router.post("/{profile_id}/unlock")
async def unlock(profile_id: int, body: UnlockIn, session: Session) -> dict[str, bool]:
    stored = (
        await session.execute(
            text("select pin_hash from profile where id = :id"), {"id": profile_id}
        )
    ).first()
    if stored is None:
        raise HTTPException(status_code=404, detail="no such profile")
    if stored.pin_hash is None:
        return {"ok": True}
    return {"ok": verify_pin(body.pin, stored.pin_hash)}


@router.delete("/{profile_id}")
async def delete(profile_id: int, session: Session) -> dict[str, Any]:
    row = await _one(session, profile_id)
    if row.is_manager:
        raise HTTPException(status_code=409, detail="the managing profile cannot be deleted")
    removed = await delete_profile(session, profile_id)
    await session.commit()
    return {"ok": True, "series_removed": removed}


@router.get("/{profile_id}/connections")
async def connections(profile_id: int, session: Session) -> list[dict[str, Any]]:
    """Which of a profile's lists are connected. The local list is not one."""
    row = await _one(session, profile_id)
    stored = {
        r.provider: r.account_name
        for r in (
            await session.execute(
                text("select provider, account_name from provider_token where profile_id = :id"),
                {"id": profile_id},
            )
        ).all()
    }
    result = []
    for provider in syncing_providers():
        source = get_source(provider)
        # The manager's key-based providers answer from the environment.
        configured = row.is_manager and bool(source.static_credential())
        result.append(
            {
                "provider": str(provider),
                "connected": str(provider) in stored or configured,
                "account_name": stored.get(str(provider)),
                "uses_oauth": source.uses_oauth,
            }
        )
    return result


@router.put("/{profile_id}/credentials/{provider}")
async def store_credential(
    profile_id: int, provider: Provider, body: CredentialIn, session: Session
) -> dict[str, bool]:
    """A key for a provider that takes one instead of a sign-in, for one profile."""
    row = await _one(session, profile_id)
    if get_source(provider).uses_oauth:
        raise HTTPException(status_code=400, detail=f"{provider} is connected by signing in")
    if row.is_manager:
        raise HTTPException(
            status_code=400,
            detail=f"the managing profile's {provider} key is set in the environment",
        )
    await store_token(
        session, profile_id, provider, access_token=body.key, refresh_token=None, expires_in=None
    )
    await session.commit()
    return {"ok": True}
