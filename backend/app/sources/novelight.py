"""Novelight (novelight.net).

Two things about this site shape everything below. Chapter text is never in
the page: the reader fetches it from an AJAX endpoint after load, and that
endpoint - like the chapter list - answers 403 without X-Requested-With.
And chapter numbers restart in every volume, so the number a title shows is
not unique within a book; the position in the full list is.
"""

import re
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    ChapterUnavailable,
    PageRef,
    ProseSource,
)
from app.sources.net import CatalogueRow, get_client
from app.sources.prose import clean_chapter_html
from app.text_utils import best_similarity

SITE = "novelight"
BASE_URL = "https://novelight.net"
AJAX = {"X-Requested-With": "XMLHttpRequest"}

_BOOK_ID = re.compile(r'const BOOK_ID = "(\d+)"')
_CHAPTER_ID = re.compile(r"/book/chapter/(\d+)")
_VOLUME = re.compile(r"^\s*(\d+)\s*vol\.", re.IGNORECASE)


class NovelightSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("novelight.net",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get("/catalog/", params={"search": query})
        response.raise_for_status()
        return self.parse_search(response.text, titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        page = await self.client.get(url)
        page.raise_for_status()
        book_id = self.parse_book_id(page.text)
        # pagination=0 is the whole list in one answer; without it the
        # endpoint pages by fifty.
        response = await self.client.get(
            "/book/ajax/chapter-pagination",
            params={"book_id": book_id, "page": 1, "pagination": 0},
            headers=AJAX,
        )
        response.raise_for_status()
        return self.parse_chapters(response.json()["html"])

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        match = _CHAPTER_ID.search(chapter_url)
        if match is None:
            raise ChapterUnavailable(f"{chapter_url} is not a Novelight chapter address")
        response = await self.client.get(
            f"/book/ajax/read-chapter/{match.group(1)}",
            headers={**AJAX, "Referer": chapter_url},
        )
        if response.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        response.raise_for_status()
        return self.parse_chapter(response.json()["content"], chapter_url)

    def parse_book_id(self, html: str) -> str:
        match = _BOOK_ID.search(html)
        if match is None:
            raise ChapterUnavailable("the book page no longer names its BOOK_ID")
        return match.group(1)

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in HTMLParser(html).css(".manga-grid-list a.item"):
            href = item.attributes.get("href")
            label = item.css_first(".title")
            title = " ".join(label.text().split()) if label else ""
            if not href or not title:
                continue
            image = item.css_first("img")
            cover = image.attributes.get("src") if image else None
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=urljoin(BASE_URL, href),
                    title=title,
                    cover_url=urljoin(BASE_URL, cover) if cover else None,
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        links = HTMLParser(html).css("a.chapter")
        chapters: list[ChapterRef] = []
        # The list arrives newest first; numbering runs from the oldest.
        for link in reversed(links):
            href = link.attributes.get("href")
            if not href:
                continue
            label = link.css_first(".title")
            name = label.css_first("span") if label else None
            volume = _VOLUME.match(label.text()) if label else None
            chapters.append(
                ChapterRef(
                    # Position, not the printed number: numbers restart every
                    # volume, and two chapters numbered 12 would collide on
                    # the (series, number) the pipeline keys chapters by.
                    number=Decimal(len(chapters) + 1),
                    url=urljoin(BASE_URL, href),
                    title=" ".join(name.text().split()) if name else None,
                    volume=volume.group(1) if volume else None,
                )
            )
        return chapters

    def parse_chapter(self, content: str, chapter_url: str) -> ChapterText:
        tree = HTMLParser(content)
        box = tree.css_first(".chapter-text")
        # A locked chapter answers 200 with the text container left empty.
        if box is None or not box.text().strip():
            raise ChapterUnavailable(f"{chapter_url} is locked or empty on Novelight")
        for junk in box.css(".advertisment, script"):
            junk.decompose()
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
