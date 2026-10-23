"""A chapter's archive as one file, for a client that reads without a network.

The reader serves pages one at a time, which is right for reading here and no
use to a phone that has to keep reading on a train.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.config import get_settings
from app.reader import archive as reader_archive

router = APIRouter(prefix="/api/chapters", tags=["chapters"])

Session = Annotated[AsyncSession, Depends(db_session)]

CBZ = "application/vnd.comicbook+zip"
EPUB = "application/epub+zip"


def library_file(file_path: str | None) -> Path | None:
    """The stored file, only when it exists and really sits inside the library."""
    if file_path is None:
        return None
    path = Path(file_path)
    if not path.is_file() or not reader_archive.inside(path, get_settings().library_path):
        return None
    return path


@router.get("/{chapter_id}/archive")
async def archive(chapter_id: int, session: Session) -> FileResponse:
    # Read here rather than through the reader's chapter lookup, which refuses
    # prose: the reader cannot page an EPUB, but a phone can still copy one.
    row = (
        await session.execute(
            text(
                "select c.file_path, s.kind from chapter c"
                " join series s on s.id = c.series_id where c.id = :id"
            ),
            {"id": chapter_id},
        )
    ).first()
    # The request's session would otherwise keep its connection, idle in a
    # transaction, until the last byte is sent. A copy over weak Wi-Fi takes
    # minutes, and a few of them in parallel empty the pool for everyone.
    await session.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"chapter {chapter_id} not found")
    path = library_file(row.file_path)
    if path is None:
        raise HTTPException(status_code=404, detail="chapter is not in the library")
    # FileResponse answers Range, so a copy cut off by weak Wi-Fi resumes, and
    # its ETag changes when the archive is rebuilt, so the client copies again.
    media_type = EPUB if row.kind == "prose" else CBZ
    return FileResponse(path, media_type=media_type, filename=path.name)
