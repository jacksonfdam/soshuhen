"""The source catalogue, as the settings screen reads and writes it.

Paged because the catalogue is generated output that grows to four figures: a
listing that returned all of it would be the one request on this screen that
gets slower every time the generator runs.
"""

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.config import get_settings
from app.enums import JobType
from app.handlers.match_search import source_priorities
from app.queue import repo
from app.sources import jnovel_auth, registry
from app.sources.base import Candidate, SiteSource, all_sources, get_prose_source
from app.sources.jnovelclub import API_BASE as JNC_API_BASE
from app.sources.jnovelclub import SITE as JNC_SITE
from app.sources.jnovelclub import JNovelClubSource
from app.sources.net import CatalogueRow, get_client

router = APIRouter(prefix="/api/sources", tags=["sources"])

Session = Annotated[AsyncSession, Depends(db_session)]

MAX_PAGE_SIZE = 100

# Every parameter is cast before it is compared: asyncpg cannot infer the type
# of a null one, and each of these is null whenever its filter is unused.
FILTERS = """
    (cast(:q as text) is null
        or c.name ilike '%' || cast(:q as text) || '%'
        or c.key ilike '%' || cast(:q as text) || '%')
    and (cast(:lang as text) is null or c.lang = cast(:lang as text))
    and (cast(:nsfw as boolean) is null or c.nsfw = cast(:nsfw as boolean))
    and (cast(:enabled as boolean) is null
        or coalesce(p.enabled, false) = cast(:enabled as boolean))
"""

SELECT_ONE = """
    select c.key, c.name, c.template, c.base_url, c.lang, c.nsfw, c.hand_ported, c.version,
           coalesce(p.enabled, false) as enabled,
           coalesce(p.priority, 100) as priority,
           p.disabled_reason
      from site_catalogue c
      left join source_pref p on p.key = c.key
"""


class SourceIn(BaseModel):
    enabled: bool


def _reason(row: Any) -> str | None:
    """Why this row cannot run, in words the screen can print, or None if it can.

    Computed here rather than on the screen: which templates this deployment
    implements is not something the browser can know, and a row that is disabled
    for a reason nobody states reads as a broken toggle.
    """
    if row["disabled_reason"]:
        return row["disabled_reason"]
    if not row["hand_ported"]:
        return "not hand-ported"
    if row["template"] == "native":
        return None if row["key"] in registry.native_keys() else "no implementation for this site"
    if row["template"] not in registry.TEMPLATE_CLASSES:
        return f"no implementation for the {row['template']} template"
    return None


def _item(row: Any) -> dict[str, Any]:
    return {
        "key": row["key"],
        "name": row["name"],
        "template": row["template"],
        "base_url": row["base_url"],
        "lang": row["lang"],
        "nsfw": row["nsfw"],
        "hand_ported": row["hand_ported"],
        "version": row["version"],
        "enabled": row["enabled"],
        "priority": row["priority"],
        "reason": _reason(row),
    }


@router.get("")
async def list_sources(
    session: Session,
    q: str | None = None,
    lang: str | None = None,
    nsfw: bool | None = None,
    enabled: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    size = max(1, min(size, MAX_PAGE_SIZE))
    page = max(1, page)
    params: dict[str, Any] = {"q": q, "lang": lang, "nsfw": nsfw, "enabled": enabled}

    total = (
        await session.execute(
            text(
                "select count(*) from site_catalogue c"
                " left join source_pref p on p.key = c.key"
                f" where {FILTERS}"
            ),
            params,
        )
    ).scalar_one()

    rows = (
        (
            await session.execute(
                text(f"{SELECT_ONE} where {FILTERS} order by c.name limit :size offset :offset"),
                {**params, "size": size, "offset": (page - 1) * size},
            )
        )
        .mappings()
        .all()
    )

    return {"items": [_item(row) for row in rows], "total": total, "page": page, "size": size}


@router.get("/search")
async def search_sources(session: Session, q: str, kind: str | None = None) -> dict[str, Any]:
    """Every enabled source asked for one title, at once. Persists nothing.

    The same fan-out match_search runs for a series, minus the series: a title
    typed by hand rather than read off a list. Nothing is stored and no mapping
    is made, so the one network request a click costs is the search itself.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="nothing to search for")
    if kind not in (None, "comic", "prose"):
        raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")

    concurrency = await settings_store.get_int(session, settings_store.SOURCE_SEARCH_CONCURRENCY)
    timeout = await settings_store.get_int(session, settings_store.SOURCE_SEARCH_TIMEOUT)
    priorities = await source_priorities(session)
    sources = all_sources(kind=kind)
    gate = asyncio.Semaphore(max(1, concurrency))
    errors: list[dict[str, str]] = []

    async def one(source: SiteSource) -> list[Candidate]:
        async with gate:
            try:
                return await asyncio.wait_for(source.search([query]), timeout)
            except TimeoutError:
                errors.append({"site": source.site, "detail": f"no answer in {timeout}s"})
            except Exception as exc:  # noqa: BLE001 - one dead source is not an empty search
                # Reported rather than swallowed: a result list missing a site
                # that looks complete is how a title gets judged unavailable.
                errors.append({"site": source.site, "detail": str(exc)[:300]})
            return []

    found = [c for results in await asyncio.gather(*map(one, sources)) for c in results]
    found.sort(key=lambda c: (-c.score, priorities.get(c.source_site, 100)))

    # A result the library already maps leads to that series, not back out to
    # the site: the user is a click from reading it, not a mapping away.
    mapped = dict(
        (
            await session.execute(
                text(
                    "select source_url, series_id from source_mapping"
                    " where active and source_url = any(cast(:urls as text[]))"
                ),
                {"urls": [c.source_url for c in found]},
            )
        ).all()
    )

    return {
        "query": query,
        "searched": len(sources),
        "results": [
            {
                "source_site": c.source_site,
                "source_url": c.source_url,
                "title": c.title,
                "cover_url": c.cover_url,
                "chapter_count": c.chapter_count,
                "year": c.year,
                "score": c.score,
                "series_id": mapped.get(c.source_url),
            }
            for c in found
        ],
        "errors": sorted(errors, key=lambda error: error["site"]),
    }


class JncSignIn(BaseModel):
    login: str
    password: str


def _env_signs_in() -> bool:
    settings = get_settings()
    return bool(settings.jnc_login and settings.jnc_password)


@router.post("/jnovelclub/sign-in")
async def jnc_sign_in(body: JncSignIn, session: Session) -> dict[str, Any]:
    """Sign in once and keep only the token.

    The password is used for this one request and goes nowhere else - not to
    the database, not to a log line. When the token lapses, the card says so
    and asks again; that is the price of never storing a password.
    """
    if _env_signs_in():
        raise HTTPException(status_code=409, detail="J-Novel Club is signed in from .env")
    client = get_client(CatalogueRow(key=JNC_SITE, base_url=JNC_API_BASE))
    try:
        signed_in = await jnovel_auth.login(client, body.login, body.password)
    except jnovel_auth.JncAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await settings_store.set_value(session, settings_store.JNC_TOKEN, signed_in.token)
    await settings_store.set_value(
        session, settings_store.JNC_TOKEN_EXPIRES_AT, signed_in.expires_at.isoformat()
    )
    # A fresh sign-in is when the library is most likely to hold something
    # new; waiting up to six hours for the cron would look broken.
    await repo.enqueue(session, JobType.JNC_LIBRARY_SYNC, {}, dedupe_key="jnc_library_sync")
    await session.commit()
    await registry.reload(session)
    return {"signed_in": True, "expires_at": signed_in.expires_at.isoformat()}


@router.post("/jnovelclub/library-sync")
async def jnc_library_sync(session: Session) -> dict[str, Any]:
    job_id = await repo.enqueue(
        session, JobType.JNC_LIBRARY_SYNC, {}, dedupe_key="jnc_library_sync"
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}


@router.delete("/jnovelclub/sign-in")
async def jnc_sign_out(session: Session) -> dict[str, Any]:
    token = await settings_store.stored(session, settings_store.JNC_TOKEN)
    if token:
        client = get_client(CatalogueRow(key=JNC_SITE, base_url=JNC_API_BASE))
        await jnovel_auth.logout(client, token)
    await session.execute(
        text("delete from setting where key = any(cast(:keys as text[]))"),
        {"keys": [settings_store.JNC_TOKEN, settings_store.JNC_TOKEN_EXPIRES_AT]},
    )
    await session.commit()
    await registry.reload(session)
    return {"signed_in": False}


@router.get("/jnovelclub/session")
async def jnc_session(session: Session) -> dict[str, Any]:
    if _env_signs_in():
        via, expires_at = "env", None
    else:
        token = await settings_store.stored(session, settings_store.JNC_TOKEN)
        expires = await settings_store.stored(session, settings_store.JNC_TOKEN_EXPIRES_AT)
        expires_at = datetime.fromisoformat(expires) if token and expires else None
        if expires_at is None or expires_at <= datetime.now(UTC):
            return {"via": "none", "expires_at": None, "level": None}
        via = "settings"
    try:
        source = get_prose_source(JNC_SITE)
    except (ValueError, TypeError):
        source = None
    level = (
        await source.account_level() if isinstance(source, JNovelClubSource) else None
    )
    return {
        "via": via,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "level": level,
    }


@router.put("/{key}")
async def set_source(key: str, body: SourceIn, session: Session) -> dict[str, Any]:
    exists = (
        await session.execute(text("select 1 from site_catalogue where key = :key"), {"key": key})
    ).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"the catalogue has no site {key}")

    await session.execute(
        text(
            """
            insert into source_pref (key, enabled) values (:key, :enabled)
            on conflict (key) do update set enabled = excluded.enabled
            """
        ),
        {"key": key, "enabled": body.enabled},
    )
    await registry.announce_change(session)
    await session.commit()

    # Enabling a site in settings *is* registering it (app/sources/registry.py),
    # so the registry is rebuilt here rather than at the next boot - otherwise
    # the toggle reports success and nothing searches the site until a restart.
    # The announcement above does the same for the workers, which run the
    # searches and the downloads and never see this request.
    await registry.reload(session)

    row = (
        (await session.execute(text(f"{SELECT_ONE} where c.key = :key"), {"key": key}))
        .mappings()
        .one()
    )
    return _item(row)
