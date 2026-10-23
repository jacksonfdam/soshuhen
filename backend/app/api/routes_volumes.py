"""A light novel volume's EPUB as one file, for a client that reads without a network."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.api.routes_chapters import EPUB, library_file

router = APIRouter(prefix="/api/volumes", tags=["volumes"])

Session = Annotated[AsyncSession, Depends(db_session)]


@router.get("/{volume_id}/archive")
async def archive(volume_id: int, session: Session) -> FileResponse:
    row = (
        await session.execute(
            text("select file_path from volume where id = :id"), {"id": volume_id}
        )
    ).first()
    # Closed before the body streams, for the same reason as the chapter
    # archive: a slow copy must not hold a pooled connection for minutes.
    await session.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"volume {volume_id} not found")
    path = library_file(row.file_path)
    if path is None:
        raise HTTPException(status_code=404, detail="volume is not in the library")
    # Range and an ETag from FileResponse, so a cut-off copy resumes onto the
    # same file and a rebuilt volume is copied again.
    return FileResponse(path, media_type=EPUB, filename=path.name)
