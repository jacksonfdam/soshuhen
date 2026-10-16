"""J-Novel Club (j-novel.club): pre-publication parts of licensed light novels.

A publisher, not an aggregator. Its catalogue answers without signing in; a
part's text needs the Premium member's token (sources/jnovel_auth.py). Every
part's XHTML carries a note asking that it not be turned into EPUBs - the user
chose to, for personal reading, knowing that (see the design spec).

Part numbers already run across the whole series (The Apothecary Diaries
volume 16 is parts 204-216), so they are the chapter numbers as they come.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    ChapterUnavailable,
    NotConfigured,
    PageRef,
    ProseSource,
    SignInRequired,
)
from app.sources.jnovel_auth import TokenKeeper
from app.sources.net import CatalogueRow, get_client
from app.sources.prose import clean_chapter_html
from app.text_utils import best_similarity

SITE = "jnovelclub"
API_BASE = "https://labs.j-novel.club"
WEB_BASE = "https://j-novel.club"
JSON = {"format": "json"}
# The page size the web app asks the library for.
LIBRARY_PAGE = 100

_SERIES_SLUG = re.compile(r"/series/([^/?#]+)")
_PART_SLUG = re.compile(r"/read/([^/?#]+)")

# J-Novel Club's own words for each refusal, so a skipped chapter says why.
REFUSALS = {
    402: "needs a purchase on J-Novel Club",
    403: "needs a J-Novel Club membership, or the sign-in no longer grants it",
    404: "is gone from J-Novel Club",
    410: "has expired on J-Novel Club",
    451: "is not available in your region",
}


def expires_at(publishing: datetime) -> datetime:
    """When a Premium member stops being able to read a volume's parts.

    The API's own `expiration` is null or wrong (null for every part of a
    volume published 2026-10-09). J-Novel Club's web app and jncep compute it
    from the volume's publishing date: the 15th, 10:00, of that month - or the
    next month once the volume publishes on the 9th or later - moved to Monday
    when that falls on a weekend. The web app builds the time in the browser's
    own timezone; jncep uses UTC, and so does this, since a warning given a
    week ahead does not depend on the hour.
    """
    year, month = publishing.year, publishing.month
    if publishing.day >= 9:
        month += 1
        if month == 13:
            year, month = year + 1, 1
    day = datetime(year, month, 15, 10, tzinfo=UTC)
    if day.weekday() == 5:
        day += timedelta(days=2)
    elif day.weekday() == 6:
        day += timedelta(days=1)
    return day


def _instant(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None



@dataclass(frozen=True)
class OwnedVolume:
    """One volume in the signed-in account's J-Novel Club library."""

    series_slug: str
    volume_id: str
    number: Decimal
    title: str | None
    status: str  # "owned" or "preorder"
    last_updated: datetime | None
    epub_link: str | None


def parse_library(payload: dict) -> tuple[list[OwnedVolume], bool, int]:
    """One page of the library, whether it was the last, and how many entries
    it held before any were skipped - paging counts those, not the parsed ones.

    Field names come from J-Novel Club's own message definitions (LibraryBook,
    Download) and from the clients that already download owned books; the
    account this was built with owned none, so no live page was seen.
    """
    books = payload.get("books") or []
    volumes: list[OwnedVolume] = []
    for book in books:
        try:
            parsed = _owned_volume(book)
        except (ValueError, ArithmeticError, TypeError, AttributeError):
            # No live library page has been seen. One entry in a shape this
            # does not expect is skipped, rather than failing every series'
            # sync on every run until someone reads a log.
            parsed = None
        if parsed is not None:
            volumes.append(parsed)
    last = bool((payload.get("pagination") or {}).get("lastPage", True))
    return volumes, last, len(books)


def _owned_volume(book: dict) -> OwnedVolume | None:
    volume = book.get("volume") or {}
    serie = book.get("serie") or {}
    if not volume.get("id") or volume.get("number") is None or not serie.get("slug"):
        return None
    link = next(
        (d.get("link") for d in book.get("downloads") or [] if d.get("type") == "EPUB"),
        None,
    )
    updated = book.get("lastUpdated")
    return OwnedVolume(
        series_slug=str(serie["slug"]),
        volume_id=str(volume["id"]),
        number=Decimal(str(volume["number"])),
        title=volume.get("title") or None,
        status="preorder" if book.get("status") == "PREORDER" else "owned",
        last_updated=_instant(updated) if isinstance(updated, str) else None,
        epub_link=link or None,
    )


def parse_part_ranges(payload: dict) -> dict[Decimal, tuple[Decimal, Decimal]]:
    """Each volume number's first and last part, from the series aggregate."""
    ranges: dict[Decimal, tuple[Decimal, Decimal]] = {}
    for entry in payload.get("volumes") or []:
        volume = entry.get("volume") or {}
        numbers = [Decimal(p["number"]) for p in entry.get("parts") or [] if "number" in p]
        if volume.get("number") is None or not numbers:
            continue
        ranges[Decimal(str(volume["number"]))] = (min(numbers), max(numbers))
    return ranges


class JNovelClubSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("j-novel.club", "labs.j-novel.club")

    def __init__(self, keeper: TokenKeeper | None = None, client=None, now=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=API_BASE))
        self.keeper = keeper or TokenKeeper(self.client)
        self._now = now or (lambda: datetime.now(UTC))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            f"{API_BASE}/app/v2/series", params={**JSON, "query": query}
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        match = _SERIES_SLUG.search(urlsplit(url).path)
        if match is None:
            raise ChapterUnavailable(f"{url} is not a J-Novel Club series address")
        # Signed in, `owned` is filled in, and owned volumes' parts never
        # expire; anonymous still lists everything, so a lapsed sign-in does
        # not stop discovery.
        url = f"{API_BASE}/app/v2/series/{match.group(1)}/aggregate"
        headers = await self._auth_headers(required=False)
        response = await self.client.get(url, params=JSON, headers=headers)
        if headers and response.status_code in (401, 410):
            # The token is dead on J-Novel Club's side though its clock says
            # otherwise. Say so to the keeper and list anonymously: discovery
            # runs in the other worker lane, which never learns of a rejection
            # the download lane saw.
            await self.keeper.invalidate(headers["Authorization"].removeprefix("Bearer "))
            response = await self.client.get(url, params=JSON)
        response.raise_for_status()
        return self.parse_chapters(response.json())

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        match = _PART_SLUG.search(urlsplit(chapter_url).path)
        if match is None:
            raise ChapterUnavailable(f"{chapter_url} is not a J-Novel Club part address")
        part = await self.client.get(f"{API_BASE}/app/v2/parts/{match.group(1)}", params=JSON)
        if part.status_code == 404:
            raise ChapterUnavailable(f"{chapter_url} {REFUSALS[404]}")
        part.raise_for_status()
        part_id = part.json()["id"]

        for attempt in (1, 2):
            token = await self.keeper.token()
            response = await self.client.get(
                f"{API_BASE}/embed/v2/{part_id}/data.xhtml",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code == 401 or (
                response.status_code in (403, 410) and not await self._session_alive(token)
            ):
                # A session J-Novel Club no longer accepts. 403 and 410 also
                # mean "this part is not yours" and "this part expired", and
                # reading a revoked token that way would skip every part in
                # the batch for good - so the session is asked first. Renew
                # once (from .env); otherwise the keeper now refuses it.
                await self.keeper.invalidate(token)
                if attempt == 1:
                    continue
                raise SignInRequired("J-Novel Club refused the sign-in; sign in again")
            if response.status_code in REFUSALS:
                raise ChapterUnavailable(f"{chapter_url} {REFUSALS[response.status_code]}")
            response.raise_for_status()
            return self.parse_chapter(response.text, chapter_url)
        raise AssertionError("unreachable")

    async def account_level(self) -> str | None:
        """The membership level of the signed-in account, for the Settings card.

        None for anything that goes wrong: the card is a convenience, and a
        failed lookup must not make the sign-in look broken.
        """
        try:
            headers = await self._auth_headers(required=True)
            response = await self.client.get(f"{API_BASE}/app/v2/me", params=JSON, headers=headers)
            response.raise_for_status()
            return response.json().get("level")
        except Exception:  # noqa: BLE001 - see the docstring
            return None

    async def library(self) -> list[OwnedVolume]:
        """Every volume the signed-in account owns or has pre-ordered."""
        volumes: list[OwnedVolume] = []
        skip = 0
        while True:
            token = await self.keeper.token()
            response = await self.client.get(
                f"{API_BASE}/app/v2/me/library",
                params={**JSON, "include": "serie", "limit": LIBRARY_PAGE, "skip": skip},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code in (401, 410):
                await self.keeper.invalidate(token)
                raise SignInRequired("J-Novel Club refused the sign-in; sign in again")
            response.raise_for_status()
            page, last, raw = parse_library(response.json())
            volumes.extend(page)
            if last or raw == 0:
                return volumes
            skip += raw

    async def part_ranges(self, series_slug: str) -> dict[Decimal, tuple[Decimal, Decimal]]:
        response = await self.client.get(
            f"{API_BASE}/app/v2/series/{series_slug}/aggregate", params=JSON
        )
        response.raise_for_status()
        return parse_part_ranges(response.json())

    async def fetch_volume(self, link: str) -> bytes:
        """The volume's EPUB, fetched from the link the library handed out.

        No Authorization header: the link carries its own, and the bearer
        token must never travel to whatever host the link points at.
        """
        response = await self.client.get(link, follow_redirects=True)
        response.raise_for_status()
        return response.content

    async def _session_alive(self, token: str) -> bool:
        """Whether J-Novel Club still accepts this token, asked of /me.

        A 5xx raises: not knowing is not the same as a dead session, and the
        retry ladder is the right answer to it.
        """
        response = await self.client.get(
            f"{API_BASE}/app/v2/me", params=JSON, headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code in (401, 410):
            return False
        response.raise_for_status()
        return True

    async def _auth_headers(self, *, required: bool) -> dict[str, str]:
        try:
            return {"Authorization": f"Bearer {await self.keeper.token()}"}
        except NotConfigured:
            if required:
                raise
            return {}

    def parse_search(self, payload: dict, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload.get("series") or []:
            # The same catalogue carries J-Novel Club's manga, often under the
            # very same title as the novel it adapts.
            if item.get("type") != "NOVEL" or not item.get("slug"):
                continue
            names = [n for n in (item.get("title"), item.get("shortTitle"),
                                 item.get("originalTitle")) if n]
            if not names:
                continue
            cover = (item.get("cover") or {}).get("thumbnailUrl") or None
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{WEB_BASE}/series/{item['slug']}",
                    title=names[0],
                    cover_url=cover,
                    alt_titles=names[1:],
                    score=round(max((best_similarity(names, t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, payload: dict) -> list[ChapterRef]:
        now = self._now()
        chapters: list[ChapterRef] = []
        for entry in payload.get("volumes") or []:
            volume = entry.get("volume") or {}
            publishing = _instant(volume.get("publishing"))
            for part in entry.get("parts") or []:
                launch = _instant(part.get("launch"))
                # A part announced but not out yet answers 403 to everyone;
                # listing it would queue a download that cannot succeed.
                if launch is not None and launch > now:
                    continue
                expiry = None
                if not part.get("preview") and not volume.get("owned") and publishing:
                    expiry = expires_at(publishing)
                chapters.append(
                    ChapterRef(
                        number=Decimal(part["number"]),
                        url=f"{WEB_BASE}/read/{part['slug']}",
                        title=part.get("title") or None,
                        volume=str(volume["number"]) if volume.get("number") is not None else None,
                        available_until=expiry,
                    )
                )
        return sorted(chapters, key=lambda c: c.number)

    def parse_chapter(self, xhtml: str, chapter_url: str) -> ChapterText:
        body = HTMLParser(xhtml).body
        if body is None:
            raise ChapterUnavailable(f"{chapter_url} returned no chapter body")
        text, images = clean_chapter_html(body.html, chapter_url)
        return ChapterText(
            title=None,
            body=text,
            images=[PageRef(url=url, headers={"Referer": f"{WEB_BASE}/"}) for url in images],
        )
