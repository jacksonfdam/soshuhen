"""The reader: pages, where reading stands, and how a series is shown."""

import asyncio
import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reader_service as service
from app.api.deps import db_session
from app.api.progress_queue import progress_bounds, queue_progress_write
from app.enums import JobType, ProgressSource
from app.handlers.progress_write import forward_only
from app.queue import repo
from app.reader import epub_text

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
            status_code=409,
            detail="this is a light novel chapter; open it in the novel reader",
        ) from exc
    except service.WrongKind as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except epub_text.EpubBroken as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    # Exactly one: a light novel volume is a book with no chapter rows.
    chapter_id: int | None = None
    volume_id: int | None = None
    page: int = Field(ge=0)
    # Prose: how far through the section `page` names.
    fraction: float | None = Field(default=None, ge=0, le=1)
    # Sent by a client replaying reading done offline; the web reader sends none.
    read_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def one_book(self) -> "PositionIn":
        if (self.chapter_id is None) == (self.volume_id is None):
            raise ValueError("name exactly one of chapter_id and volume_id")
        return self


class CompleteIn(BaseModel):
    # When the chapter was finished, from a client replaying offline reading.
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
            session,
            series_id,
            chapter_id=body.chapter_id,
            volume_id=body.volume_id,
            page=body.page,
            fraction=body.fraction,
            read_at=body.read_at,
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
async def complete(
    chapter_id: int, session: Session, body: CompleteIn | None = None
) -> dict[str, bool]:
    """Finishing a chapter here says the same thing finishing it in Komga does.

    A refusal is not an error. Rereading an old chapter, or reading a series on
    no list, must not interrupt the reader; it only moves nothing.
    """
    with service_errors():
        # Prose too: a novel's chapter finished in the novel reader is the
        # same statement as a comic's, and goes to the lists the same way.
        row = await service.chapter(session, chapter_id, prose_ok=True)

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
        await queue_progress_write(
            session,
            row.series_id,
            chapter,
            source=ProgressSource.READER,
            read_at=body.read_at if body else None,
        )

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


@router.post("/volumes/{volume_id}/complete")
async def complete_volume(
    volume_id: int, session: Session, body: CompleteIn | None = None
) -> dict[str, bool]:
    """A light novel volume finished in the novel reader.

    It reaches the lists the way a volume read in Komga does: marked read
    there, then progress_push works out the furthest volume read and pushes it
    only forward. `read_at` is accepted for clients replaying offline reading
    and has nothing to date: the push is dated when it runs.
    """
    del body
    with service_errors():
        book = await service.prose_volume_row(session, volume_id)
    if book.komga_book_id is None:
        # Nothing Komga knows, so nothing progress_push could ever read back.
        return {"progress_queued": False, "komga_queued": False}
    await repo.enqueue(
        session,
        JobType.KOMGA_READ_PROGRESS,
        {"book_id": book.komga_book_id, "push_series_id": book.series_id},
        series_id=book.series_id,
        dedupe_key=f"komga_read_progress:{book.komga_book_id}",
    )
    await session.commit()
    return {"progress_queued": True, "komga_queued": True}


# --- Prose -------------------------------------------------------------------
#
# Reading an EPUB is zip and parser work with no await in it, so it runs in a
# thread: on the loop, a long volume opening would stall every other request
# and the event stream with it.

ProseKind = Literal["chapter", "volume"]


class ProsePrefsIn(BaseModel):
    font_size: int = Field(ge=1, le=7)
    theme: Literal["light", "sepia", "dark"]


def _resource_url(kind: str, book_id: int) -> Any:
    def url(href: str) -> str:
        return f"/api/reader/prose/{kind}/{book_id}/resources/{quote(href)}"

    return url


@router.get("/prose/prefs")
async def prose_prefs(session: Session) -> dict[str, Any]:
    return await service.prose_prefs(session)


@router.put("/prose/prefs")
async def save_prose_prefs(body: ProsePrefsIn, session: Session) -> dict[str, Any]:
    await service.save_prose_prefs(session, body.font_size, body.theme)
    await session.commit()
    return await service.prose_prefs(session)


@router.get("/prose/series/{series_id}/resume")
async def prose_resume(series_id: int, session: Session) -> dict[str, Any]:
    with service_errors():
        return await service.prose_resume(session, series_id)


@router.get("/prose/{kind}/{book_id}")
async def prose_manifest(kind: ProseKind, book_id: int, session: Session) -> dict[str, Any]:
    with service_errors():
        book = await service.prose_book(session, kind, book_id)
        sections = await asyncio.to_thread(epub_text.sections, book.path)
    previous, following = await service.prose_neighbours(session, book)
    return {
        "kind": book.kind,
        "id": book.id,
        "series": {"id": book.series_id, "title": book.series_title},
        "title": book.title,
        "number": float(book.number),
        "edition": book.edition,
        "sections": [{"index": s.index, "title": s.title} for s in sections],
        "previous": previous,
        "next": following,
        "position": await service.prose_position(session, book),
        "prefs": await service.prose_prefs(session),
    }


@router.get("/prose/{kind}/{book_id}/sections/{index}")
async def prose_section(
    kind: ProseKind, book_id: int, index: int, session: Session
) -> dict[str, Any]:
    with service_errors():
        book = await service.prose_book(session, kind, book_id)
        sections = await asyncio.to_thread(epub_text.sections, book.path)
        html = await asyncio.to_thread(
            epub_text.section_html, book.path, index, _resource_url(kind, book_id)
        )
    return {"index": index, "title": sections[index].title, "html": html}


@router.get("/prose/{kind}/{book_id}/resources/{href:path}")
async def prose_resource(kind: ProseKind, book_id: int, href: str, session: Session) -> Response:
    with service_errors():
        book = await service.prose_book(session, kind, book_id)
        try:
            data, media_type = await asyncio.to_thread(epub_text.resource, book.path, href)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="no such image in this book") from exc
    return Response(content=data, media_type=media_type, headers={"Cache-Control": IMMUTABLE})
