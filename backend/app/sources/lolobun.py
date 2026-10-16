"""LoLoBun (lolobun.com), the English storefront of SF Light Novel.

An official, paid platform: the web serves the first chapters of a book and
locks the rest behind its app and coins. Locked chapters are listed like any
other and refused when fetched, so they land as `skipped` with a reason
rather than vanishing from the series.
"""

from decimal import Decimal
from typing import ClassVar

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

SITE = "lolobun"
BASE_URL = "https://www.lolobun.com"


class LolobunSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("lolobun.com",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            "/ajax/Common.ashx",
            params={"op": "getSearchSuggest", "keyword": query},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        response = await self.client.get(url)
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        response = await self.client.get(chapter_url)
        if response.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        response.raise_for_status()
        return self.parse_chapter(response.text, chapter_url)

    def parse_search(self, payload: dict, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload.get("data") or []:
            # The suggest endpoint mixes the storefront's comics in with its
            # novels, often under the very same title.
            if item.get("EntityType") != "Novel":
                continue
            title = (item.get("Title") or "").strip()
            url = item.get("Url") or ""
            if not title or not url.startswith("/n/"):
                continue
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{BASE_URL}{url}",
                    title=title,
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        # Volume by volume rather than one selector over headings and items:
        # selectolax returns a comma selector's matches grouped by selector,
        # not in document order, which would detach every chapter from its
        # volume.
        for block in HTMLParser(html).css(".catalog-volume"):
            heading = block.css_first(".catalog-volume-title")
            volume = " ".join(heading.text().split()) if heading else None
            for item in block.css(".catalog-item"):
                link = item.css_first(".title a[href]")
                if link is None:
                    continue
                # Position, not the title: early chapters spell their numbers
                # out ("Chapter Three: ...") and later ones drop punctuation,
                # while the catalogue order is the one thing the site keeps
                # consistent.
                chapters.append(
                    ChapterRef(
                        number=Decimal(len(chapters) + 1),
                        url=f"{BASE_URL}{link.attributes['href']}",
                        title=" ".join(link.text().split()) or None,
                        volume=volume or None,
                    )
                )
        return chapters

    def parse_chapter(self, html: str, chapter_url: str) -> ChapterText:
        tree = HTMLParser(html)
        # A locked chapter still answers 200 and still fills the text box - with
        # a teaser of its first lines. Shipping that as the chapter would look
        # like a working download. The purchase panel is the one element that
        # differs: present on every page, hidden only when the chapter is free.
        purchase = tree.css_first(".order-vip-container")
        if purchase is not None and "hidden" not in (purchase.attributes.get("class") or "").split():
            raise ChapterUnavailable(f"{chapter_url} is locked to the LoLoBun app")
        box = tree.css_first(".text-content-box")
        if box is None:
            raise ChapterUnavailable(f"{chapter_url} has no chapter text")
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
