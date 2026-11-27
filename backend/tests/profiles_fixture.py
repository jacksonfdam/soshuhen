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


async def run_one(session: AsyncSession, job_type, payload: dict) -> None:
    """Enqueue one job, lease it, and run its handler inside `session`."""
    import importlib

    from app.enums import Lane, types_for
    from app.handlers.base import JobContext, get_handler
    from app.queue import repo

    await session.execute(text("delete from job"))
    await repo.enqueue(session, job_type, payload)
    await session.commit()
    job = await repo.lease(
        session, types=[*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]
    )
    await session.commit()
    # A handler registers itself when its module is imported, as the worker does.
    importlib.import_module(f"app.handlers.{job_type.value}")
    handler = get_handler(job_type)
    assert handler is not None and job is not None
    await handler(JobContext(session=session, job=job))
    await session.commit()
