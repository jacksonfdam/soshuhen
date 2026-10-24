"""Mark one Komga book read because it was finished in Soshuhen's reader.

Its own job rather than a call from the route: Komga can be down, and the
retry ladder is what should absorb that, not the reader's page turn.
"""

from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.komga import from_settings
from app.queue import repo


@register(JobType.KOMGA_READ_PROGRESS)
async def handle(ctx: JobContext) -> None:
    client = from_settings()
    if not client.has_credentials:
        raise PermanentError("set KOMGA_API_KEY, or KOMGA_USER and KOMGA_PASS")
    book_id = str(ctx.payload["book_id"])
    await client.set_read_progress(book_id, page=1, completed=True)
    await ctx.log(f"marked {book_id} read in komga", pct=100)

    series_id = ctx.payload.get("push_series_id")
    if series_id is None:
        return
    # A finished volume reaches the lists through progress_push, which reads
    # Komga's read state. Queued from here, after the mark, because queued
    # beside this job a second worker could read Komga before the book was
    # marked and push nothing. The cron's own key: one waiting push is enough,
    # and one already running when this lands is caught by the next hour's.
    await repo.enqueue(
        ctx.session,
        JobType.PROGRESS_PUSH,
        {"series_id": int(series_id)},
        series_id=int(series_id),
        dedupe_key=f"progress_push:{series_id}",
    )
