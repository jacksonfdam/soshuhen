"""Removing a series, and remembering that it was removed.

The first destructive operation in this pipeline, and the reason it needs more
than a delete: `list_entry` survives the cascade with a null series_id and
`list_sync` matches on it, so a series removed at noon returns by six. A
tombstone keyed by the provider's own id is what makes the removal stick.

Removal is one profile's. Another profile still holding the series keeps it,
with its mapping and chapters; the series row goes only when no list of anyone's
holds it any more.

Downloaded archives are deliberately left on disk. Nothing else here deletes a
file, and a reader who removes a series from the pipeline has not asked to lose
the chapters they already have.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import profiles


@dataclass(frozen=True)
class Removal:
    """What a removal did, so the screen can say it rather than "removed 0"."""

    # Series that left the requester's library.
    removed: int = 0
    # Of those, series no one holds any more, whose rows went too.
    deleted: int = 0
    # Ids that were never in the requester's library, and were left alone.
    skipped: list[int] = field(default_factory=list)


async def remove_series(
    session: AsyncSession, series_ids: Sequence[int], *, profile_id: int | None = None
) -> Removal:
    """Remove these series from one profile's library.

    A caller naming no profile acts for the manager, as a request without a
    profile header does. Only series in the requester's library are touched:
    another profile's series, or for anyone but the manager a series no list
    holds, is skipped rather than deleted from under its owner.

    One statement per step rather than per series: removing a selection of
    twenty is one decision the user made once, not twenty round trips.
    """
    if not series_ids:
        return Removal()

    requested = list(dict.fromkeys(series_ids))
    profile = (
        await profiles.by_id(session, profile_id)
        if profile_id is not None
        else await profiles.manager(session)
    )
    if profile is None:
        raise LookupError(f"no profile {profile_id}")
    profile_id = profile.id
    held = set(
        (
            await session.execute(
                text(
                    """
                    select s.id from series s
                     where s.id = any(cast(:ids as bigint[]))
                       and (exists (select 1 from list_entry e
                                     where e.series_id = s.id and e.profile_id = :profile_id)
                            or (cast(:is_manager as boolean)
                                and not exists (select 1 from list_entry e
                                                 where e.series_id = s.id)))
                    """
                ),
                {"ids": requested, "profile_id": profile_id, "is_manager": profile.is_manager},
            )
        ).scalars().all()
    )
    ids = [series_id for series_id in requested if series_id in held]
    skipped = [series_id for series_id in requested if series_id not in held]
    if not ids:
        return Removal(skipped=skipped)

    # Recorded before anything is deleted, because the entries are about to go
    # and they are the only place the provider's id for this work is written.
    await session.execute(
        text(
            """
            insert into removed_entry (profile_id, provider, provider_media_id)
            select profile_id, provider, provider_media_id
              from list_entry
             where series_id = any(cast(:ids as bigint[])) and profile_id = :profile_id
            on conflict do nothing
            """
        ),
        {"ids": ids, "profile_id": profile_id},
    )

    # The entries go too. Left behind they would be orphans with a null series,
    # and the tombstone already carries what a later sync needs to know.
    await session.execute(
        text(
            "delete from list_entry"
            " where series_id = any(cast(:ids as bigint[])) and profile_id = :profile_id"
        ),
        {"ids": ids, "profile_id": profile_id},
    )
    deleted = await _drop_unheld(session, ids)
    return Removal(removed=len(ids), deleted=deleted, skipped=skipped)


async def _drop_unheld(session: AsyncSession, ids: list[int]) -> int:
    """Delete those of these series no profile's list still holds."""
    result = await session.execute(
        text(
            """
            delete from series s
             where s.id = any(cast(:ids as bigint[]))
               and not exists (select 1 from list_entry e where e.series_id = s.id)
            returning s.id
            """
        ),
        {"ids": ids},
    )
    return len(result.fetchall())


async def delete_profile(session: AsyncSession, profile_id: int) -> int:
    """Delete a profile and everything that was only theirs. Returns series removed.

    Their own rows go by cascade. A series is then removed only if they were
    the last to hold it; one another profile reads stays, with its files.
    """
    found = await profiles.by_id(session, profile_id)
    if found is None:
        raise LookupError(f"no profile {profile_id}")
    if found.is_manager:
        raise ValueError("the managing profile cannot be deleted")
    held = (
        await session.execute(
            text(
                "select distinct series_id from list_entry"
                " where profile_id = :p and series_id is not null"
            ),
            {"p": profile_id},
        )
    ).scalars().all()
    # Its waiting jobs would only fail: nothing they write belongs to anyone now.
    await session.execute(
        text(
            "delete from job where state = 'pending'"
            " and cast(payload->>'profile_id' as bigint) = :p"
        ),
        {"p": profile_id},
    )
    await session.execute(text("delete from profile where id = :p"), {"p": profile_id})
    return await _drop_unheld(session, list(held))
