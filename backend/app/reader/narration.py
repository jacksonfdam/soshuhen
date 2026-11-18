"""Asks the narrator service what a page says.

Pure like the rest of `reader/`: bytes and a direction in, a transcript out. It reads no
setting and touches no database, so the caller decides which service and which client.
"""

from typing import Any, Literal

import httpx

Direction = Literal["rtl", "ltr"]

# A page takes under a second and the longest strip seen took five, on a laptop. A minute is
# room for a slower machine with a queue of pages in front of this one; past that the reader
# is better told the page could not be read than left waiting.
TIMEOUT = httpx.Timeout(60.0, connect=5.0)


class NarratorFailed(RuntimeError):
    """The narrator could not be reached, or did not answer with a transcript."""


async def transcribe(
    client: httpx.AsyncClient, base_url: str, data: bytes, direction: Direction
) -> dict[str, Any]:
    """The transcript of one page image, as the narrator's JSON."""
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/v1/pages",
            params={"direction": direction},
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
    except httpx.HTTPError as exc:
        # A timeout's message is empty, and "the narrator failed: " tells nobody anything.
        raise NarratorFailed(str(exc) or type(exc).__name__) from exc

    if response.is_error:
        raise NarratorFailed(_reason(response))
    try:
        body = response.json()
    except ValueError as exc:
        raise NarratorFailed("the answer was not JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("panels"), list):
        raise NarratorFailed("the answer was not a transcript")
    return body


def _reason(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str) and detail:
        return detail
    return f"status {response.status_code}"
