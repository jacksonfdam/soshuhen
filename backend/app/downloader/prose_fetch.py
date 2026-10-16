"""Fetch one prose chapter: its text from the source, its images like pages.

Images go through fetch_pages rather than a fetch of their own, so they obey
the site's rate limit, carry the referer the source attached, and are checked
for being images at all - the same sites that answer a hotlinked comic page
with 200 text/html do the same to an illustration.
"""

from app.downloader.fetcher import fetch_pages
from app.sources.base import ChapterText, ProseSource
from app.sources.net import SiteClient


async def fetch_prose_chapter(
    source: ProseSource, chapter_url: str, client: SiteClient
) -> tuple[ChapterText, list[bytes]]:
    text = await source.fetch_chapter(chapter_url)
    images = await fetch_pages(client, text.images) if text.images else []
    return text, images
