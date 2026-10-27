"""Gadgetized Panda Translation (gadgetizedpanda.net).

A translator's WordPress blog, read through the WordPress REST API rather than
its pages. The hand-kept index post the blog links each series from is the
wrong list: it holds the web novel and the blog's own light novel translation
on one page, numbered from one each, links chapters already free on the blog
to Ko-fi, and parsing it picks up the sidebar's recent posts. A series'
category is the list the blog itself maintains, so a mapping's URL is the
category page, and a paywalled chapter simply has no post there yet.
"""

import html
import re
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser, Node

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

SITE = "gadgetizedpanda"
BASE_URL = "https://gadgetizedpanda.net"
API = "/wp-json/wp/v2"
# The API's own ceiling for one page of a collection.
PER_PAGE = 100

_CHAPTER = re.compile(r"\bchapter\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_VOLUME = re.compile(r"\bvolume\s*(\d+)", re.IGNORECASE)


def _plain(rendered: str | None) -> str:
    return " ".join(html.unescape(rendered or "").replace("\xa0", " ").split())


def _starts_footer(node: Node) -> bool:
    """The first spacer or separator block ends the story.

    Every chapter closes the same way: a spacer, then translator notes, the
    previous/next links and the Ko-fi plea between separators. Scene breaks
    inside the story are star paragraphs, never these blocks.
    """
    classes = (node.attributes.get("class") or "").split()
    return (node.tag == "div" and "wp-block-spacer" in classes) or (
        node.tag == "hr" and "wp-block-separator" in classes
    )


def _cut_footer(box: Node) -> None:
    cut = False
    for child in list(box.iter(include_text=True)):
        cut = cut or _starts_footer(child)
        if cut:
            child.decompose()


class GadgetizedPandaSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("gadgetizedpanda.net",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        # Category names are the blog's own ("web novel geek mob"), so no one
        # spelling of a title is likely to be a substring of them; each is asked.
        queries = list(dict.fromkeys(t.strip() for t in titles if t and t.strip()))[:3]
        found: dict[int, dict] = {}
        for query in queries:
            response = await self.client.get(
                f"{API}/categories",
                params={"search": query, "per_page": 20, "_fields": "id,name,count,link"},
            )
            response.raise_for_status()
            for item in response.json():
                found.setdefault(item.get("id"), item)
        return self.parse_search(list(found.values()), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        slug = self.category_slug(url)
        response = await self.client.get(f"{API}/categories", params={"slug": slug, "_fields": "id"})
        response.raise_for_status()
        categories = response.json()
        if not categories:
            raise ChapterUnavailable(f"Gadgetized Panda has no category {slug!r}")
        category = categories[0]["id"]

        posts: list[dict] = []
        page, pages = 1, 1
        while page <= pages:
            response = await self.client.get(
                f"{API}/posts",
                params={
                    "categories": category,
                    "per_page": PER_PAGE,
                    "page": page,
                    "orderby": "date",
                    "order": "asc",
                    "_fields": "slug,link,title",
                },
            )
            response.raise_for_status()
            posts.extend(response.json())
            pages = int(response.headers.get("X-WP-TotalPages", "1"))
            page += 1
        return self.parse_chapters(posts)

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        slug = urlsplit(chapter_url).path.rstrip("/").rsplit("/", 1)[-1]
        response = await self.client.get(
            f"{API}/posts", params={"slug": slug, "_fields": "title,content"}
        )
        post = None
        if response.status_code == 200:
            try:
                found = response.json()
            except ValueError:
                # A security plugin answering the API with its own HTML page.
                found = None
            if isinstance(found, list) and found:
                post = found[0]
        if post is not None:
            return self.parse_chapter(post["content"]["rendered"], chapter_url)

        # The API refused, or does not know the post: the page decides whether
        # the chapter is gone.
        page = await self.client.get(chapter_url)
        if page.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        page.raise_for_status()
        return self.parse_chapter_page(page.text, chapter_url)

    def category_slug(self, url: str) -> str:
        segments = [s for s in urlsplit(url).path.split("/") if s]
        if "category" not in segments or segments[-1] == "category":
            raise ChapterUnavailable(
                f"{url} is not a Gadgetized Panda category address - map the series' category page"
            )
        # Categories nest (/category/translation/spacemob/geek-mob/); the last
        # segment is the series' own.
        return segments[-1]

    def parse_search(self, payload: list, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload or []:
            name = _plain(item.get("name"))
            link = item.get("link")
            if not name or not link:
                continue
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=link,
                    title=name,
                    chapter_count=item.get("count"),
                    score=round(max((best_similarity([name], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, posts: list[dict]) -> list[ChapterRef]:
        found: list[tuple[Decimal, str | None, str]] = []
        for post in posts:
            title = _plain((post.get("title") or {}).get("rendered"))
            match = _CHAPTER.search(title)
            link = post.get("link")
            # The index page and the illustration post share the category.
            if match is None or not link:
                continue
            volume = _VOLUME.search(title)
            found.append((Decimal(match.group(1)), volume.group(1) if volume else None, link))

        printed = [number for number, _, _ in found]
        # The blog's other series restart numbering every volume and split
        # chapters into parts. Two chapters numbered 1 would collide on the
        # (series, number) the pipeline keys chapters by, so a series whose
        # printed numbers repeat is numbered by position instead.
        by_position = len(set(printed)) != len(printed)
        return [
            ChapterRef(
                number=Decimal(index + 1) if by_position else number,
                url=link,
                volume=volume,
            )
            for index, (number, volume, link) in enumerate(found)
        ]

    def parse_chapter(self, content: str, chapter_url: str) -> ChapterText:
        box = HTMLParser(content).body
        if box is None:
            raise ChapterUnavailable(f"{chapter_url} has no chapter text")
        return self._chapter(box, chapter_url)

    def parse_chapter_page(self, page: str, chapter_url: str) -> ChapterText:
        box = HTMLParser(page).css_first(".entry-content")
        if box is None:
            raise ChapterUnavailable(f"{chapter_url} has no chapter text")
        return self._chapter(box, chapter_url)

    def _chapter(self, box: Node, chapter_url: str) -> ChapterText:
        _cut_footer(box)
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
