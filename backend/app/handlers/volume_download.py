"""Download one owned volume, exactly as J-Novel Club serves it.

The link is read fresh from the library every time: it carries its own
authorisation, J-Novel Club asks that it not be stored, and one read hours ago
may have lapsed. The file is placed untouched - its number and position in
Komga are set through Komga's API, never by rewriting the publisher's EPUB.
"""

import os
import tempfile
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.downloader.cbz import place_file
from app.downloader.epub import is_epub
from app.downloader.paths import volume_number_from_filename, volume_path
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.sources.base import SignInRequired, get_prose_source

SITE = "jnovelclub"


async def _set_state(ctx: JobContext, volume_id: int, state: str) -> None:
    await ctx.session.execute(
        text("update volume set state = :state where id = :id"), {"state": state, "id": volume_id}
    )
    await ctx.session.commit()


@register(JobType.VOLUME_DOWNLOAD)
async def handle(ctx: JobContext) -> None:
    volume_id = int(ctx.payload["volume_id"])
    row = (
        await ctx.session.execute(
            text(
                """
                select v.id, v.series_id, v.number, v.source_volume_id, v.title, v.file_path,
                       v.last_updated, s.slug
                  from volume v join series s on s.id = v.series_id
                 where v.id = :id
                """
            ),
            {"id": volume_id},
        )
    ).first()
    if row is None:
        raise PermanentError(f"volume {volume_id} no longer exists")
    await _set_state(ctx, volume_id, "downloading")

    try:
        await _download(ctx, row, volume_id)
    except BaseException:
        # Whatever went wrong - the library, the disk, the database - the row
        # must not keep saying downloading with no job behind it; the next
        # sync queues it again, and the retry ladder still runs this job.
        await ctx.session.rollback()
        await _set_state(ctx, volume_id, "known")
        raise


async def _download(ctx: JobContext, row, volume_id: int) -> None:
    source = get_prose_source(SITE)
    try:
        owned = await source.library()
    except SignInRequired as exc:
        await _set_state(ctx, volume_id, "known")
        raise PermanentError(str(exc)) from exc

    entry = next((v for v in owned if v.volume_id == row.source_volume_id), None)
    if entry is None or entry.epub_link is None:
        await _set_state(ctx, volume_id, "known")
        reason = "is no longer in your J-Novel Club library" if entry is None else (
            "has no EPUB download"
        )
        raise PermanentError(f"volume {row.number} {reason}")

    data = await source.fetch_volume(entry.epub_link)
    if not is_epub(data):
        raise RuntimeError(f"J-Novel Club's answer for volume {row.number} is not an EPUB")

    title = entry.title or row.title
    destination = volume_path(Path(get_settings().library_path), row.slug, row.number, title)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, scratch_name = tempfile.mkstemp(dir=destination.parent, suffix=".epub.part")
    with os.fdopen(handle_fd, "wb") as scratch:
        scratch.write(data)
    await place_file(Path(scratch_name), destination)
    # A revision whose title changed lands under a new name; the previous file
    # is that same volume's older edition, and it goes only once the new one
    # is in place.
    if row.file_path and row.file_path != str(destination):
        previous = Path(row.file_path)
        # Only ever this volume's own earlier file: same folder, and a name that
        # reads back as this volume. Anything else stays, whatever the row says.
        if (
            previous.parent == destination.parent
            and volume_number_from_filename(previous.name) == row.number
        ):
            previous.unlink(missing_ok=True)

    await ctx.session.execute(
        text(
            """
            update volume
               set state = 'downloaded', file_path = :path, title = :title,
                   downloaded_updated = coalesce(cast(:updated as timestamptz), now())
             where id = :id
            """
        ),
        {
            "id": volume_id,
            "path": str(destination),
            "title": title,
            "updated": entry.last_updated or row.last_updated,
        },
    )
    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": row.series_id},
        series_id=row.series_id,
        dedupe_key=f"komga_scan:{row.series_id}",
    )
    await ctx.session.commit()
    await ctx.log(f"saved volume {row.number}", pct=100)
