"""The prose half of the download handlers.

download_batch and download_chapter keep everything around the archive write -
leasing, batching, the unavailable/failed bookkeeping, the Komga scan after -
and branch only here, so a light novel chapter is retried, skipped and
requeued by exactly the rules a manga chapter is.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from app.downloader.epub import EpubChapter, write_epub
from app.downloader.prose_fetch import fetch_prose_chapter
from app.handlers.base import JobContext
from app.handlers.download_chapter import build_comicinfo
from app.handlers.komga_scan import fetch_series_artwork
from app.sources.base import ProseSource
from app.sources.net import SiteClient


async def cover_for(ctx: JobContext, series_id: int) -> bytes | None:
    """The series cover, or None. Never a reason to fail a chapter.

    Komga takes each book's thumbnail from the EPUB's cover-image, and a scraped
    chapter has no art of its own - but a provider CDN being down for a minute
    is not worth a chapter, so any failure here just ships it without one.
    """
    try:
        return await fetch_series_artwork(ctx, series_id)
    except httpx.HTTPError as exc:
        await ctx.log(f"cover unavailable, chapters ship without one: {exc}", level="warning")
        return None


async def write_prose_chapter(
    ctx: JobContext,
    row: dict[str, Any],
    source: ProseSource,
    client: SiteClient,
    cover: bytes | None,
    destination: Path,
) -> None:
    text, images = await fetch_prose_chapter(source, row["chapter_url"], client)
    # ComicInfo's fields are the series metadata this pipeline already
    # resolves from every provider; the EPUB carries the same answers.
    info = await build_comicinfo(ctx.session, row)
    number = Decimal(str(row["number"]))
    await write_epub(
        EpubChapter(
            series=row["canonical_title"],
            number=number,
            identifier=f"soshuhen:{row['series_id']}:{number.normalize()}",
            title=row["title"] or text.title,
            body=text.body,
            images=images,
            cover=cover,
            authors=[info.writer] if info.writer else [],
            summary=info.summary,
        ),
        destination,
    )
