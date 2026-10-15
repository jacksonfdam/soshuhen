"""Close the loop: what you read in Komga becomes progress on your lists.

Only forward movement is written. If a list already records a higher chapter
than Komga has marked read, the list wins, so reading elsewhere is never undone
by this job.
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, ProgressSource, Provider
from app.handlers import progress_events
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.progress_write import forward_only
from app.handlers.volume_progress import VolumeRow, furthest_volume, pushable_volume
from app.komga import KomgaBook, from_settings
from app.providers import get_source
from app.providers.base import WriteRefused
from app.providers.tokens import access_token_for, keyed_providers


def highest_completed(books: list[KomgaBook], numbers: dict[str, Decimal]) -> Decimal | None:
    """The furthest chapter marked finished, ignoring books we did not place."""
    completed = [numbers[book.id] for book in books if book.completed and book.id in numbers]
    return max(completed) if completed else None


def pushable_chapter(read_chapter: int, kind: str | None, total: int | None) -> int:
    """The chapter to write to one list entry.

    Light novels only. J-Novel Club numbers its parts across a whole series,
    and a list counts the novel's chapters its own way, so a part number can
    run past the total the list itself holds - a number the provider would
    refuse or store as nonsense. Comics are left alone: their providers'
    totals lag releases, and capping them would hold real progress back.
    """
    if kind == "prose" and total and read_chapter > total:
        return total
    return read_chapter


async def chapter_numbers(session: AsyncSession, series_id: int) -> dict[str, Decimal]:
    result = await session.execute(
        text(
            """
            select komga_book_id, number from chapter
             where series_id = :series_id and komga_book_id is not null
            """
        ),
        {"series_id": series_id},
    )
    return {row.komga_book_id: Decimal(str(row.number)) for row in result.all()}


async def volume_rows(session: AsyncSession, series_id: int) -> list[VolumeRow]:
    rows = (
        await session.execute(
            text(
                "select number, first_part, last_part, komga_book_id from volume"
                " where series_id = :s"
            ),
            {"s": series_id},
        )
    ).all()
    return [
        VolumeRow(
            number=Decimal(str(r.number)),
            first_part=Decimal(str(r.first_part)) if r.first_part is not None else None,
            last_part=Decimal(str(r.last_part)) if r.last_part is not None else None,
            komga_book_id=r.komga_book_id,
        )
        for r in rows
    ]


async def chapter_books(session: AsyncSession, series_id: int) -> dict[Decimal, str | None]:
    rows = (
        await session.execute(
            text("select number, komga_book_id from chapter where series_id = :s"),
            {"s": series_id},
        )
    ).all()
    return {Decimal(str(r.number)): r.komga_book_id for r in rows}


async def entries_of(session: AsyncSession, series_id: int) -> list:
    """Every list entry this job may actually write to.

    A provider authenticating with a configured key has no `provider_token` row
    and never will, so the join alone dropped it from the loop silently - the
    job reported the lists it did push and never mentioned the one it had not
    looked at.
    """
    result = await session.execute(
        text(
            """
            select e.id, e.provider, e.provider_media_id, e.user_progress_chapter,
                   e.total_chapters, e.user_progress_volume, e.total_volumes
              from list_entry e
              left join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
               and (t.provider is not null
                    or e.provider = any(cast(:keyed as text[])))
            """
        ),
        {"series_id": series_id, "keyed": keyed_providers()},
    )
    return result.all()


@register(JobType.PROGRESS_PUSH)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    result = await ctx.session.execute(
        text("select komga_series_id, kind from series where id = :id"), {"id": series_id}
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"series {series_id} no longer exists")
    if not row.komga_series_id:
        raise PermanentError(f"series {series_id} has not been indexed by komga yet")

    client = from_settings()
    if not client.has_credentials:
        raise PermanentError("set KOMGA_API_KEY, or KOMGA_USER and KOMGA_PASS")

    books = await client.books_of_series(row.komga_series_id)
    numbers = await chapter_numbers(ctx.session, series_id)
    furthest = highest_completed(books, numbers)
    read_volume, volume_last_part = furthest_volume(
        books, await volume_rows(ctx.session, series_id), await chapter_books(ctx.session, series_id)
    )
    # A finished volume is its parts read: chapters follow it to its last part,
    # even when no chapter book of its own was ever finished.
    candidates = [n for n in (furthest, volume_last_part) if n is not None]
    if not candidates:
        await ctx.log("nothing marked read in komga", pct=100)
        return

    read_chapter = int(max(candidates))
    before = await progress_events.furthest_read(ctx.session, series_id)
    pushed = 0

    for entry in await entries_of(ctx.session, series_id):
        chapter = pushable_chapter(read_chapter, row.kind, entry.total_chapters)
        if chapter < read_chapter:
            await ctx.log(
                f"{entry.provider}: part {read_chapter} is past the list's {chapter} chapters,"
                f" sending {chapter}"
            )
        chapter_moves = forward_only(entry.user_progress_chapter, chapter) is not None
        volume = pushable_volume(read_volume, entry.total_volumes, entry.user_progress_volume)
        if not chapter_moves and volume is None:
            continue
        # A volume-only move must not carry the chapter backwards.
        chapter_sent = max(chapter, entry.user_progress_chapter)
        provider = Provider(entry.provider)
        token = await access_token_for(ctx.session, provider)
        source = get_source(provider)
        try:
            await source.push_progress(token, entry.provider_media_id, chapter_sent, volume)
        except WriteRefused:
            if volume is None:
                raise
            # No provider documents what it does past its volume count; one it
            # will not take must not hold chapter progress back with it.
            await ctx.log(f"{provider} refused volume {volume}, sent chapter only", level="warning")
            volume = None
            await source.push_progress(token, entry.provider_media_id, chapter_sent)
        await ctx.session.execute(
            text(
                "update list_entry set user_progress_chapter = :c,"
                " user_progress_volume = coalesce(cast(:v as integer), user_progress_volume)"
                " where id = :id"
            ),
            {"c": chapter_sent, "v": volume, "id": entry.id},
        )
        shown = f"chapter {chapter_sent}" + (f", volume {volume}" if volume is not None else "")
        await ctx.log(f"{provider}: progress set to {shown}")
        pushed += 1

    # Guarded by `pushed` so the event cannot repeat: an entry that was not
    # updated leaves the series' recorded progress where it was, and the next
    # run of this job would measure the same distance all over again.
    if pushed:
        await progress_events.record(
            ctx.session,
            series_id,
            before=before,
            chapter=read_chapter,
            source=ProgressSource.KOMGA,
        )

    await ctx.log(f"chapter {read_chapter} read, {pushed} lists updated", pct=100)
