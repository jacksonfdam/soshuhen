"""Importing PDFs a user owns into a prose series.

The preview answers with a plan and writes nothing; the confirmation queues the
write on the download lane, the only process that may write /manga. Both read
the same staged files through the same code, so what was reviewed is what lands.
"""

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.downloader.epub import is_epub
from app.enums import JobType
from app.importer import staging
from app.importer.plan import Existing, Override, PlannedFile
from app.importer.reading import build_plan, sha256_of
from app.queue import repo

router = APIRouter(prefix="/api/series", tags=["import"])

Session = Annotated[AsyncSession, Depends(db_session)]

# Twenty volumes of a novel are about 200 MB; a drop past that is not one book.
_MAX_DROP_BYTES = 200 * 1024 * 1024


async def import_target(session: AsyncSession, series_id: int) -> tuple[str, Existing]:
    row = (
        await session.execute(
            text("select slug, kind from series where id = :id"), {"id": series_id}
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no such series")
    if row.kind != "prose":
        raise HTTPException(status_code=409, detail="import is for prose series")
    chapters = (
        await session.execute(
            text("select number from chapter where series_id = :id"), {"id": series_id}
        )
    ).scalars()
    volumes = (
        await session.execute(
            text("select number, edition from volume where series_id = :id"), {"id": series_id}
        )
    ).all()
    return row.slug, Existing(
        chapters=frozenset(Decimal(str(n)) for n in chapters),
        volumes=frozenset((Decimal(str(v.number)), v.edition) for v in volumes),
    )


def planned_json(item: PlannedFile) -> dict[str, Any]:
    return {
        "name": item.name,
        "sha256": item.sha256,
        "volume": str(item.volume) if item.volume is not None else None,
        "edition": item.edition,
        "chapters": [str(n) for n in item.chapters],
        "outputs": item.outputs,
        "status": item.status,
        "reason": item.reason,
    }


def parse_overrides(raw: dict[str, Any]) -> dict[str, Override]:
    overrides: dict[str, Override] = {}
    for sha256, value in raw.items():
        try:
            volume = Decimal(str(value["volume"])) if value.get("volume") is not None else None
        except (InvalidOperation, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"volume for {sha256} is not a number") from exc
        edition = value.get("edition")
        if edition not in (None, "web", "light"):
            raise HTTPException(status_code=422, detail=f"edition for {sha256} is not web or light")
        overrides[sha256] = Override(volume=volume, edition=edition, replace=bool(value.get("replace")))
    return overrides


@router.post("/{series_id}/import")
async def preview(series_id: int, files: list[UploadFile], session: Session) -> dict[str, Any]:
    slug, existing = await import_target(session, series_id)
    received: list[tuple[str, str, bytes]] = []
    total = 0
    for upload in files:
        # Starlette has already spooled the file to disk and knows its size;
        # checking first keeps an oversized drop out of this process's memory.
        total += upload.size or 0
        if total > _MAX_DROP_BYTES:
            raise HTTPException(status_code=413, detail="the drop is over 200 MB")
        data = await upload.read()
        if not (data.startswith(b"%PDF-") or is_epub(data)):
            raise HTTPException(status_code=415, detail=f"{upload.filename} is not a PDF or an EPUB")
        received.append((upload.filename or "unnamed.pdf", sha256_of(data), data))
    await session.close()

    # Parsing twenty books takes seconds; the event loop keeps serving meanwhile.
    planned, _ = await asyncio.to_thread(build_plan, slug, received, existing, {})
    token = await asyncio.to_thread(staging.stage, received)
    return {"token": token, "files": [planned_json(item) for item in planned]}


@router.post("/{series_id}/import/{token}", status_code=202)
async def confirm(
    series_id: int,
    token: str,
    session: Session,
    files: Annotated[dict[str, dict[str, Any]], Body(embed=True)],
) -> dict[str, Any]:
    slug, existing = await import_target(session, series_id)
    overrides = parse_overrides(files)
    received = await asyncio.to_thread(staging.staged, token)
    if received is None:
        raise HTTPException(status_code=410, detail="upload again")
    planned, _ = await asyncio.to_thread(build_plan, slug, received, existing, overrides)
    if not any(item.status == "ready" for item in planned):
        raise HTTPException(status_code=409, detail="nothing in this drop can be imported")
    # Pin what the user reviewed. Unprefixed, a file's edition is guessed from the
    # chapters the series holds, and a retry after the first volume landed would
    # guess light for a web volume and write the wrong book.
    overrides = {
        item.sha256: Override(
            volume=item.volume,
            edition=item.edition,
            replace=overrides.get(item.sha256, Override()).replace,
        )
        for item in planned
    }

    job_id = await repo.enqueue(
        session,
        JobType.IMPORT_FILES,
        {
            "series_id": series_id,
            "token": token,
            "overrides": {
                sha: {
                    "volume": str(o.volume) if o.volume is not None else None,
                    "edition": o.edition,
                    "replace": o.replace,
                }
                for sha, o in overrides.items()
            },
        },
        series_id=series_id,
        dedupe_key=f"import_files:{token}",
        # A failed write leaves its job to be read in the queue; the files and
        # the rows are idempotent per volume, so a retry finishes what is left.
        max_attempts=3,
    )
    await session.commit()
    return {"job_id": job_id, "files": [planned_json(item) for item in planned]}
