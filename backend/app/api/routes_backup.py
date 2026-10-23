"""A Mihon backup, out and in.

Out: every series with a confirmed source, as a .tachibk Mihon restores, with
each chapter read up to where the lists say and the bookmarks kept here.

In: a backup is read against the library, never into it. A series it holds is
found by the tracker it is linked to in Mihon, or by its title, and a series
already here that has no source yet takes the one Mihon read it from. That is a
mapping confirmed without the review step, which is the deliberate stop the
pipeline keeps everywhere else: it is allowed here because the backup records
a choice the reader already made, in Mihon, and because the same request run
with apply=false shows every one of them first. Nothing a backup holds creates
a series; series come from the lists.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import JobType, Provider
from app.handlers.match_search import series_kind
from app.mihon.backup import (
    TRACKER_ANILIST,
    TRACKER_MAL,
    TRACKER_MANGABAKA,
    MihonBackup,
    MihonChapter,
    MihonManga,
    MihonTracking,
    read_backup,
    source_id,
    write_backup,
)
from app.queue import repo
from app.sources import kind_of, source_for_url
from app.text_utils import normalize

router = APIRouter(prefix="/api/backup", tags=["backup"])

Session = Annotated[AsyncSession, Depends(db_session)]

# A backup of a few thousand titles is a few megabytes; this is room to spare
# without reading an arbitrary upload into memory.
MAX_UPLOAD = 64 * 1024 * 1024

TRACKER_OF: dict[str, int] = {
    Provider.MAL: TRACKER_MAL,
    Provider.ANILIST: TRACKER_ANILIST,
    Provider.MANGABAKA: TRACKER_MANGABAKA,
}
PROVIDER_OF = {tracker: provider for provider, tracker in TRACKER_OF.items()}

# Each tracker's own status numbers, from its class in Mihon's data/track.
# MyAnimeList skips 5; the other two do not.
STATUS_OF: dict[str, dict[str, int]] = {
    Provider.MAL: {"reading": 1, "completed": 2, "on_hold": 3, "dropped": 4, "plan_to_read": 6},
    Provider.ANILIST: {"reading": 1, "completed": 2, "on_hold": 3, "dropped": 4, "plan_to_read": 5},
    Provider.MANGABAKA: {
        "reading": 1, "completed": 2, "on_hold": 3, "dropped": 4, "plan_to_read": 5,
    },
}

TRACKER_URL = {
    Provider.MAL: "https://myanimelist.net/manga/{id}",
    Provider.ANILIST: "https://anilist.co/manga/{id}",
}

# MangaDex is the one native source whose addresses differ from its Mihon
# extension's: this one stores the site's /title/ link, the extension the API's
# /manga/ path. Every generated source was ported from the extension and
# already uses its paths.
MANGADEX = "mangadex"


def mihon_url(site: str, url: str) -> str:
    """A Soshuhen address as the Mihon extension keeps it: a path on the site."""
    parts = urlsplit(url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    if site == MANGADEX and path.startswith("/title/"):
        return "/manga/" + path.removeprefix("/title/").split("/")[0]
    return path


def soshuhen_url(site: str, base_url: str, url: str) -> str:
    """The reverse: a Mihon path as an address a Soshuhen source owns."""
    if url.startswith(("http://", "https://")):
        return url
    if site == MANGADEX and url.startswith("/manga/"):
        return "https://mangadex.org/title/" + url.removeprefix("/manga/")
    return base_url.rstrip("/") + "/" + url.lstrip("/")


@router.get("/mihon")
async def export_mihon(session: Session) -> Response:
    series = (
        await session.execute(
            text(
                """
                select s.id, s.canonical_title, s.meta->>'cover_url' as cover_url,
                       m.source_site, m.source_url, c.name, c.lang
                  from series s
                  join source_mapping m on m.series_id = s.id and m.active
                  left join site_catalogue c on c.key = m.source_site
                 order by s.canonical_title
                """
            )
        )
    ).all()
    chapters: dict[int, list[Any]] = {}
    for row in (
        await session.execute(
            text(
                "select series_id, number, title, source_url, bookmarked from chapter"
                " where source_url is not null order by series_id, number"
            )
        )
    ).all():
        chapters.setdefault(row.series_id, []).append(row)
    entries: dict[int, list[Any]] = {}
    for row in (
        await session.execute(
            text(
                "select series_id, provider, provider_media_id, status, user_progress_chapter"
                " from list_entry"
            )
        )
    ).all():
        entries.setdefault(row.series_id, []).append(row)

    backup = MihonBackup()
    for row in series:
        # A source missing from the catalogue still gets an id, from its key:
        # Mihon restores the title under a source it does not have, and its
        # migration screen moves it to one it does.
        name, lang = row.name or row.source_site, row.lang or "en"
        sid = source_id(name, lang)
        backup.sources[sid] = name
        held = entries.get(row.id, [])
        progress = max((e.user_progress_chapter or 0 for e in held), default=0)
        backup.mangas.append(
            MihonManga(
                source_id=sid,
                url=mihon_url(row.source_site, row.source_url),
                title=row.canonical_title,
                thumbnail_url=row.cover_url,
                chapters=[
                    MihonChapter(
                        url=mihon_url(row.source_site, c.source_url),
                        name=c.title or f"Chapter {c.number.normalize():f}",
                        number=float(c.number),
                        # Lists count whole chapters, so 23.5 is read at 24.
                        read=c.number <= progress,
                        bookmark=c.bookmarked,
                    )
                    for c in chapters.get(row.id, [])
                ],
                tracking=[
                    MihonTracking(
                        tracker=TRACKER_OF[e.provider],
                        media_id=int(e.provider_media_id),
                        url=TRACKER_URL.get(e.provider, "").format(id=e.provider_media_id),
                        title=row.canonical_title,
                        last_chapter_read=float(e.user_progress_chapter or 0),
                        status=STATUS_OF[e.provider].get(e.status or "", 0),
                    )
                    for e in held
                    if e.provider in TRACKER_OF and str(e.provider_media_id).isdigit()
                ],
            )
        )

    filename = f"soshuhen_{datetime.now(UTC):%Y-%m-%d_%H-%M}.tachibk"
    return Response(
        write_backup(backup),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@dataclass
class _Catalogue:
    by_name: dict[str, list[Any]]


async def _catalogue(session: AsyncSession) -> _Catalogue:
    rows = (await session.execute(text("select key, name, lang, base_url from site_catalogue"))).all()
    by_name: dict[str, list[Any]] = {}
    for row in rows:
        by_name.setdefault(row.name.lower(), []).append(row)
    return _Catalogue(by_name)


def _resolve(catalogue: _Catalogue, backup: MihonBackup, manga: MihonManga) -> tuple[str, str] | str:
    """(site, url) for a backed-up title's source, or why there is none.

    By name first, since a backup lists the name of every source it uses, then
    by the id among that name's languages. One row of the name is taken even
    when the id disagrees: the extension overrode its id, which is common, and
    a name is rarely shared by two sites.
    """
    name = backup.sources.get(manga.source_id)
    if not name:
        return "the backup does not name this title's source"
    rows = catalogue.by_name.get(name.lower(), [])
    if not rows:
        return f"{name} is not a source Soshuhen knows"
    chosen = next((r for r in rows if source_id(r.name, r.lang) == manga.source_id), None)
    if chosen is None:
        if len(rows) > 1:
            return f"{name} exists in {len(rows)} languages here and the backup's id matches none"
        chosen = rows[0]
    url = soshuhen_url(chosen.key, chosen.base_url, manga.url)
    try:
        site = source_for_url(url).site
    except ValueError:
        return f"{name} is not enabled here"
    return site, url


async def _match(session: AsyncSession, manga: MihonManga, titles: dict[str, int]) -> tuple[int, str] | None:
    for track in manga.tracking:
        provider = PROVIDER_OF.get(track.tracker)
        if provider is None or not track.media_id:
            continue
        found = (
            await session.execute(
                text(
                    "select series_id from list_entry"
                    " where provider = :provider and provider_media_id = :media_id"
                ),
                {"provider": str(provider), "media_id": str(track.media_id)},
            )
        ).scalar_one_or_none()
        if found is not None:
            return found, f"linked to the same {provider} entry"
    found = titles.get(normalize(manga.title))
    return (found, "same title") if found is not None else None


@router.post("/mihon")
async def import_mihon(request: Request, session: Session, apply: bool = False) -> dict[str, Any]:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="no file in the request")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="the file is larger than any backup should be")
    try:
        backup = read_backup(data)
    except (ValueError, OSError, EOFError) as exc:
        raise HTTPException(status_code=400, detail=f"not a Mihon backup: {exc}") from exc

    catalogue = await _catalogue(session)
    titles = {
        normalize(row.canonical_title): row.id
        for row in (await session.execute(text("select id, canonical_title from series"))).all()
    }
    mapped = dict(
        (await session.execute(text("select series_id, source_url from source_mapping where active"))).all()
    )

    items = []
    for manga in backup.mangas:
        if not manga.favorite:
            continue
        item: dict[str, Any] = {"title": manga.title, "series_id": None, "action": "unmatched"}
        items.append(item)
        match = await _match(session, manga, titles)
        if match is None:
            item["reason"] = "no series here holds it; series come from your lists"
            continue
        series_id, how = match
        item.update(series_id=series_id, matched_by=how)
        bookmarked = [c.number for c in manga.chapters if c.bookmark]
        item["bookmarks"] = len(bookmarked)

        resolved = _resolve(catalogue, backup, manga)
        if isinstance(resolved, str):
            item.update(action="kept", reason=resolved)
        else:
            site, url = resolved
            item.update(source_site=site, source_url=url)
            if mapped.get(series_id) == url:
                item["action"] = "same"
            elif series_id in mapped:
                item.update(action="kept", reason="already reads from another source here")
            elif kind_of(source_for_url(url)) != await series_kind(session, series_id):
                item.update(action="kept", reason=f"{site} publishes another kind of work")
            else:
                item["action"] = "map"
                if apply:
                    await _confirm(session, series_id, site, url)
                    mapped[series_id] = url

        if apply and bookmarked:
            await session.execute(
                text(
                    "update chapter set bookmarked = true where series_id = :id"
                    " and number = any(cast(:numbers as numeric[]))"
                ),
                {"id": series_id, "numbers": bookmarked},
            )

    if apply:
        await session.commit()
    counts: dict[str, int] = {}
    for item in items:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    return {"applied": apply, "titles": len(items), "counts": counts, "items": items}


async def _confirm(session: AsyncSession, series_id: int, site: str, url: str) -> None:
    """POST /api/series/{id}/mapping, for a series that has no mapping to supersede."""
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active, confirmed_at)"
            " values (:id, :site, :url, true, now())"
        ),
        {"id": series_id, "site": site, "url": url},
    )
    await session.execute(
        text("update series set needs_review = false where id = :id"), {"id": series_id}
    )
    await repo.enqueue(
        session,
        JobType.CHAPTER_DISCOVER,
        {"series_id": series_id},
        priority=0,
        series_id=series_id,
        dedupe_key=f"chapter_discover:{series_id}",
    )
