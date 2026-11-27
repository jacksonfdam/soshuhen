from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import profiles
from app.db import get_sessionmaker
from app.profiles import Profile


async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def current_profile(
    x_soshuhen_profile: Annotated[str | None, Header()] = None,
) -> Profile:
    """The profile this request acts for. No header is the manager.

    An id that names nobody is refused rather than read as the manager: a phone
    still holding a deleted profile must fail loudly, not quietly start writing
    to someone else's lists.

    Its own short session rather than the request's: this runs for every
    request, the event stream included, and a session left open there would
    hold a pooled connection for as long as a tab stays open.
    """
    try:
        profile_id = None if x_soshuhen_profile is None else int(x_soshuhen_profile)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Soshuhen-Profile is not a profile id")
    async with get_sessionmaker()() as session:
        if profile_id is None:
            return await profiles.manager(session)
        found = await profiles.by_id(session, profile_id)
    if found is None:
        raise HTTPException(status_code=400, detail=f"no profile {profile_id}")
    return found


CurrentProfile = Annotated[Profile, Depends(current_profile)]
