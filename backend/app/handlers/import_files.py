"""Write an import the user confirmed: staged PDFs into chapter and volume EPUBs.

The plan is computed again here from the same staged files, so a retry after a
crash skips what already landed - those files now read as existing - and writes
only the rest. Nothing here marks a chapter read: importing makes chapters
available, and reading progress belongs to the lists.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.downloader.cbz import page_extension
from app.downloader.epub import EpubChapter, write_epub
from app.downloader.paths import (
    chapter_path,
    number_from_filename,
    volume_number_from_filename,
    volume_path,
)
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.download_chapter import build_comicinfo
from app.importer import staging
from app.importer.numbering import ReadVolume
from app.importer.pdf import PdfEntry
from app.importer.plan import Existing, Override, PlannedFile
from app.importer.reading import build_plan
from app.importer.xhtml import entries_to_body


def _usable(image: bytes) -> bool:
    try:
        page_extension(image)
    except ValueError:
        return False
    return True


def _clean(entries: list[PdfEntry]) -> list[PdfEntry]:
    # write_epub refuses a format it cannot name; an image pypdf hands back raw
    # is dropped rather than costing the chapter its text.
    return [PdfEntry(e.title, e.pages, [i for i in e.images if _usable(i)]) for e in entries]


def _overrides(raw: dict[str, Any]) -> dict[str, Override]:
    return {
        sha: Override(
            volume=Decimal(str(v["volume"])) if v.get("volume") is not None else None,
            edition=v.get("edition"),
            replace=bool(v.get("replace")),
        )
        for sha, v in raw.items()
    }


async def _existing(ctx: JobContext, series_id: int) -> Existing:
    chapters = (
        await ctx.session.execute(
            text("select number from chapter where series_id = :s"), {"s": series_id}
        )
    ).scalars()
    volumes = (
        await ctx.session.execute(
            text("select number, edition from volume where series_id = :s"), {"s": series_id}
        )
    ).all()
    return Existing(
        chapters=frozenset(Decimal(str(n)) for n in chapters),
        volumes=frozenset((Decimal(str(v.number)), v.edition) for v in volumes),
    )


def _drop_previous(previous: str | None, written: Path, reads_back: bool) -> None:
    """Remove a replaced file, only when it is this same item's own older file."""
    if not previous or previous == str(written):
        return
    old = Path(previous)
    if old.parent == written.parent and reads_back:
        old.unlink(missing_ok=True)


async def _write_web(
    ctx: JobContext,
    series: Any,
    item: PlannedFile,
    read: ReadVolume,
    info: Any,
    library: Path,
) -> None:
    for chapter in read.chapters:
        destination = chapter_path(library, series.slug, chapter.number, chapter.title, kind="prose")
        body, images = entries_to_body(_clean(chapter.entries), own_heading=False)
        await write_epub(_epub(series, chapter.number, chapter.title, body, images, read, info,
                               f"soshuhen:{series.id}:{chapter.number}"), destination)
        previous = (
            await ctx.session.execute(
                text(
                    """
                    insert into chapter (series_id, number, title, state, file_path)
                    values (:s, :n, :t, 'downloaded', :p)
                    on conflict (series_id, number) do update
                       set title = excluded.title, state = 'downloaded',
                           file_path = excluded.file_path, komga_book_id = null
                    returning (select file_path from chapter c
                                where c.series_id = :s and c.number = :n) as previous
                    """
                ),
                {"s": series.id, "n": chapter.number, "t": chapter.title, "p": str(destination)},
            )
        ).scalar_one()
        _drop_previous(previous, destination,
                       number_from_filename(Path(previous).name) == chapter.number if previous else False)

    numbers = [c.number for c in read.chapters]
    await _upsert_volume(ctx, series.id, item, min(numbers), max(numbers), None)


async def _write_light(
    ctx: JobContext,
    series: Any,
    item: PlannedFile,
    read: ReadVolume,
    info: Any,
    library: Path,
) -> None:
    destination = volume_path(library, series.slug, item.volume)
    entries = [entry for chapter in read.chapters for entry in chapter.entries]
    body, images = entries_to_body(_clean(entries))
    await write_epub(
        _epub(series, item.volume, f"Volume {item.volume}", body, images, read, info,
              f"soshuhen:{series.id}:light-volume:{item.volume}"),
        destination,
    )
    previous = await _upsert_volume(ctx, series.id, item, None, None, str(destination))
    _drop_previous(previous, destination,
                   volume_number_from_filename(Path(previous).name) == item.volume if previous else False)


def _epub(series, number: Decimal, title: str | None, body: str, images: list[bytes],
          read: ReadVolume, info, identifier: str) -> EpubChapter:
    cover = read.cover if read.cover is not None and _usable(read.cover) else None
    return EpubChapter(
        series=series.canonical_title,
        number=number,
        identifier=identifier,
        title=title,
        body=body,
        images=images,
        cover=cover,
        authors=[info.writer] if info.writer else [],
        summary=info.summary,
    )


async def _upsert_volume(
    ctx: JobContext,
    series_id: int,
    item: PlannedFile,
    first: Decimal | None,
    last: Decimal | None,
    file_path: str | None,
) -> str | None:
    return (
        await ctx.session.execute(
            text(
                """
                insert into volume (series_id, number, edition, source_volume_id, title, status,
                                    state, first_part, last_part, file_path)
                values (:s, :n, :e, :src, :t, 'owned', 'downloaded', :first, :last, :p)
                on conflict (series_id, number, edition) do update
                   set source_volume_id = excluded.source_volume_id, state = 'downloaded',
                       first_part = excluded.first_part, last_part = excluded.last_part,
                       file_path = excluded.file_path, komga_book_id = null
                returning (select file_path from volume v
                            where v.series_id = :s and v.number = :n and v.edition = :e) as previous
                """
            ),
            {
                "s": series_id,
                "n": item.volume,
                "e": item.edition,
                "src": f"import:{item.sha256}",
                "t": f"Volume {item.volume}" if item.edition == "light" else None,
                "first": first,
                "last": last,
                "p": file_path,
            },
        )
    ).scalar_one()


@register(JobType.IMPORT_FILES)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    token = str(ctx.payload["token"])
    series = (
        await ctx.session.execute(
            text("select id, slug, canonical_title from series where id = :id"), {"id": series_id}
        )
    ).first()
    if series is None:
        raise PermanentError(f"series {series_id} no longer exists")
    received = await asyncio.to_thread(staging.staged, token)
    if received is None:
        raise PermanentError("staged files are gone; upload again")

    existing = await _existing(ctx, series_id)
    planned, read = await asyncio.to_thread(
        build_plan, series.slug, received, existing, _overrides(ctx.payload.get("overrides") or {})
    )
    ready = [item for item in planned if item.status == "ready"]
    info = await build_comicinfo(
        ctx.session,
        {"series_id": series_id, "canonical_title": series.canonical_title, "number": 0,
         "title": None, "source_url": None},
    )
    library = Path(get_settings().library_path)

    for index, item in enumerate(ready, start=1):
        volume = read[item.sha256]
        assert volume is not None  # a ready file was read
        if item.edition == "web":
            await _write_web(ctx, series, item, volume, info, library)
        else:
            await _write_light(ctx, series, item, volume, info, library)
        # Per file, so a crash keeps every volume already written.
        await ctx.session.commit()
        await ctx.log(f"imported {item.edition} volume {item.volume}", pct=int(index * 100 / len(ready)))

    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": series_id},
        series_id=series_id,
        dedupe_key=f"komga_scan:{series_id}",
    )
    await ctx.session.commit()
    await asyncio.to_thread(staging.discard, token)

