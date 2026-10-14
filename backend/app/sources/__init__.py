"""Source sites. The registry is loaded at boot - see registry.reload."""

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    NotConfigured,
    PageRef,
    ProseSource,
    SiteSource,
    Source,
    all_sources,
    get_comic_source,
    get_prose_source,
    get_source,
    kind_of,
    source_for_url,
)
from app.sources.registry import reload

__all__ = [
    "Candidate",
    "ChapterRef",
    "ChapterText",
    "NotConfigured",
    "PageRef",
    "ProseSource",
    "SiteSource",
    "Source",
    "all_sources",
    "get_comic_source",
    "get_prose_source",
    "get_source",
    "kind_of",
    "reload",
    "source_for_url",
]
