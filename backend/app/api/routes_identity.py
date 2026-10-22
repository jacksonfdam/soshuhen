"""Who this installation is, for a client looking for it on the LAN.

`/api/health` answers `ok` like any service would, so a scan matching on it
would accept the first thing that replied. `app` is what a scan matches on, and
`instance_id` is what lets a client find the same server again once DHCP has
given the machine another address.
"""

import uuid
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session

router = APIRouter(prefix="/api/identity", tags=["identity"])

Session = Annotated[AsyncSession, Depends(db_session)]


def _version() -> str:
    try:
        return version("soshuhen")
    except PackageNotFoundError:
        return "0.0.0"


async def _instance_id(session: AsyncSession) -> str:
    found = await settings_store.stored(session, settings_store.INSTANCE_ID)
    if found is not None:
        return found
    # Two first requests can race here. Do nothing on conflict and read back,
    # so both answer with whichever id was stored first.
    await session.execute(
        text("insert into setting (key, value) values (:key, :value) on conflict (key) do nothing"),
        {"key": settings_store.INSTANCE_ID, "value": str(uuid.uuid4())},
    )
    await session.commit()
    stored = await settings_store.stored(session, settings_store.INSTANCE_ID)
    assert stored is not None
    return stored


@router.get("")
async def identity(session: Session) -> dict[str, str]:
    return {
        "app": "soshuhen",
        "name": "Soshuhen",
        "version": _version(),
        "instance_id": await _instance_id(session),
    }
