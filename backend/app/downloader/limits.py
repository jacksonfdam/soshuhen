"""Per-source concurrency, shared by every handler that reaches a source site.

Parallelism across sites is free; parallelism against one site is what earns a
rate limit, so the semaphore is keyed by site rather than global.
"""

import asyncio

_semaphores: dict[str, asyncio.Semaphore] = {}
_lock = asyncio.Lock()


async def source_semaphore(site: str, limit: int) -> asyncio.Semaphore:
    async with _lock:
        if site not in _semaphores:
            _semaphores[site] = asyncio.Semaphore(limit)
        return _semaphores[site]


# One request at a time per site for the reader, apart from the downloads'
# slots. A download batch holds its slot for every chapter in it, so a reader
# waiting in the same queue would wait minutes for a page. The site sees at
# most per_source_concurrency + 1, which is a person reading on top of the
# backlog, not a second backlog.
READER_SLOTS = 1


async def reader_semaphore(site: str) -> asyncio.Semaphore:
    return await source_semaphore(f"reader:{site}", READER_SLOTS)
