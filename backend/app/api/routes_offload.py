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


# Table names come from this map, never from the request.
_KINDS = (("chapters", "chapter"), ("volumes", "volume"))


@router.post("")
async def offload(body: OffloadIn, session: Session) -> dict[str, Any]:
    if not body.chapters and not body.volumes:
        raise HTTPException(status_code=422, detail="nothing to offload")
    accepted: dict[str, list[dict[str, Any]]] = {"chapters": [], "volumes": []}
    skipped: list[dict[str, Any]] = []
    for key, table in _KINDS:
        items: list[OffloadItem] = getattr(body, key)
        if not items:
            continue
        rows = await session.execute(
            text(f"select id, state, file_path from {table} where id = any(cast(:ids as bigint[]))"),
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
            if reason is not None:
                skipped.append({"id": item.id, "kind": table, "reason": reason})
            else:
                accepted[key].append(item.model_dump())
    queued = len(accepted["chapters"]) + len(accepted["volumes"])
    if queued:
        await repo.enqueue(session, JobType.OFFLOAD, accepted)
        await session.commit()
    return {"queued": queued, "skipped": skipped}
