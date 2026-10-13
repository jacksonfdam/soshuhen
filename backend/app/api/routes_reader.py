"""The reader: pages, where reading stands, and how a series is shown."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reader_service as service
from app.api.deps import db_session

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


@router.get("/chapters/{chapter_id}")
async def manifest(chapter_id: int, session: Session) -> dict[str, Any]:
    with service_errors():
        row = await service.chapter(session, chapter_id)
        origin, count = await service.page_count(session, row)
    await session.commit()
    return {
        "chapter": _chapter_ref(row),
        "series": {"id": row.series_id, "title": row.series_title},
        "origin": origin,
        "page_count": count,
    }


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
