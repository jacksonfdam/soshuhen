"""Give back to `known` what the database says is on disk and is not.

Nothing else notices an archive that disappears outside the pipeline: a
folder removed by hand, a restore that left a series out. The row stays
`downloaded` for good, the web interface shows a chapter it cannot open, a
phone copying it gets a 404, and nothing ever downloads it again. On one
server 757 chapters across six series sat like that, Gin Tama's whole folder
among them.

`known` is the honest state: missing locally. Nothing downloads it by itself
unless the series has auto_download set; "Download range" brings it back.
"""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.downloader.paths import ARCHIVE_SUFFIXES
from app.enums import JobType
from app.handlers.base import JobContext, register

log = logging.getLogger(__name__)


def _holds_an_archive(library: Path) -> bool:
    return library.is_dir() and any(p.suffix in ARCHIVE_SUFFIXES for p in library.rglob("*"))


async def _gone(session: AsyncSession, table: str) -> list[int]:
    rows = await session.execute(
        text(f"select id, file_path from {table} where state = 'downloaded' and file_path is not null")
    )
    return [row.id for row in rows if not Path(row.file_path).is_file()]


async def forget_missing(session: AsyncSession, library: Path) -> tuple[int, int] | None:
    """(chapters, volumes) set back to `known`, or None when the library looked unmounted.

    An unmounted volume is an empty folder, and believing it would mark the
    whole library as missing; `verify_library_mount` reasons the same way.
    """
    if not _holds_an_archive(library):
        return None
    chapters = await _gone(session, "chapter")
    volumes = await _gone(session, "volume")
    if chapters:
        await session.execute(
            text(
                "update chapter set state = 'known', file_path = null, komga_book_id = null"
                " where id = any(:ids) and state = 'downloaded'"
            ),
            {"ids": chapters},
        )
    if volumes:
        await session.execute(
            text(
                "update volume set state = 'known', file_path = null, komga_book_id = null"
                " where id = any(:ids) and state = 'downloaded'"
            ),
            {"ids": volumes},
        )
    return len(chapters), len(volumes)


@register(JobType.LIBRARY_AUDIT)
async def handle(ctx: JobContext) -> None:
    result = await forget_missing(ctx.session, Path(get_settings().library_path))
    await ctx.session.commit()
    if result is None:
        log.warning("library audit skipped: no archive found under the library, is it mounted?")
        return
    chapters, volumes = result
    log.info("library audit: %d chapters and %d volumes missing from disk, now known", chapters, volumes)
