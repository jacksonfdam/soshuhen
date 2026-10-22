"""Series covers kept on this installation.

A cover's URL points at a list provider's CDN. A client that reads on the home
network must not reach out to it, so the server fetches each cover once and
serves its copy. Values in, values out: this never learns which series a URL
belongs to.
"""

import hashlib
from pathlib import Path

import httpx

from app.downloader.cbz import page_extension

# Swapped for a MockTransport by the tests; None is httpx's own.
TRANSPORT: httpx.AsyncBaseTransport | None = None

_TIMEOUT = 15.0


def key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def cached(root: Path, url: str) -> Path | None:
    # The key names the URL, not the series, so a changed cover_url is simply a
    # file that does not exist yet and nothing needs invalidating.
    for candidate in root.glob(f"{key(url)}.*"):
        if not candidate.name.endswith(".part"):
            return candidate
    return None


async def fetch(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> bytes | None:
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return None
    if not response.is_success:
        return None
    try:
        page_extension(response.content)
    except ValueError:
        # A CDN's error page arrives with a 200 often enough. Kept, it would be
        # served as the cover until the URL changed.
        return None
    return response.content


def store(root: Path, url: str, data: bytes) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / f"{key(url)}.{page_extension(data)}"
    # Written aside and renamed, so a request arriving mid-write never serves
    # half a cover.
    scratch = final.with_name(final.name + ".part")
    scratch.write_bytes(data)
    scratch.rename(final)
    return final
