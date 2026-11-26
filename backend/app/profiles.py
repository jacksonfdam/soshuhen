"""Profiles: who a request or a job acts for.

A profile is a person in one household sharing one library. The PIN keeps a
child from opening a parent's profile by a wrong tap; it is not access control,
and the API does not pretend otherwise (see docs/configuration.md, "The stack
has no authentication of its own").
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

AVATAR_KEYS: tuple[str, ...] = tuple(f"avatar-{n:02d}" for n in range(1, 13))

_PIN = re.compile(r"^\d{4,6}$")
# scrypt's interactive-login parameters: a PIN check is one call per tap.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


@dataclass(frozen=True)
class Profile:
    id: int
    is_manager: bool


def valid_pin(pin: str) -> bool:
    return bool(_PIN.match(pin))


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


async def manager(session: AsyncSession) -> Profile:
    row = (
        await session.execute(text("select id from profile where is_manager"))
    ).scalar_one()
    return Profile(id=int(row), is_manager=True)


async def by_id(session: AsyncSession, profile_id: int) -> Profile | None:
    row = (
        await session.execute(
            text("select id, is_manager from profile where id = :id"), {"id": profile_id}
        )
    ).first()
    return Profile(id=int(row.id), is_manager=bool(row.is_manager)) if row else None


async def of_job(session: AsyncSession, payload: dict[str, Any]) -> Profile:
    """The profile a job acts for. Jobs queued before profiles existed are the manager's."""
    profile_id = payload.get("profile_id")
    if profile_id is None:
        return await manager(session)
    found = await by_id(session, int(profile_id))
    if found is None:
        # Deleted while the job waited: nothing it could write still belongs to anyone.
        raise LookupError(f"profile {profile_id} no longer exists")
    return found


async def all_profiles(session: AsyncSession) -> list[Profile]:
    rows = (
        await session.execute(text("select id, is_manager from profile order by position, id"))
    ).all()
    return [Profile(id=int(r.id), is_manager=bool(r.is_manager)) for r in rows]
