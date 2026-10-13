"""Mark one Komga book read because it was finished in Soshuhen's reader.

Its own job rather than a call from the route: Komga can be down, and the
retry ladder is what should absorb that, not the reader's page turn.
"""

from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.komga import from_settings


@register(JobType.KOMGA_READ_PROGRESS)
async def handle(ctx: JobContext) -> None:
    client = from_settings()
    if not client.has_credentials:
        raise PermanentError("set KOMGA_API_KEY, or KOMGA_USER and KOMGA_PASS")
    book_id = str(ctx.payload["book_id"])
    await client.set_read_progress(book_id, page=1, completed=True)
    await ctx.log(f"marked {book_id} read in komga", pct=100)
