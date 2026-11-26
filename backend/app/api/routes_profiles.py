"""Profiles: the picker's list, and managing who uses this installation."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentProfile, db_session
from app.profiles import AVATAR_KEYS, hash_pin, valid_pin, verify_pin

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
    raise HTTPException(status_code=501, detail="deleting a profile is not available yet")
