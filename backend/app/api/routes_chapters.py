"""A chapter's archive as one file, for a client that reads without a network.

The reader serves pages one at a time, which is right for reading here and no
use to a phone that has to keep reading on a train.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reader_service as service
from app.api.deps import db_session
from app.api.routes_reader import service_errors

router = APIRouter(prefix="/api/chapters", tags=["chapters"])

Session = Annotated[AsyncSession, Depends(db_session)]


@router.get("/{chapter_id}/archive")
async def archive(chapter_id: int, session: Session) -> FileResponse:
    with service_errors():
        row = await service.chapter(session, chapter_id)
    path = service.archive_of(row)
    # The request's session would otherwise keep its connection, idle in a
    # transaction, until the last byte is sent. A copy over weak Wi-Fi takes
    # minutes, and a few of them in parallel empty the pool for everyone.
    await session.close()
    if path is None:
        raise HTTPException(status_code=404, detail="chapter is not in the library")
    # FileResponse answers Range, so a copy cut off by weak Wi-Fi resumes, and
    # its ETag changes when the archive is rebuilt, so the client copies again.
    return FileResponse(path, media_type="application/vnd.comicbook+zip", filename=path.name)
