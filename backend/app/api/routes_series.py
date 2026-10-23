"""Library and review screens."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import rhythm, settings_store
from app.api.deps import db_session
from app.api.list_raw import display_fields, metadata_of
from app.api.progress_queue import progress_bounds, queue_progress_write
from app.api.reading_frequency import reading_frequency
from app.api.reading_recency import LAST_READ_AT
from app.api.routes_reader import MEDIA_TYPES
from app.config import get_settings
from app.enums import JobType, ListStatus, ProgressSource, Provider
from app.handlers.batching import queue_batches
from app.handlers.match_search import series_kind
from app.handlers.media_enrich import is_stale
from app.handlers.progress_write import forward_only
from app.providers import get_source
from app.queue import repo
from app.reader import covers
from app.series_removal import remove_series
from app.sources import kind_of, source_for_url

router = APIRouter(prefix="/api/series", tags=["series"])

Session = Annotated[AsyncSession, Depends(db_session)]


class MappingIn(BaseModel):
    source_url: str


class DownloadIn(BaseModel):
    from_chapter: float | None = None
    to_chapter: float | None = None


class AutoDownloadIn(BaseModel):
    enabled: bool


class KindIn(BaseModel):
    kind: Literal["comic", "prose"]


class ProgressIn(BaseModel):
    chapter: int


# Above the whole library as it stands (295 titles), so selecting everything on
# the grid still goes through in one request. The cap is not about the grid
# though: series_ids arrives from the network, and one job per series means an
# unbounded list is an unbounded number of provider writes queued by one POST.
BATCH_STATUS_LIMIT = 500


class BatchStatusIn(BaseModel):
    series_ids: list[int] = Field(max_length=BATCH_STATUS_LIMIT)
    status: ListStatus


class StatusIn(BaseModel):
    status: ListStatus


class NotesIn(BaseModel):
    # MyAnimeList refuses a comment past 5000 characters, and refuses it again
    # however many times it is asked - so the refusal belongs here, where the
    # user can still edit what they typed.
    notes: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=20)


LIST_SQL = f"""
select s.id, s.canonical_title, s.slug, s.needs_review, s.meta, s.komga_series_id,
       s.auto_download, s.kind,
       coalesce(m.source_site, '') as source_site,
       coalesce(m.source_url, '') as source_url,
       coalesce(max(ch.downloaded), 0) as downloaded,
       coalesce(max(ch.known), 0) as known,
       coalesce(max(ch.in_flight), 0) as in_flight,
       coalesce(max(ch.failed), 0) as failed,
       coalesce(max(ch.expiring_count), 0) as expiring_count,
       max(ch.expiring_earliest) as expiring_earliest,
       array_remove(array_agg(distinct e.provider), null) as providers,
       max(e.total_chapters) as total_chapters,
       (array_agg(e.status order by
           (e.provider = any(cast(:writable as text[]))) desc,
           e.updated_at desc))[1] as status,
       -- Whether a progress or status write has anywhere to land. A series
       -- held only by read-only providers (MangaBaka reads, it is never
       -- written) can accept neither, and the screen has to know that before
       -- it draws a control rather than after the click fails.
       coalesce(bool_or(e.provider = any(cast(:writable as text[]))), false) as writable,
       coalesce(max(e.user_progress_chapter), 0) as progress,
       max(e.updated_at) as updated_at,
       {LAST_READ_AT} as last_read_at,
       (array_agg(e.raw order by e.updated_at desc))[1] as raw
  from series s
  left join source_mapping m on m.series_id = s.id and m.active
  left join list_entry e on e.series_id = s.id
  left join (
      -- Chapter stats grouped on their own, one row per series, so joining
      -- them alongside list_entry (also one-to-many on series) never lets the
      -- two relations cross-multiply each other's rows. See #34: a series
      -- synced from two providers used to count every chapter twice.
      select series_id,
             count(*) filter (where state = 'downloaded') as downloaded,
             count(*) as known,
             count(*) filter (where state in ('queued', 'downloading')) as in_flight,
             count(*) filter (where state = 'failed') as failed,
             -- The same week as chapter_discover.EXPIRY_WARNING_DAYS.
             count(*) filter (where state in ('known', 'queued', 'failed')
                                and available_until > now()
                                and available_until <= now() + interval '7 days')
                 as expiring_count,
             min(available_until) filter (where state in ('known', 'queued', 'failed')
                                            and available_until > now()
                                            and available_until <= now() + interval '7 days')
                 as expiring_earliest
        from chapter
       group by series_id
  ) ch on ch.series_id = s.id
 group by s.id, m.source_site, m.source_url
 order by s.canonical_title
"""

# Same aggregate as LIST_SQL, narrowed to one row — the detail route needs the
# exact shape the library card already rendered, not a second query that could
# drift from it one column at a time.
LIST_SQL_ONE = f"""
select s.id, s.canonical_title, s.slug, s.needs_review, s.meta, s.komga_series_id,
       s.auto_download, s.kind,
       coalesce(m.source_site, '') as source_site,
       coalesce(m.source_url, '') as source_url,
       coalesce(max(ch.downloaded), 0) as downloaded,
       coalesce(max(ch.known), 0) as known,
       coalesce(max(ch.in_flight), 0) as in_flight,
       coalesce(max(ch.failed), 0) as failed,
       coalesce(max(ch.expiring_count), 0) as expiring_count,
       max(ch.expiring_earliest) as expiring_earliest,
       array_remove(array_agg(distinct e.provider), null) as providers,
       max(e.total_chapters) as total_chapters,
       (array_agg(e.status order by
           (e.provider = any(cast(:writable as text[]))) desc,
           e.updated_at desc))[1] as status,
       -- Whether a progress or status write has anywhere to land. A series
       -- held only by read-only providers (MangaBaka reads, it is never
       -- written) can accept neither, and the screen has to know that before
       -- it draws a control rather than after the click fails.
       coalesce(bool_or(e.provider = any(cast(:writable as text[]))), false) as writable,
       coalesce(max(e.user_progress_chapter), 0) as progress,
       max(e.updated_at) as updated_at,
       {LAST_READ_AT} as last_read_at,
       (array_agg(e.raw order by e.updated_at desc))[1] as raw
  from series s
  left join source_mapping m on m.series_id = s.id and m.active
  left join list_entry e on e.series_id = s.id
  left join (
      -- The same per-series chapter stats as LIST_SQL, for the same reason:
      -- joined straight to series beside list_entry, a series on two
      -- providers counted every chapter twice here long after #34 fixed the
      -- library card, and the two screens disagreed about the same series.
      select series_id,
             count(*) filter (where state = 'downloaded') as downloaded,
             count(*) as known,
             count(*) filter (where state in ('queued', 'downloading')) as in_flight,
             count(*) filter (where state = 'failed') as failed,
             -- The same week as chapter_discover.EXPIRY_WARNING_DAYS.
             count(*) filter (where state in ('known', 'queued', 'failed')
                                and available_until > now()
                                and available_until <= now() + interval '7 days')
                 as expiring_count,
             min(available_until) filter (where state in ('known', 'queued', 'failed')
                                            and available_until > now()
                                            and available_until <= now() + interval '7 days')
                 as expiring_earliest
        from chapter
       where series_id = :id
       group by series_id
  ) ch on ch.series_id = s.id
 where s.id = :id
 group by s.id, m.source_site, m.source_url
"""


# The review queue, which is not the library list narrowed down.
#
# LIST_SQL's `needs_review` state is derived from having no active mapping, and
# every screen that reads it — Library cards, the series header, the download
# path — has to keep meaning exactly that. So the one place a user's "stop
# asking" belongs is a query of its own, and LIST_SQL is left alone.
#
# Same `not exists` shape the dashboard's pending-mappings count already uses,
# so the two cannot drift into disagreeing about what "waiting" means.
REVIEW_QUEUE_SQL = """
select s.id, s.canonical_title, s.meta,
       count(c.id) as candidate_count
  from series s
  left join series_candidate c on c.series_id = s.id
 where not exists (
     select 1 from source_mapping m where m.series_id = s.id and m.active
 )
   and (s.review_ignored_at is not null) = cast(:ignored as boolean)
 group by s.id
 -- id breaks the tie, or two series sharing a title could swap places between
 -- loads and the position the screen shows would be a different series' place.
 order by s.canonical_title, s.id
"""


async def _review_list(session: AsyncSession, *, ignored: bool) -> dict[str, Any]:
    result = await session.execute(text(REVIEW_QUEUE_SQL), {"ignored": ignored})
    items = [
        {
            "id": row.id,
            "title": row.canonical_title,
            "cover_url": (row.meta or {}).get("cover_url"),
            "candidate_count": row.candidate_count,
        }
        for row in result.all()
    ]
    # Counted from the rows that were returned, not from a second count(*). The
    # screen numbers a series "3 of 168" out of this same list, and a total the
    # list cannot account for is how a position ends up past the end of it.
    return {"total": len(items), "items": items}


def _iso_or_none(value: Any) -> str | None:
    return value.isoformat() if value else None


def _row_to_series(row: Any) -> dict[str, Any]:
    """Shared by the list and detail routes so they cannot drift.

    Two builders would each need updating the same way forever, and the
    detail page would quietly start disagreeing with the card the user
    clicked to reach it.
    """
    return {
        "id": row.id,
        "title": row.canonical_title,
        "slug": row.slug,
        "cover_url": (row.meta or {}).get("cover_url"),
        "source_site": row.source_site or None,
        "source_url": row.source_url or None,
        "providers": sorted(row.providers or []),
        "writable": row.writable,
        "downloaded": row.downloaded,
        "known": row.known,
        "in_flight": row.in_flight,
        "failed": row.failed,
        "total_chapters": row.total_chapters,
        "auto_download": row.auto_download,
        "kind": row.kind,
        "expiring": (
            {"count": row.expiring_count, "earliest": row.expiring_earliest.isoformat()}
            if row.expiring_count
            else None
        ),
        "state": _state_of(row),
        "status": row.status,
        "progress": row.progress,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # Absent from rows built by queries other than LIST_SQL, which never
        # order by reading.
        "last_read_at": _iso_or_none(row._mapping.get("last_read_at")),
        # The reader lives in Komga, not here, so the screen needs Komga's own
        # id to link to it. Null until a scan has matched the series there.
        "komga_series_id": row.komga_series_id,
        **display_fields(row.raw),
    }


async def _resolve_similar(session: AsyncSession, metadata: dict[str, Any] | None) -> None:
    """Say which similar works are already in the library, by AniList id.

    Matched on `provider_media_id` rather than on the title: the recommendations
    and the list entries come from the same provider, so the id is exact, and
    title matching across romanisations is the thing this project already spends
    a whole screen correcting.

    A work with no `series_id` is one the reader does not have, and the screen
    sends them to AniList for it instead.
    """
    if not metadata:
        return
    similar = metadata.get("similar")
    if not similar:
        return

    ids = [str(item["media_id"]) for item in similar if item.get("media_id")]
    if not ids:
        return

    rows = await session.execute(
        text(
            """
            select provider_media_id, series_id
              from list_entry
             where provider = 'anilist'
               and series_id is not null
               and provider_media_id = any(cast(:ids as text[]))
            """
        ),
        {"ids": ids},
    )
    owned = {row.provider_media_id: row.series_id for row in rows.all()}
    for item in similar:
        item["series_id"] = owned.get(str(item.get("media_id")))


def _state_of(row: Any) -> str:
    if row.in_flight:
        return "downloading"
    if row.failed:
        return "failed"
    if not row.source_url:
        return "needs_review"
    return "mapped"


@router.get("")
async def list_series(
    session: Session,
    state: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    result = await session.execute(text(LIST_SQL), {"writable": writable_providers()})
    series = []
    for row in result.all():
        item = _row_to_series(row)
        if state is None or item["state"] == state:
            series.append(item)
    return series


@router.get("/review/queue")
async def review_queue(session: Session) -> dict[str, Any]:
    """Everything Review will ask about, in the order it will ask.

    The screen shows one series at a time, so it needs the whole list to say
    where in it the user is — and to let them look ahead without answering.
    """
    return await _review_list(session, ignored=False)


@router.get("/review/ignored")
async def review_ignored(session: Session) -> dict[str, Any]:
    """The way back out of "not interested", listed the way Unmatched lists what it hid."""
    return await _review_list(session, ignored=True)


@router.post("/{series_id}/review-ignore")
async def ignore_in_review(series_id: int, session: Session) -> dict[str, Any]:
    """Take a series out of the review queue without taking it out of anything else.

    One title no source carries used to sit at the front of the queue and stop
    the other hundred and sixty-seven from being answered. This is the answer
    "there is nothing to map here" — the series keeps its list entries, its
    status, its progress and its syncs, and an unmapped series was downloading
    nothing to begin with.
    """
    return await _set_review_ignored(session, series_id, ignored=True)


@router.delete("/{series_id}/review-ignore")
async def unignore_in_review(series_id: int, session: Session) -> dict[str, Any]:
    """The undo. Permanent has to mean recoverable, or nobody presses the button."""
    return await _set_review_ignored(session, series_id, ignored=False)


async def _set_review_ignored(
    session: AsyncSession, series_id: int, *, ignored: bool
) -> dict[str, Any]:
    result = await session.execute(
        text(
            """
            update series set review_ignored_at = case when :ignored then now() end
             where id = :id
         returning id
            """
        ),
        {"ignored": ignored, "id": series_id},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="series not found")
    await session.commit()
    return {"ok": True, "ignored": ignored}


@router.get("/{series_id}/cover")
async def cover(series_id: int, request: Request, session: Session) -> Response:
    url = (
        await session.execute(
            text("select meta->>'cover_url' from series where id = :id"), {"id": series_id}
        )
    ).scalar_one_or_none()
    # Released before the CDN is asked: its timeout is fifteen seconds, and a
    # first library load asks for every cover at once.
    await session.close()
    if not url:
        raise HTTPException(status_code=404, detail="no cover for this series")
    root = get_settings().reader_cache_path / "covers"
    path = covers.cached(root, url)
    if path is None:
        data = await covers.fetch(url, transport=covers.TRANSPORT)
        if data is None:
            # Nothing is stored, so the next request tries the CDN again.
            raise HTTPException(status_code=404, detail="the cover could not be fetched")
        path = covers.store(root, url, data)
    etag = f'"{covers.key(url)}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=86400"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    extension = path.suffix.lstrip(".")
    return Response(
        content=path.read_bytes(),
        media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers=headers,
    )


@router.get("/{series_id}")
async def series_detail(series_id: int, session: Session) -> dict[str, Any]:
    result = await session.execute(
        text(LIST_SQL_ONE), {"id": series_id, "writable": writable_providers()}
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="series not found")

    chapters = await session.execute(
        text(
            """
            select id, number, title, state, file_path, komga_book_id, available_until,
                   bookmarked
              from chapter where series_id = :id order by number
            """
        ),
        {"id": series_id},
    )
    volumes = await session.execute(
        text(
            """
            select number, title, status, state, last_updated, komga_book_id,
                   (downloaded_updated is not null and last_updated is not null
                    and downloaded_updated < last_updated) as revised
              from volume where series_id = :id order by number
            """
        ),
        {"id": series_id},
    )
    entries = await session.execute(
        text(
            """
            select e.provider, e.provider_media_id, e.status, e.user_progress_chapter,
                   e.user_progress_volume, e.updated_at, e.raw,
                   exists (
                       select 1 from provider_token t where t.provider = 'anilist'
                   ) as anilist_connected
              from list_entry e
             where e.series_id = :id
             order by e.updated_at desc nulls last, e.provider
            """
        ),
        {"id": series_id},
    )
    # Newest first, because metadata_of resolves a field both providers report
    # in favour of the first raw that answers.
    entry_rows = entries.all()
    enrichment = (row.meta or {}).get("enrichment")

    days = await rhythm.release_days(session, [series_id])
    result = {
        "series": _row_to_series(row),
        # Observed, not stated: how often chapters have turned up here. None
        # until enough have, which is most series for their first month.
        "rhythm_days": rhythm.rhythm_days(days.get(series_id, [])),
        "metadata": metadata_of([entry.raw for entry in entry_rows], enrichment),
        "mapping": {"source_site": row.source_site, "source_url": row.source_url}
        if row.source_url
        else None,
        "chapters": [
            {
                "id": c.id,
                "number": float(c.number),
                "title": c.title,
                "state": c.state,
                "file_path": c.file_path,
                # Only a book Komga has indexed can be opened in its reader, so
                # this is null for every chapter that is not downloaded yet -
                # and the row simply does not offer a link.
                "komga_book_id": c.komga_book_id,
                "available_until": c.available_until.isoformat() if c.available_until else None,
                "bookmarked": c.bookmarked,
            }
            for c in chapters.all()
        ],
        "volumes": [
            {
                "number": float(v.number),
                "title": v.title,
                "status": v.status,
                "state": v.state,
                "last_updated": v.last_updated.isoformat() if v.last_updated else None,
                "revised": bool(v.revised),
                "komga_book_id": v.komga_book_id,
            }
            for v in volumes.all()
        ],
        "entries": [
            {
                "provider": e.provider,
                "provider_media_id": e.provider_media_id,
                "status": e.status,
                "user_progress_chapter": e.user_progress_chapter,
                "user_progress_volume": e.user_progress_volume,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in entry_rows
        ],
        # The detail screen derives "chapters left, about Nh" from this. Served
        # here rather than fetched from /api/settings, which would cost the
        # screen a second request for the whole settings blob and its provider
        # health with it.
        "reading_minutes_per_chapter": await settings_store.get_int(
            session, settings_store.READING_MINUTES_PER_CHAPTER
        ),
        # Served here for the same reason as the line above: the screen needs it
        # to build a reader link, and fetching /api/settings for one string would
        # cost it the whole settings blob and its provider health with it. Empty
        # means no link is offered at all.
        "komga_public_url": (
            await settings_store.get(session, settings_store.KOMGA_PUBLIC_URL)
        ).rstrip("/"),
        "reading_frequency": await reading_frequency(session, series_id),
    }

    await _resolve_similar(session, result["metadata"])

    # Opening the page is what asks for the extras. A job rather than a fetch
    # in the request path: AniList rate-limits, and a detail page must not fail
    # to render because a third party was slow.
    #
    # Queuing this with no AniList token stored made the handler raise
    # PermanentError on every run — is_stale never turns false, so every visit
    # to the page added one more failure the jobs screen never lost.
    if (
        is_stale(enrichment, datetime.now(UTC))
        and any(entry.provider == str(Provider.ANILIST) for entry in entry_rows)
        and any(entry.anilist_connected for entry in entry_rows)
    ):
        await repo.enqueue(
            session,
            JobType.MEDIA_ENRICH,
            {"series_id": series_id},
            priority=50,
            series_id=series_id,
            dedupe_key=f"media_enrich:{series_id}",
        )
        await session.commit()

    return result


@router.get("/{series_id}/candidates")
async def list_candidates(series_id: int, session: Session) -> dict[str, Any]:
    series = await session.execute(
        text(
            """
            select s.id, s.canonical_title, s.meta,
                   array_remove(array_agg(distinct e.title_english), null) as english,
                   array_remove(array_agg(distinct e.title_romaji), null) as romaji
              from series s
              left join list_entry e on e.series_id = s.id
             where s.id = :series_id
             group by s.id
            """
        ),
        {"series_id": series_id},
    )
    header = series.first()
    if header is None:
        raise HTTPException(status_code=404, detail="series not found")

    result = await session.execute(
        text(
            """
            select id, source_site, source_url, title, cover_url, chapter_count, year, score
              from series_candidate
             where series_id = :series_id
             order by score desc
            """
        ),
        {"series_id": series_id},
    )
    return {
        "series": {
            "id": header.id,
            "title": header.canonical_title,
            "titles": (header.meta or {}).get("titles", []),
            "english": header.english,
            "romaji": header.romaji,
            "cover_url": (header.meta or {}).get("cover_url"),
        },
        "candidates": [
            {
                "id": row.id,
                "source_site": row.source_site,
                "source_url": row.source_url,
                "title": row.title,
                "cover_url": row.cover_url,
                "chapter_count": row.chapter_count,
                "year": row.year,
                "score": float(row.score),
            }
            for row in result.all()
        ],
    }


@router.get("/{series_id}/mapping/preview")
async def preview_mapping(series_id: int, source_url: str, session: Session) -> dict[str, Any]:
    """What moving this series to another source would do, before it is done.

    Asks the new source for its chapter list, the one request a move costs, and
    compares it with what is held here. Persists nothing: confirming is still
    POST /mapping, and the first discovery after it applies what this predicts
    (chapter_discover.hand_over).
    """
    try:
        source = source_for_url(source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    expected = await series_kind(session, series_id)
    if kind_of(source) != expected:
        raise HTTPException(
            status_code=422, detail=f"{source.site} publishes {kind_of(source)}, not {expected}"
        )

    rows = (
        await session.execute(
            text("select number, state from chapter where series_id = :id"), {"id": series_id}
        )
    ).all()
    progress = (
        await session.execute(
            text(
                "select coalesce(max(user_progress_chapter), 0) from list_entry"
                " where series_id = :id"
            ),
            {"id": series_id},
        )
    ).scalar_one()
    timeout = await settings_store.get_int(session, settings_store.SOURCE_SEARCH_TIMEOUT)
    # Released before the source is asked, which can take the whole timeout.
    await session.close()

    try:
        listed = await asyncio.wait_for(source.list_chapters(source_url), timeout)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504, detail=f"{source.site} did not answer in {timeout}s"
        ) from exc
    except Exception as exc:  # the source's own words are the answer
        raise HTTPException(status_code=502, detail=f"{source.site}: {exc}"[:300]) from exc

    offered = {chapter.number for chapter in listed}
    held = {row.number: row.state for row in rows}
    fetchable = ("known", "queued", "failed")
    return {
        "source_site": source.site,
        "chapters": len(offered),
        "last": float(max(offered)) if offered else None,
        "current_last": float(max(held)) if held else None,
        "progress": progress,
        # A source that stops before where reading got to cannot carry on from
        # there, which is the one thing a move is usually for.
        "stops_before_progress": bool(offered) and max(offered) < progress,
        "gained": len(offered - held.keys()),
        "retried": sum(1 for n, s in held.items() if n in offered and s in ("failed", "skipped")),
        "set_aside": sum(1 for n, s in held.items() if n not in offered and s in fetchable),
        "downloaded": sum(1 for s in held.values() if s == "downloaded"),
    }


@router.post("/{series_id}/mapping")
async def confirm_mapping(series_id: int, body: MappingIn, session: Session) -> dict[str, Any]:
    """Confirming a mapping is what releases a series into the download pipeline."""
    try:
        source = source_for_url(body.source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # The one place a person can still cross the comic/prose boundary by hand -
    # a pasted link - so it is refused here rather than discovered as a
    # download that writes the wrong kind of file.
    expected = await series_kind(session, series_id)
    if kind_of(source) != expected:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{source.site} publishes {kind_of(source)}, and this series is {expected}. "
                "Change the series kind first if it is wrong."
            ),
        )

    await session.execute(
        text("update source_mapping set active = false where series_id = :series_id"),
        {"series_id": series_id},
    )
    await session.execute(
        text(
            """
            insert into source_mapping (series_id, source_site, source_url, active, confirmed_at)
            values (:series_id, :site, :url, true, now())
            """
        ),
        {"series_id": series_id, "site": source.site, "url": body.source_url},
    )
    await session.execute(
        text("update series set needs_review = false where id = :series_id"),
        {"series_id": series_id},
    )
    job_id = await repo.enqueue(
        session,
        JobType.CHAPTER_DISCOVER,
        {"series_id": series_id},
        priority=0,
        series_id=series_id,
        dedupe_key=f"chapter_discover:{series_id}",
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}


@router.post("/{series_id}/download")
async def download_range(series_id: int, body: DownloadIn, session: Session) -> dict[str, Any]:
    """Manual download. Priority 0 puts it ahead of whatever the cron queued."""
    clauses = [
        "series_id = :series_id",
        "state in ('known', 'failed', 'skipped', 'streaming')",
    ]
    params: dict[str, Any] = {"series_id": series_id}
    if body.from_chapter is not None:
        clauses.append("number >= :from_chapter")
        params["from_chapter"] = body.from_chapter
    if body.to_chapter is not None:
        clauses.append("number <= :to_chapter")
        params["to_chapter"] = body.to_chapter

    result = await session.execute(
        text(f"select id from chapter where {' and '.join(clauses)} order by number"), params
    )
    queued = await queue_batches(
        session, series_id, [row.id for row in result.all()], priority=0
    )
    await session.commit()
    return {"ok": True, "queued": queued}


@router.post("/{series_id}/auto-download")
async def set_auto_download(
    series_id: int, body: AutoDownloadIn, session: Session
) -> dict[str, Any]:
    """Opt a series in or out of automatic downloading.

    Turning it on queues whatever is already missing; leaving it off means the
    series is still tracked and discovered, but nothing is fetched until asked.
    """
    await session.execute(
        text("update series set auto_download = :enabled where id = :series_id"),
        {"enabled": body.enabled, "series_id": series_id},
    )

    queued = 0
    if body.enabled:
        result = await session.execute(
            text(
                """
                select id from chapter
                 where series_id = :series_id and state in ('known', 'streaming')
                 order by number
                """
            ),
            {"series_id": series_id},
        )
        queued = await queue_batches(
            session, series_id, [row.id for row in result.all()], priority=0
        )
    await session.commit()
    return {"ok": True, "auto_download": body.enabled, "queued": queued}


@router.post("/{series_id}/kind")
async def set_kind(series_id: int, body: KindIn, session: Session) -> dict[str, Any]:
    """Say what a series is when no provider did, or when one said it wrong.

    Locked, so the next list sync does not put it back: the providers that
    stay silent about format are exactly the ones a person corrects by hand.
    The active mapping is left alone - if it is now the wrong kind, the
    download refuses it by name, and Review is where a new one is chosen.
    """
    result = await session.execute(
        text(
            """
            update series
               set kind = :kind,
                   meta = jsonb_set(coalesce(meta, '{}'::jsonb), '{kind_locked}', 'true'::jsonb)
             where id = :id
            returning id
            """
        ),
        {"kind": body.kind, "id": series_id},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="series not found")
    # Review's candidates were searched as the old kind. A mapped series has already
    # chosen its source, so only an unmapped one has stale candidates to replace.
    mapped = (
        await session.execute(
            text("select 1 from source_mapping where series_id = :id and active limit 1"),
            {"id": series_id},
        )
    ).first() is not None
    if not mapped:
        await repo.enqueue(
            session,
            JobType.MATCH_SEARCH,
            {"series_id": series_id},
            priority=0,
            series_id=series_id,
            dedupe_key=f"match_search:{series_id}",
        )
    await session.commit()
    return {"ok": True, "kind": body.kind}


@router.get("/{series_id}/chapters")
async def list_chapters(series_id: int, session: Session) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select id, number, title, state, file_path
              from chapter where series_id = :series_id order by number
            """
        ),
        {"series_id": series_id},
    )
    return [
        {
            "id": row.id,
            "number": float(row.number),
            "title": row.title,
            "state": row.state,
            "file_path": row.file_path,
        }
        for row in result.all()
    ]


class BookmarkIn(BaseModel):
    bookmarked: bool


@router.put("/{series_id}/chapters/{chapter_id}/bookmark")
async def set_bookmark(
    series_id: int, chapter_id: int, body: BookmarkIn, session: Session
) -> dict[str, Any]:
    """Mark a chapter to come back to, or clear the mark.

    Read is derived from the lists and never stored here; a bookmark is the one
    thing about a chapter only this installation knows, so it is the one mark
    the chapter row keeps.
    """
    result = await session.execute(
        text(
            """
            update chapter set bookmarked = :bookmarked
             where id = :chapter_id and series_id = :series_id
            returning id
            """
        ),
        {"bookmarked": body.bookmarked, "chapter_id": chapter_id, "series_id": series_id},
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="chapter not found in this series")
    await session.commit()
    return {"ok": True, "bookmarked": body.bookmarked}


@router.post("/{series_id}/search")
async def research(series_id: int, session: Session) -> dict[str, Any]:
    job_id = await repo.enqueue(
        session,
        JobType.MATCH_SEARCH,
        {"series_id": series_id},
        priority=0,
        series_id=series_id,
        dedupe_key=f"match_search:{series_id}",
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}


class RemoveIn(BaseModel):
    ids: list[int]


@router.delete("")
async def remove_series_endpoint(body: RemoveIn, session: Session) -> dict[str, Any]:
    """Remove one or many series, and remember that they were removed.

    A selection is one decision, so the body takes a list and the single case
    is a list of one rather than a second endpoint that drifts from this one.
    """
    removed = await remove_series(session, body.ids)
    await session.commit()
    return {"ok": True, "removed": removed}


@router.post("/{series_id}/queue/top")
async def promote_queue(series_id: int, session: Session) -> dict[str, Any]:
    """Put this series' waiting work at the front of the queue."""
    moved = await repo.promote_series(session, series_id)
    await session.commit()
    return {"ok": True, "moved": moved}


@router.delete("/{series_id}/queue")
async def cancel_queue(series_id: int, session: Session) -> dict[str, Any]:
    """Drop this series' waiting work.

    A job a worker is already running is left alone: nothing can stop one, and
    deleting the row would strand the chapter it is part-way through writing.
    """
    dropped = await repo.cancel_series(session, series_id)
    await session.commit()
    return {"ok": True, "dropped": dropped}


@router.post("/{series_id}/track-local")
async def track_local(series_id: int, session: Session) -> dict[str, Any]:
    """Give a series nothing else will take a chapter for somewhere to keep one.

    Every remote provider here is writable, so this is reachable only while a
    series has no list entry at all — the window after it is created and before
    its first sync lands one. It is still the difference between a reader
    recording what they have read and a control that refuses to move.

    A series a real list already holds is refused rather than given a second
    row: two entries that can both take a chapter is two numbers for one series
    with nothing to say which of them is right.
    """
    title = (
        await session.execute(
            text("select canonical_title from series where id = :id"), {"id": series_id}
        )
    ).scalar_one_or_none()
    if title is None:
        raise HTTPException(status_code=404, detail="series not found")

    held = await session.execute(
        text(
            """
            select provider from list_entry
             where series_id = :id
               and provider <> :local
               and provider = any(cast(:writable as text[]))
             limit 1
            """
        ),
        {"id": series_id, "local": str(Provider.LOCAL), "writable": writable_providers()},
    )
    existing = held.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"{existing} already holds this series and can be written to",
        )

    # The series id is the media id: it is unique, which the provider/media
    # unique index requires, and it is the only identifier a list with no
    # service behind it has.
    await session.execute(
        text(
            """
            insert into list_entry (series_id, provider, provider_media_id, status,
                                    user_progress_chapter, title_english, synonyms, raw)
            values (:id, :local, :media_id, :status, 0, :title, '[]'::jsonb, '{}'::jsonb)
            on conflict (provider, provider_media_id) do nothing
            """
        ),
        {
            "id": series_id,
            "local": str(Provider.LOCAL),
            "media_id": str(series_id),
            # Tracking a series by hand is something a reader does because they
            # are reading it. Nothing else here knows better.
            "status": str(ListStatus.READING),
            "title": title,
        },
    )
    await session.commit()
    return {"tracked": True, "series_id": series_id}


@router.post("/{series_id}/progress")
async def set_progress(series_id: int, body: ProgressIn, session: Session) -> dict[str, Any]:
    """The forward-only guard is enforced here too, not only in the handler.

    Rejecting a backward chapter before it is even queued means the library
    screen learns of the refusal immediately, instead of finding out later
    from a job that failed.
    """
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    # min(), not max(), lives in progress_bounds: see the comment there.
    bounds = await progress_bounds(session, series_id)
    if forward_only(bounds.current, body.chapter) is None:
        raise HTTPException(status_code=409, detail="progress cannot move backwards")

    if bounds.ceiling is not None and body.chapter > bounds.ceiling:
        raise HTTPException(
            status_code=409,
            detail=f"this series is only known to have {bounds.ceiling} chapters",
        )

    await queue_progress_write(session, series_id, body.chapter, source=ProgressSource.MANUAL)
    await session.commit()
    return {"progress": body.chapter, "queued": True}


async def queue_status_write(session: AsyncSession, series_id: int, status: ListStatus) -> None:
    """Queue one status write, carrying the status last asked for.

    A second click while the first is queued raises that job rather than adding
    one, or the status the user moved away from lands on their account second.
    Matching 'leased' too, not only 'pending': a worker can have claimed the row
    by the time the second click arrives, and the dedupe key still refuses a
    fresh insert in that state. The handler re-reads the latest row before
    pushing, which is what keeps this from dropping the click the way updating
    only the pending row would.
    """
    await repo.enqueue(
        session,
        JobType.STATUS_WRITE,
        {"series_id": series_id, "status": str(status)},
        priority=0,
        series_id=series_id,
        dedupe_key=f"status_write:{series_id}",
    )
    await session.execute(
        text(
            """
            update job
               set payload = jsonb_set(payload, '{status}', to_jsonb(cast(:status as text)))
             where type = :type and series_id = :series_id
               and state in ('pending', 'leased')
            """
        ),
        {"status": str(status), "type": str(JobType.STATUS_WRITE), "series_id": series_id},
    )


def writable_providers() -> list[str]:
    """List providers the pipeline can write to, asked of the providers.

    A status the user can change is one that lands somewhere we write. A
    read-only provider's status is something we were told, and it must not
    outrank something the user did — which is what ordering purely by recency
    let it do, every time that provider synced.
    """
    return [str(p) for p in Provider if get_source(p).writable]


def status_write_destinations() -> list[str]:
    """Where a status write actually lands, asked of the providers themselves.

    The interface names these to the user before they apply anything, so the
    list has to be true rather than a constant someone typed once. A provider
    that is read only, or that has no write path yet, must not appear: telling
    someone a change reached a service it never touched is worse than saying
    nothing.
    """
    # The local list is left out on purpose. This is what the interface names
    # to the user before they apply anything — the services a change will
    # reach — and the local list is this database, not a service. Naming it on
    # every batch, when most selections hold no local entry at all, would be
    # the same overstatement the rest of this list exists to avoid.
    outward = [p for p in writable_providers() if p != str(Provider.LOCAL)]
    return [*outward, "komga"]


@router.post("/{series_id}/status")
async def set_list_status(series_id: int, body: StatusIn, session: Session) -> dict[str, Any]:
    """Validated here as well as in the handler, so the screen learns of a
    refusal on the click rather than from a job that failed minutes later."""
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    entries = await session.execute(
        text("select count(*) from list_entry where series_id = :id"), {"id": series_id}
    )
    if entries.scalar_one() == 0:
        raise HTTPException(
            status_code=409, detail="this series is not on any reading list"
        )

    await queue_status_write(session, series_id, body.status)
    await session.commit()
    return {"ok": True, "status": str(body.status), "queued": True}


@router.get("/status/destinations")
async def list_status_destinations() -> dict[str, Any]:
    """Where a status write lands. Read by the batch bar, which names them to
    the user before they apply anything to a selection."""
    return {"destinations": status_write_destinations()}


@router.post("/status")
async def set_list_status_batch(body: BatchStatusIn, session: Session) -> dict[str, Any]:
    """Apply one status to many series.

    One job per series rather than one job for the batch: a provider failing for
    one series must not strand the other twenty-nine, and each retries alone.

    A series that is on no reading list — or that does not exist at all — is
    skipped rather than refused. In a batch the user selected by eye, one such
    row is not a reason to reject the other twenty-nine, and the response names
    the ids that were left out so the screen can say so too. Both cases share
    one `skipped` list because the user can do nothing different about either:
    the id was not queued, and there is no second action to offer.

    Nothing here writes to list_entry. Queueing is the whole of the route, and
    the STATUS_WRITE handler it queues touches `status` and `updated_at` only,
    which is what keeps a status apply from carrying progress with it.
    """
    ids = list(dict.fromkeys(body.series_ids))
    if not ids:
        # A no-op, not an error: the bar can send an empty selection while the
        # grid is still settling, and a 4xx there is a failure toast for
        # nothing having happened.
        return {
            "ok": True,
            "status": str(body.status),
            "queued": 0,
            "skipped": [],
            "destinations": status_write_destinations(),
        }

    rows = await session.execute(
        text(
            """
            select s.id,
                   count(e.id) as entries
              from series s
              left join list_entry e on e.series_id = s.id
             where s.id = any(cast(:ids as bigint[]))
             group by s.id
            """
        ),
        {"ids": ids},
    )
    listed = {row.id: row.entries for row in rows.all()}

    queued: list[int] = []
    skipped: list[int] = []
    for series_id in ids:
        if listed.get(series_id):
            await queue_status_write(session, series_id, body.status)
            queued.append(series_id)
        else:
            skipped.append(series_id)

    await session.commit()
    return {
        "ok": True,
        "status": str(body.status),
        "queued": len(queued),
        "skipped": skipped,
        "destinations": status_write_destinations(),
    }


@router.post("/{series_id}/notes")
async def save_notes(series_id: int, body: NotesIn, session: Session) -> dict[str, Any]:
    """Validated here as well as in the handler, so the screen learns of a
    refusal on the click rather than from a job that failed minutes later."""
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    entries = await session.execute(
        text("select count(*) from list_entry where series_id = :id"), {"id": series_id}
    )
    if entries.scalar_one() == 0:
        raise HTTPException(
            status_code=409, detail="this series is not on any reading list"
        )

    await repo.enqueue(
        session,
        JobType.NOTES_WRITE,
        {"series_id": series_id, "notes": body.notes, "tags": body.tags},
        priority=0,
        series_id=series_id,
        dedupe_key=f"notes_write:{series_id}",
    )
    # One job per series, carrying the note last asked for. A second save
    # while the first is queued raises that job rather than adding one, or the
    # note the user moved away from lands on their account second. Matching
    # 'leased' too, not only 'pending': a worker can have already claimed the
    # row by the time this second save arrives, and the dedupe key still
    # refuses a fresh insert in that state. The handler re-reads the latest
    # row before pushing, which is what keeps this from silently dropping the
    # save the way updating only the pending row would.
    await session.execute(
        text(
            """
            update job
               set payload = cast(:payload as jsonb)
             where type = :type and series_id = :series_id
               and state in ('pending', 'leased')
            """
        ),
        {
            "payload": json.dumps(
                {"series_id": series_id, "notes": body.notes, "tags": body.tags}
            ),
            "type": str(JobType.NOTES_WRITE),
            "series_id": series_id,
        },
    )
    await session.commit()
    return {"ok": True, "queued": True}
