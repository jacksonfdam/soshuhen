"""The reader: pages, where reading stands, and how a series is shown."""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reader_service as service
from app.api.deps import db_session
from app.api.progress_queue import progress_bounds, queue_progress_write
from app.enums import JobType, ProgressSource
from app.handlers.progress_write import forward_only
from app.queue import repo

router = APIRouter(prefix="/api/reader", tags=["reader"])

Session = Annotated[AsyncSession, Depends(db_session)]

# A page of a chapter never changes once fetched, and a reader flipping back
# and forth should not ask twice.
IMMUTABLE = "public, max-age=31536000, immutable"

MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
}


@contextmanager
def service_errors() -> Iterator[None]:
    try:
        yield
    except service.ChapterMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="no such page") from exc
    except service.ProseChapter as exc:
        raise HTTPException(
            status_code=409, detail="this is a light novel chapter; read it in Komga"
        ) from exc
    except service.NoMapping as exc:
        raise HTTPException(
            status_code=409, detail="this series has no confirmed source yet"
        ) from exc
    except service.Unavailable as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except service.PageFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _chapter_ref(row: service.ChapterRow) -> dict[str, Any]:
    return {"id": row.id, "number": float(row.number), "title": row.title, "state": row.state}


class PositionIn(BaseModel):
    chapter_id: int
    page: int = Field(ge=0)
    # Sent by a client replaying reading done offline; the web reader sends none.
    read_at: AwareDatetime | None = None


class PrefsIn(BaseModel):
    mode: Literal["paged_ltr", "paged_rtl", "long_strip", "double"]
    scale: Literal["fit_width", "fit_height", "fit_screen"]
    background: Literal["black", "gray", "white"]


@router.get("/chapters/{chapter_id}")
async def manifest(chapter_id: int, session: Session) -> dict[str, Any]:
    with service_errors():
        row = await service.chapter(session, chapter_id)
        origin, count = await service.page_count(session, row)
    previous, following = await service.neighbours(session, row)
    body = {
        "chapter": _chapter_ref(row),
        "series": {"id": row.series_id, "title": row.series_title},
        "origin": origin,
        "page_count": count,
        "previous": previous,
        "next": following,
        "position": await service.position_in(session, row),
        "prefs": await service.effective_prefs(session, row.series_id),
    }
    await session.commit()
    return body


@router.get("/chapters/{chapter_id}/pages/{index}")
async def page(chapter_id: int, index: int, session: Session) -> Response:
    with service_errors():
        row = await service.chapter(session, chapter_id)
        data, extension = await service.serve_page(session, row, index)
    await session.commit()
    return Response(
        content=data,
        media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers={"Cache-Control": IMMUTABLE},
    )


@router.put("/series/{series_id}/position")
async def save_position(series_id: int, body: PositionIn, session: Session) -> dict[str, bool]:
    with service_errors():
        applied = await service.save_position(
            session, series_id, body.chapter_id, body.page, body.read_at
        )
    await session.commit()
    return {"ok": True, "applied": applied}


@router.get("/series/{series_id}/prefs")
async def prefs(series_id: int, session: Session) -> dict[str, Any]:
    return await service.effective_prefs(session, series_id)


@router.put("/series/{series_id}/prefs")
async def save_prefs(series_id: int, body: PrefsIn, session: Session) -> dict[str, Any]:
    if not await service.series_exists(session, series_id):
        raise HTTPException(status_code=404, detail="series not found")
    await service.save_prefs(session, series_id, body.mode, body.scale, body.background)
    await session.commit()
    return await service.effective_prefs(session, series_id)


@router.put("/defaults")
async def save_defaults(body: PrefsIn, session: Session) -> dict[str, bool]:
    await service.save_defaults(session, body.mode, body.scale, body.background)
    await session.commit()
    return {"ok": True}


@router.get("/series/{series_id}/resume")
async def resume(series_id: int, session: Session) -> dict[str, int]:
    with service_errors():
        return await service.resume(session, series_id)


@router.post("/chapters/{chapter_id}/complete")
async def complete(chapter_id: int, session: Session) -> dict[str, bool]:
    """Finishing a chapter here says the same thing finishing it in Komga does.

    A refusal is not an error. Rereading an old chapter, or reading a series on
    no list, must not interrupt the reader; it only moves nothing.
    """
    with service_errors():
        row = await service.chapter(session, chapter_id)

    # Lists count whole chapters. 23.5 finished means 23 is, and 24 is not.
    chapter = math.floor(row.number)
    bounds = await progress_bounds(session, row.series_id)
    # No ceiling here, unlike the progress button. The ceiling counts chapter
    # rows to catch a mistyped number; a chapter someone just finished reading
    # exists, and a source listing only chapters 100 to 120 has 21 rows.
    progress_queued = (
        bounds.has_entries
        and chapter >= 1
        and forward_only(bounds.current, chapter) is not None
    )
    if progress_queued:
        await queue_progress_write(session, row.series_id, chapter, source=ProgressSource.READER)

    komga_queued = False
    if row.komga_book_id is not None:
        await repo.enqueue(
            session,
            JobType.KOMGA_READ_PROGRESS,
            {"book_id": row.komga_book_id},
            series_id=row.series_id,
            dedupe_key=f"komga_read_progress:{row.komga_book_id}",
        )
        komga_queued = True

    await session.commit()
    return {"progress_queued": progress_queued, "komga_queued": komga_queued}
