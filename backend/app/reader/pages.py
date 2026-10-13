"""PageRef to and from what the database stores."""

from typing import Any

from app.sources.base import PageRef


def dump(pages: list[PageRef]) -> list[dict[str, Any]]:
    return [{"url": page.url, "headers": dict(page.headers)} for page in pages]


def load(raw: list[dict[str, Any]]) -> list[PageRef]:
    return [PageRef(url=item["url"], headers=dict(item.get("headers") or {})) for item in raw]
