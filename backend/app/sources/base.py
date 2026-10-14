"""Contract for a source site, plus the registry that picks one for a URL.

Every source answers which works match a title and which chapters exist at a
URL. What a chapter *is* depends on the kind: a comic source lists page images,
which the downloader fetches; a prose source returns the chapter's text.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urlsplit


class NotConfigured(RuntimeError):
    """The site needs a personal login this deployment never set up.

    Distinct from a failed call: nothing is wrong, the target simply does not
    exist here, so a caller records an absence instead of retrying.
    """


class SignInRequired(NotConfigured):
    """The account a source signs in with has to sign in again.

    Its own class rather than plain NotConfigured, because the cure differs:
    a chapter refused for this reason is waiting on the user, not broken, and
    nothing about it may be marked skipped - the download handlers catch this,
    and only this, to put chapters back. A source that is simply not set up
    for one chapter (ComiciViewer's paid pages) still raises NotConfigured.
    """


class ChapterUnavailable(RuntimeError):
    """The source itself says the chapter is gone - a 404 on the chapter URL,
    or an empty page list - not that one request to reach it failed.

    The distinction is the whole point: a handler maps this to PermanentError
    and everything else onto the retry ladder, because retrying a chapter the
    source has removed cannot succeed and costs three more attempts to find
    that out.
    """


@dataclass(frozen=True)
class Candidate:
    source_site: str
    source_url: str
    title: str
    cover_url: str | None = None
    chapter_count: int | None = None
    year: int | None = None
    score: float = 0.0
    alt_titles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChapterRef:
    number: Decimal
    url: str
    title: str | None = None
    volume: str | None = None
    language: str = "en"
    # When a source stops serving this chapter to the signed-in account. None,
    # for every source but one, means it never expires.
    available_until: datetime | None = None


@dataclass(frozen=True)
class PageRef:
    """One page of a chapter.

    Headers travel with the page rather than with the source: many sites
    answer 403 without their own referer, and that referer is per-chapter,
    not per-site.
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChapterText:
    """One prose chapter, already reduced to the XHTML an EPUB can carry.

    Images stay references rather than bytes, so the downloader fetches them
    through the same rate-limited path as comic pages, referer and all. The
    body names them as {{img:N}}, an index into `images`.
    """

    title: str | None
    body: str
    images: list[PageRef] = field(default_factory=list)


class SiteSource(ABC):
    """What every site answers, whatever it publishes."""

    site: str
    domains: tuple[str, ...]
    kind: ClassVar[str]

    @abstractmethod
    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        """Candidates for the review screen, best score first."""

    @abstractmethod
    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        """Every chapter the source publishes for this work."""


class Source(SiteSource):
    """A comic source. The name predates prose sources and stays, so the
    templates and every native comic source keep compiling untouched."""

    kind: ClassVar[str] = "comic"

    @abstractmethod
    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        """Every page image for one chapter, in reading order."""

    def descramble(self, data: bytes, page: PageRef) -> bytes:
        """The bytes a reader should see. Identity for every source but one.

        Concrete rather than abstract: adding it here must not force every
        other source to grow a no-op override. comiciviewer is the only site
        that needs it today.
        """
        return data


class ProseSource(SiteSource):
    """A source that publishes text."""

    kind: ClassVar[str] = "prose"

    @abstractmethod
    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        """The chapter's text. Raises ChapterUnavailable for a chapter the site
        removed or keeps behind a paywall."""


def kind_of(source: object) -> str:
    """A source's kind, with comic as the answer for anything that never said.

    The download tests register duck-typed fakes with no base class at all, and
    every source written before prose existed is a comic one.
    """
    return getattr(source, "kind", "comic")


@dataclass(frozen=True)
class RegisteredSource:
    """A loaded row: the source instance plus the catalogue base_url it resolves from.

    The base_url travels separately from Source.domains because it comes from
    data (site_catalogue), while domains stays the extra aliases a hand-written
    class already carries - both are checked when a URL is resolved.
    """

    source: SiteSource
    base_url: str


_REGISTRY: dict[str, RegisteredSource] = {}


def install_registry(entries: dict[str, RegisteredSource]) -> None:
    """Replace the registry wholesale.

    Called by app.sources.registry.reload once at boot and again whenever
    settings change which sites are enabled - never incrementally, so a
    disabled site cannot linger from a stale entry nobody removed.
    """
    _REGISTRY.clear()
    _REGISTRY.update(entries)


def get_source(site: str) -> SiteSource:
    if site not in _REGISTRY:
        raise ValueError(f"unknown source site: {site}")
    return _REGISTRY[site].source


def get_comic_source(site: str) -> Source:
    """The source for a site that must publish images.

    Raises rather than returning something that lacks list_pages, so a mapping
    that crossed kinds fails here by name instead of as an AttributeError deep
    in a download.
    """
    source = get_source(site)
    if kind_of(source) != "comic":
        raise TypeError(f"{site} is a {kind_of(source)} source, not a comic one")
    return source  # type: ignore[return-value]


def get_prose_source(site: str) -> ProseSource:
    """The source for a site that must publish text. See get_comic_source."""
    source = get_source(site)
    if not isinstance(source, ProseSource):
        raise TypeError(f"{site} is a {kind_of(source)} source, not a prose one")
    return source


def all_sources(kind: str | None = None) -> list[SiteSource]:
    sources = [entry.source for entry in _REGISTRY.values()]
    if kind is None:
        return sources
    return [source for source in sources if kind_of(source) == kind]


def _host(url: str) -> str:
    """The comparable host of a URL.

    The `www.` prefix is dropped on both sides of the comparison. This used to
    be a substring test, which matched a pasted `https://www.weebcentral.com/…`
    by accident; an exact host match is right but would have started rejecting
    the same link, and the review screen is where people paste links by hand.
    """
    host = urlsplit(url).netloc.lower()
    return host.removeprefix("www.")


def source_for_url(url: str) -> SiteSource:
    """Pick the enabled source that owns a URL, so a hand-pasted link still resolves.

    Matches the URL's host against the host of each loaded row's base_url,
    and against the source's own domains tuple - the extra aliases a
    hand-written class already carries alongside what the catalogue knows.
    """
    host = _host(url)
    for entry in _REGISTRY.values():
        aliases = {_host(entry.base_url), *(_host(f"//{d}") for d in entry.source.domains)}
        if host in aliases:
            return entry.source
    enabled = ", ".join(sorted(entry.source.site for entry in _REGISTRY.values())) or "none"
    raise ValueError(f"no enabled source handles {url} - enabled sites: {enabled}")
