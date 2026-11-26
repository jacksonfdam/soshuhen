"""Profiles for tests: the manager the migration made, and others made on demand."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.profiles import hash_pin

HEADER = "X-Soshuhen-Profile"


async def manager_id(session: AsyncSession) -> int:
    return (await session.execute(text("select id from profile where is_manager"))).scalar_one()


async def make_profile(session: AsyncSession, name: str = "Kid", *, pin: str | None = None) -> int:
    return (
        await session.execute(
            text(
                "insert into profile (name, avatar, pin_hash) values (:n, 'avatar-02', :p)"
                " returning id"
            ),
            {"n": name, "p": hash_pin(pin) if pin else None},
        )
    ).scalar_one()


async def drop_other_profiles(session: AsyncSession) -> None:
    """Every profile but the manager goes, and their rows with them by cascade."""
    await session.execute(text("delete from profile where not is_manager"))


def as_profile(profile_id: int) -> dict[str, str]:
    return {HEADER: str(profile_id)}
