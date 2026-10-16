"""fetch_prose_chapter fetches the text and every image the text references."""

import httpx

from app.downloader.prose_fetch import fetch_prose_chapter
from app.sources.base import ChapterText, PageRef, ProseSource
from app.sources.net import CatalogueRow, SiteClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class Fake(ProseSource):
    site = "fake"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        return ChapterText(
            title="T",
            body="<p>{{img:0}}</p>",
            images=[PageRef(url="https://img.test/a.png", headers={"Referer": chapter_url})],
        )


async def test_images_are_fetched_with_their_referer():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    client = SiteClient(
        CatalogueRow(key="fake-prose-fetch", base_url="https://site.test"),
        transport=httpx.MockTransport(handler),
    )
    text, images = await fetch_prose_chapter(Fake(), "https://site.test/c/1", client)
    assert text.title == "T"
    assert images == [PNG]
    assert seen[0].headers["referer"] == "https://site.test/c/1"


async def test_a_chapter_without_images_makes_no_requests():
    class NoImages(Fake):
        async def fetch_chapter(self, chapter_url, *, language="en"):
            return ChapterText(title=None, body="<p>x</p>", images=[])

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = SiteClient(
        CatalogueRow(key="fake-prose-none", base_url="https://site.test"),
        transport=httpx.MockTransport(handler),
    )
    _, images = await fetch_prose_chapter(NoImages(), "https://site.test/c/1", client)
    assert images == []
