"""Runtime settings held in the database, so they change without a redeploy.

Environment variables carry credentials and paths; this table carries the knobs
the interface is allowed to turn.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.enums import Lane

CRON_LIST_SYNC = "cron_list_sync"
CRON_CHAPTER_DISCOVER = "cron_chapter_discover"
CRON_PROGRESS_PUSH = "cron_progress_push"
CRON_ANIME_LIST_SYNC = "cron_anime_list_sync"
CRON_JNC_LIBRARY_SYNC = "cron_jnc_library_sync"
DOWNLOAD_CONCURRENCY = "download_concurrency"
FETCH_CONCURRENCY = "fetch_concurrency"
PER_SOURCE_CONCURRENCY = "per_source_concurrency"
SOURCE_SEARCH_CONCURRENCY = "source_search_concurrency"
SOURCE_SEARCH_TIMEOUT = "source_search_timeout"
DOWNLOAD_BATCH_SIZE = "download_batch_size"
AUTO_DOWNLOAD_NEW = "auto_download_new"
DISCOVER_BY_RHYTHM = "discover_by_rhythm"
COMICK_URL = "comick_url"
COMICK_ENABLED = "comick_enabled"
READING_MINUTES_PER_CHAPTER = "reading_minutes_per_chapter"
KOMGA_PUBLIC_URL = "komga_public_url"
MANGAFIRE_WAF_PASS = "mangafire_waf_pass"
# The J-Novel Club token saved by the Settings sign-in, and when it lapses.
# Deliberately absent from all_settings(): the token is a credential, and
# GET /api/settings sends everything it lists to the browser.
JNC_TOKEN = "jnc_token"
JNC_TOKEN_EXPIRES_AT = "jnc_token_expires_at"
READER_DEFAULT_MODE = "reader_default_mode"
READER_DEFAULT_SCALE = "reader_default_scale"
READER_DEFAULT_BACKGROUND = "reader_default_background"
# The novel reader's, one pair for every novel: type size and page colour are
# about the reader's eyes, not about the book.
READER_PROSE_FONT_SIZE = "reader_prose_font_size"
READER_PROSE_THEME = "reader_prose_theme"
# Who this installation is, for a client that finds it on the LAN and must
# recognise it again after DHCP moves it. An identity, not a knob, so it is
# absent from all_settings().
INSTANCE_ID = "instance_id"


@dataclass(frozen=True)
class Defaults:
    cron_list_sync: str = "0 */6 * * *"
    cron_chapter_discover: str = "0 */2 * * *"
    cron_progress_push: str = "30 * * * *"
    # Twelve hours, not the six or two the reading crons use: an anime list
    # changes when an episode airs, not continuously, and the discovery pass
    # it feeds is expensive.
    cron_anime_list_sync: str = "0 */12 * * *"
    cron_jnc_library_sync: str = "0 */6 * * *"
    per_source_concurrency: int = 2
    # Four at once against five sites: enough that a match search is one round
    # trip rather than five, low enough that a series never has more sockets
    # open than a homelab's connection tracking enjoys.
    source_search_concurrency: int = 4
    # Well under the job lease, deliberately. A source that has not answered in
    # twenty seconds is not about to, and the whole point of the timeout is that
    # its silence costs the other sources nothing.
    source_search_timeout: int = 20
    download_batch_size: int = 20
    auto_download_new: bool = True
    # Off until switched on: it stops asking sources about series that are not
    # due, and a rhythm read wrongly costs a late chapter, so it is a choice.
    discover_by_rhythm: bool = False
    comick_url: str = ""
    comick_enabled: bool = False
    reading_minutes_per_chapter: int = 8
    # Empty, and it stays empty until someone fills it in. `komga_url` is how
    # the worker reaches Komga inside the compose network, which is useless as a
    # link in a browser; there is no way to guess the address the reader is
    # actually served on, and a link that 404s is worse than no link.
    komga_public_url: str = ""
    # Empty, and only a person can fill it in. MangaFire gates its API behind a
    # challenge that is solved in a browser by a human; the cookie that solving
    # it produces is what this holds. Nothing here solves the challenge.
    mangafire_waf_pass: str = ""
    # Right to left because most of what this library holds is manga; a
    # webtoon is one tap away and remembered per series after that.
    reader_default_mode: str = "paged_rtl"
    reader_default_scale: str = "fit_screen"
    reader_default_background: str = "black"
    reader_prose_font_size: int = 3
    reader_prose_theme: str = "dark"


DEFAULTS = Defaults()


def _fallback(key: str) -> str:
    match key:
        case k if k == CRON_LIST_SYNC:
            return DEFAULTS.cron_list_sync
        case k if k == CRON_CHAPTER_DISCOVER:
            return DEFAULTS.cron_chapter_discover
        case k if k == CRON_PROGRESS_PUSH:
            return DEFAULTS.cron_progress_push
        case k if k == CRON_ANIME_LIST_SYNC:
            return DEFAULTS.cron_anime_list_sync
        case k if k == CRON_JNC_LIBRARY_SYNC:
            return DEFAULTS.cron_jnc_library_sync
        case k if k == DOWNLOAD_CONCURRENCY:
            return str(get_settings().download_concurrency)
        case k if k == FETCH_CONCURRENCY:
            # The same number downloads already used. Splitting the lanes
            # changes what competes for a slot and nothing else: neither lane
            # runs hotter than the single pool did, and no source sees new load.
            return str(get_settings().download_concurrency)
        case k if k == PER_SOURCE_CONCURRENCY:
            return str(DEFAULTS.per_source_concurrency)
        case k if k == SOURCE_SEARCH_CONCURRENCY:
            return str(DEFAULTS.source_search_concurrency)
        case k if k == SOURCE_SEARCH_TIMEOUT:
            return str(DEFAULTS.source_search_timeout)
        case k if k == DOWNLOAD_BATCH_SIZE:
            return str(DEFAULTS.download_batch_size)
        case k if k == AUTO_DOWNLOAD_NEW:
            return "true" if DEFAULTS.auto_download_new else "false"
        case k if k == DISCOVER_BY_RHYTHM:
            return "true" if DEFAULTS.discover_by_rhythm else "false"
        case k if k == COMICK_URL:
            return DEFAULTS.comick_url
        case k if k == COMICK_ENABLED:
            return "true" if DEFAULTS.comick_enabled else "false"
        case k if k == READING_MINUTES_PER_CHAPTER:
            return str(DEFAULTS.reading_minutes_per_chapter)
        case k if k == KOMGA_PUBLIC_URL:
            return DEFAULTS.komga_public_url
        case k if k == MANGAFIRE_WAF_PASS:
            return DEFAULTS.mangafire_waf_pass
        case k if k == READER_DEFAULT_MODE:
            return DEFAULTS.reader_default_mode
        case k if k == READER_DEFAULT_SCALE:
            return DEFAULTS.reader_default_scale
        case k if k == READER_DEFAULT_BACKGROUND:
            return DEFAULTS.reader_default_background
        case k if k == READER_PROSE_FONT_SIZE:
            return str(DEFAULTS.reader_prose_font_size)
        case k if k == READER_PROSE_THEME:
            return DEFAULTS.reader_prose_theme
        case _:
            return ""


async def stored(session: AsyncSession, key: str) -> str | None:
    """The value someone set, or None when nothing has been.

    `get` cannot answer this: it folds "never set" into the packaged default,
    which is right for a reader and wrong for anything that has to tell a
    deliberate choice from an absence.
    """
    result = await session.execute(
        text("select value from setting where key = :key"), {"key": key}
    )
    row = result.first()
    return row[0] if row else None


async def get(session: AsyncSession, key: str) -> str:
    raw = await stored(session, key)
    return raw if raw is not None else _fallback(key)


async def get_int(session: AsyncSession, key: str) -> int:
    raw = await get(session, key)
    try:
        return int(raw)
    except ValueError:
        return int(_fallback(key))


async def get_bool(session: AsyncSession, key: str) -> bool:
    return (await get(session, key)).strip().lower() in {"1", "true", "yes", "on"}


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    await session.execute(
        text(
            """
            insert into setting (key, value) values (:key, :value)
            on conflict (key) do update set value = excluded.value
            """
        ),
        {"key": key, "value": value},
    )


async def all_settings(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(text("select key, value from setting"))
    stored = dict(result.all())
    keys = [
        CRON_LIST_SYNC,
        CRON_CHAPTER_DISCOVER,
        CRON_PROGRESS_PUSH,
        CRON_ANIME_LIST_SYNC,
        CRON_JNC_LIBRARY_SYNC,
        DOWNLOAD_CONCURRENCY,
        PER_SOURCE_CONCURRENCY,
        SOURCE_SEARCH_CONCURRENCY,
        SOURCE_SEARCH_TIMEOUT,
        DOWNLOAD_BATCH_SIZE,
        AUTO_DOWNLOAD_NEW,
        DISCOVER_BY_RHYTHM,
        COMICK_URL,
        COMICK_ENABLED,
        READING_MINUTES_PER_CHAPTER,
        KOMGA_PUBLIC_URL,
        MANGAFIRE_WAF_PASS,
    ]
    return {key: stored.get(key, _fallback(key)) for key in keys}


async def concurrency_for(session: AsyncSession, lane: Lane) -> int:
    """How many jobs this lane may run at once.

    An unset fetch_concurrency inherits the tuned download_concurrency rather
    than the packaged default. Before the lanes there was one pool and it ran
    at whatever download_concurrency had been set to; falling back to the
    default would have cut those jobs from that number to three on the first
    restart, which is a throughput change nobody asked for. Once fetch has a
    number of its own, that number rules.
    """
    if lane is Lane.DOWNLOAD:
        return await get_int(session, DOWNLOAD_CONCURRENCY)

    raw = await stored(session, FETCH_CONCURRENCY)
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass
    return await get_int(session, DOWNLOAD_CONCURRENCY)
