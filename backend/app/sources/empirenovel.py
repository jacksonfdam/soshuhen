"""EmpireNovel (empirenovel.com).

Behind a Cloudflare challenge. Nothing here deals with it: SiteClient detects
the challenge and replays FlareSolverr's clearance, so without the
`flaresolverr` profile this source fails exactly the way every other
challenged site does.

The chapter number is the last segment of the chapter URL, and the site is
not careful with it - one book carries both /01 and /1, another skips numbers
that then 404. The first URL for a number wins, and a gap stays a gap.
"""

import re
from decimal import Decimal, InvalidOperation
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

SITE = "empirenovel"
BASE_URL = "https://www.empirenovel.com"


def _other_names(raw) -> list[str]:
    # The payload carries one string ("a, b" or "a | b"); iterating it as a
    # list used to turn a name into single characters.
    if isinstance(raw, str):
        raw = re.split(r"[,|]", raw)
    if not isinstance(raw, list):
        return []
    return [n.strip() for n in raw if isinstance(n, str) and n.strip()]


class EmpireNovelSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("empirenovel.com",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        # The typeahead endpoint is the only search that honours the query;
        # /novels-list ignores its search parameter.
        response = await self.client.get("/search-live", params={"q": query})
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        page = await self.client.get(url)
        page.raise_for_status()
        first = self.parse_first_chapter(page.text)
        # The chapter dropdown is the whole list in one request, where the
        # book page pages by thirty. It is served relative to any chapter that
        # exists, which is why the first one is read off the book page.
        response = await self.client.get(f"/select-partial{first.removeprefix(BASE_URL)}")
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        response = await self.client.get(chapter_url)
        if response.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        response.raise_for_status()
        return self.parse_chapter(response.text, chapter_url)

    def parse_search(self, payload: list, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload or []:
            slug = item.get("slug")
            title = (item.get("name") or "").strip()
            if not slug or not title:
                continue
            others = _other_names(item.get("otherNames"))
            names = [title, *others]
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{BASE_URL}/novel/{slug}",
                    title=title,
                    # The payload only says whether a cover exists; the path
                    # is the one the book page itself uses.
                    cover_url=(
                        f"{BASE_URL}/uploads/novel/{slug}/cover/cover_250x350.jpg"
                        if item.get("cover")
                        else None
                    ),
                    alt_titles=others,
                    score=round(max((best_similarity(names, t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_first_chapter(self, html: str) -> str:
        for link in HTMLParser(html).css(".col-6.text-center a[href]"):
            href = link.attributes["href"]
            if "/novel/" in href:
                return urljoin(BASE_URL, href)
        raise ChapterUnavailable("the book page links to no chapter")

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        seen: set[Decimal] = set()
        chapters: list[ChapterRef] = []
        # Newest first in the dropdown; reading it oldest first makes "first
        # URL wins" mean the lower, original address.
        for option in reversed(HTMLParser(html).css("select#chapter-list option")):
            value = option.attributes.get("value") or ""
            try:
                number = Decimal(value.rstrip("/").rsplit("/", 1)[-1])
            except InvalidOperation:
                continue
            if number in seen:
                continue
            seen.add(number)
            chapters.append(ChapterRef(number=number, url=urljoin(BASE_URL, value)))
        return chapters

    def parse_chapter(self, html: str, chapter_url: str) -> ChapterText:
        box = HTMLParser(html).css_first("#read-novel")
        if box is None:
            raise ChapterUnavailable(f"{chapter_url} has no chapter text")
        # The heading, the next-chapter link row and the reader footer all sit
        # inside the text container as divs and an h3. css() on a node also
        # matches the node itself, so the container is skipped by identity.
        for junk in box.css("div, h3"):
            if junk.attributes.get("id") != "read-novel":
                junk.decompose()
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
