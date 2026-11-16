"""Hand server copies a device has verified to the download lane for deletion.

Nothing is deleted here: `api` mounts the library read-only, and the job re-checks
each file against the ETag the device copied it under before it removes anything.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import JobType
from app.queue import repo

router = APIRouter(prefix="/api/offload", tags=["offload"])

Session = Annotated[AsyncSession, Depends(db_session)]


class OffloadItem(BaseModel):
    id: int
    etag: str
    size: int


class OffloadIn(BaseModel):
    chapters: list[OffloadItem] = []
    volumes: list[OffloadItem] = []


# Table names come from this map, never from the request. The source column says
# whether the item can ever be downloaded again: an imported file cannot.
_KINDS = (
    ("chapters", "chapter", "source_url is not null"),
    ("volumes", "volume", "source_volume_id not like 'import:%'"),
)


@router.post("")
async def offload(body: OffloadIn, session: Session) -> dict[str, Any]:
    if not body.chapters and not body.volumes:
        raise HTTPException(status_code=422, detail="nothing to offload")
    accepted: dict[str, list[dict[str, Any]]] = {"chapters": [], "volumes": []}
    skipped: list[dict[str, Any]] = []
    for key, table, has_source in _KINDS:
        items: list[OffloadItem] = getattr(body, key)
        if not items:
            continue
        rows = await session.execute(
            text(
                f"select id, state, file_path, {has_source} as has_source from {table}"
                " where id = any(cast(:ids as bigint[]))"
            ),
            {"ids": [item.id for item in items]},
        )
        by_id = {row.id: row for row in rows.all()}
        for item in items:
            row = by_id.get(item.id)
            reason = None
            if row is None:
                reason = "unknown"
            elif row.state != "downloaded" or row.file_path is None:
                reason = "not downloaded"
            elif not row.has_source:
                # The phone would hold the only copy, with nowhere to fetch it again.
                reason = "no source to download it again"
            if reason is not None:
                skipped.append({"id": item.id, "kind": table, "reason": reason})
            else:
                accepted[key].append(item.model_dump())
    queued = len(accepted["chapters"]) + len(accepted["volumes"])
    if queued:
        # Marked now, not when the job runs: the phone refreshes straight after,
        # and a row still saying downloaded would let it delete its own copy
        # without the only-copy warning while the job waits behind downloads.
        # The file stays and file_path with it until the job has checked it.
        for key, table, _ in _KINDS:
            ids = [item["id"] for item in accepted[key]]
            if ids:
                await session.execute(
                    text(
                        f"update {table} set state = 'offloaded'"
                        " where id = any(cast(:ids as bigint[])) and state = 'downloaded'"
                    ),
                    {"ids": ids},
                )
        await repo.enqueue(session, JobType.OFFLOAD, accepted, priority=0)
        await session.commit()
    return {"queued": queued, "skipped": skipped}
