"""Delete server copies that a device has verified it holds.

The phone names each file by the ETag it copied it under. A file rebuilt on the
server since then answers a different ETag, and is kept: the device holds an
older archive, not this one. Nothing here ever queues a download - an offloaded
row waits until the user asks for it again.
"""

import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy import text
from starlette.responses import FileResponse

from app.config import get_settings
from app.enums import JobType
from app.handlers.base import JobContext, register
from app.reader.archive import inside

log = logging.getLogger(__name__)

# Table names come from this map, never from the payload.
_TABLES = {"chapters": "chapter", "volumes": "volume"}


def served_etag(path: Path) -> str:
    """The ETag the archive endpoint serves for this file.

    Taken from FileResponse itself rather than recomputed, so the value the
    phone recorded and the value checked here cannot drift apart.
    """
    return FileResponse(path, stat_result=os.stat(path)).headers["etag"]


async def _offload_one(
    ctx: JobContext, table: str, item: dict[str, Any], root: Path
) -> tuple[int | None, int, str | None]:
    """(series_id, bytes freed, reason kept). One transaction per item.

    The API marks a row offloaded as it accepts it; a row the job then keeps
    goes back to downloaded, since the server still holds its file.
    """
    item_id = int(item["id"])
    row = (
        await ctx.session.execute(
            text(f"select series_id, state, file_path from {table} where id = :id for update"),
            {"id": item_id},
        )
    ).first()
    if row is None:
        return None, 0, "unknown"
    if row.state not in ("downloaded", "offloaded") or row.file_path is None:
        return None, 0, f"state is {row.state}"

    async def keep(reason: str) -> tuple[None, int, str]:
        await ctx.session.execute(
            text(f"update {table} set state = 'downloaded' where id = :id"), {"id": item_id}
        )
        return None, 0, reason

    path = Path(row.file_path)
    if not inside(path, root):
        return await keep("outside the library")
    size = 0
    if path.is_file():
        size = path.stat().st_size
        if size != int(item["size"]) or served_etag(path) != item["etag"]:
            return await keep("changed since the device copied it")
    # The row is committed before the file goes: a failure after the commit
    # leaves a stray file, which is harmless, never a row that says the server
    # holds a file it deleted. A file already gone still becomes offloaded -
    # the device has it, which is all the state promises.
    await ctx.session.execute(
        text(f"update {table} set state = 'offloaded', file_path = null where id = :id"),
        {"id": item_id},
    )
    await ctx.session.commit()
    if size:
        path.unlink(missing_ok=True)
        # Only an empty folder goes: anything else in it is still the library's.
        try:
            path.parent.rmdir()
        except OSError:
            pass
    return int(row.series_id), size, None


@register(JobType.OFFLOAD)
async def handle(ctx: JobContext) -> None:
    root = get_settings().library_path
    touched: set[int] = set()
    deleted = skipped = freed = 0
    for key, table in _TABLES.items():
        for item in ctx.payload.get(key, []):
            try:
                series_id, size, reason = await _offload_one(ctx, table, item, root)
            except Exception:
                # One bad item must not cost the rest of a library's offload.
                await ctx.session.rollback()
                log.exception("offload of %s %s failed", table, item.get("id"))
                skipped += 1
                continue
            await ctx.session.commit()
            if reason is not None:
                skipped += 1
                log.info("offload kept %s %s: %s", table, item.get("id"), reason)
                continue
            deleted += 1
            freed += size
            if series_id is not None:
                touched.add(series_id)
    for series_id in sorted(touched):
        await ctx.enqueue(
            JobType.KOMGA_SCAN,
            {"series_id": series_id},
            series_id=series_id,
            dedupe_key=f"komga_scan:{series_id}",
        )
    await ctx.log(f"{deleted} removed from the server, {skipped} kept, {freed} bytes freed")
