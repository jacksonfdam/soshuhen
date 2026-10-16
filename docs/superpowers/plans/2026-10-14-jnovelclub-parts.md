# J-Novel Club Parts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A light novel J-Novel Club publishes can be mapped to J-Novel Club. Its pre-publication parts are downloaded with the user's Premium sign-in, one EPUB per part, and read in Komga, and progress flows to MAL and AniList.

**Architecture:**
- A native `JNovelClubSource(ProseSource)` is built on each registry reload. It gets a `TokenKeeper` that either signs in with `.env` credentials, or loads the token saved from Settings each time it needs one. Loading it at use time is what lets the boot-time worker registries see a later sign-in.
- Parts flow through the existing prose pipeline unchanged.
- One new chapter column, `available_until`, drives an expiry warning.
- Progress for prose series is capped at the list's chapter total.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Alembic, httpx, selectolax 0.4, pytest + pytest-asyncio; React + TypeScript + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-10-14-jnovelclub-parts-design.md`. Read it before starting any task.

## Global Constraints

- Branch `feat/jnovelclub-parts`, based on `feat/light-novels`. Commit there.
- Commits: English, one focused change per commit, **no assistant attribution of any kind**. The user's global `CLAUDE.md` forbids it, and the repo's `attribution-check` CI fails on it.
- Tests run against a throwaway Postgres. Start it once:
  `docker run -d --name manga-pg-jnc -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5434:5432 postgres:17-alpine`.
  From `backend/`, run `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest <files> -q`. Run only the brief's tests plus the existing modules covering code you changed; never the full suite (it runs once in the last task).
- Lint every task: `.venv/bin/python -m ruff check app/ tests/` from `backend/`.
- `sources/` never touches the database, except `sources/registry.py`, which already does. `sources/` never imports from `downloader/`.
- asyncpg cannot infer a null parameter's type: write `cast(:x as text)` (or `timestamptz`) wherever a bound value may be null.
- Comments explain why a line exists, never what it does.
- **No password is ever stored, logged or returned.** The Settings sign-in keeps only the token and its expiry, in `setting` keys `jnc_token` and `jnc_token_expires_at`, which `GET /api/settings` must never return.
- Never use J-Novel Club endpoints other than those listed in the spec's API contract table, plus `/app/v2/parts/{slug}`. The rate limit is 1 request per second.
- Kind values are `"comic"` and `"prose"`. Null behaves as comic.
- Frontend: no hex, px or rem literals. Every new Tailwind class must be found by `grep` in `frontend/dist/` after `npm run build`. Feature folders never import from each other. Never run `docker compose`.
- Recorded J-Novel Club fixtures live in the session scratchpad at `/private/tmp/claude-501/-Users-jackson-mafra-Downloads-Projects-soshuhen/aa9ec06c-f56d-43b2-86eb-e4332ea25803/scratchpad/verify-jnc/tests/fixtures/sources/`. Copy them; do not re-fetch unless they are missing.

### Rulings this plan makes beyond the spec

- **The token is loaded at use, not at reload.** The spec has the registry build the keeper "from the stored session". Workers load the registry once at boot, so a sign-in made afterwards in the web interface would never reach the download lane. The keeper instead takes a loader that reads `setting` on every `token()` call. The loader lives in `registry.py`, which may touch the database.
- **Parts whose `launch` is in the future are not listed.** J-Novel Club's aggregate can include announced parts. They answer 403 to everyone, and listing them would queue downloads that cannot succeed. `jncep` skips them the same way.
- **The expiry time is 10:00 UTC.** J-Novel Club's web app builds it in the browser's local timezone; `jncep` uses UTC. The 7-day warning does not depend on the hour.
- **The session ttl is parsed as a protobuf Duration.** The login answer is a protobuf `Session` rendered as JSON, where a Duration is a string like `"1209600s"`. Plain numbers are accepted too, and anything else falls back to the requested ttl.

## Review Focus

1. **A Settings token expires in the middle of a batch.** Expected: the batch's unfetched chapters go back to `known`, chapters already saved stay saved and get their Komga scan, and the job fails with "sign in again", with nothing marked skipped. Pinned in Task 7 (`test_an_expired_sign_in_leaves_the_chapters_known`).
2. **Several downloads ask for a token while the `.env` session is renewing.** Expected: exactly one sign-in. Pinned in Task 1 (`test_env_credentials_sign_in_once_for_concurrent_callers`).
3. **A part number above the list's chapter total.** Apothecary part 216 against a MAL total of, say, 150. Expected for prose: progress is capped at the total, with a log line, and comics are unchanged. Pinned in Task 8 (`test_prose_progress_is_capped_at_the_lists_total`, `test_comic_progress_is_never_capped`).
4. **The token leaks through the generic settings endpoint, or the password ends up in a log or a row.** Expected: neither. Pinned in Task 4 (`test_the_token_never_reaches_get_settings`, `test_the_password_is_neither_stored_nor_logged`).
5. **A sign-in made in the web interface after the workers booted.** Expected: the next download uses it with no restart. Pinned in Task 3 (`test_a_token_saved_after_the_registry_loaded_is_used`).

---

## File Structure

**Create:**
- `backend/app/sources/jnovel_auth.py`: `JncSession`, `JncAuthError`, `login`, `logout`, `TokenKeeper`.
- `backend/app/sources/jnovelclub.py`: `JNovelClubSource`, `expires_at`.
- `backend/alembic/versions/0021_seed_jnovelclub.py` and `0022_chapter_available_until.py`.
- `frontend/src/features/settings/JNovelClubCard.tsx`.
- Tests: `tests/test_jnovel_auth.py`, `tests/test_source_jnovelclub.py`, `tests/test_jnovelclub_registry.py`, `tests/test_jnovelclub_routes.py`, `tests/test_chapter_expiry.py`.
- Fixtures: `tests/fixtures/sources/jnovelclub_{search.json,aggregate.json,part.xhtml}`.

**Modify:**

| File | Change |
|---|---|
| `backend/app/sources/base.py` | `ChapterRef.available_until` |
| `backend/app/config.py` | `jnc_login`, `jnc_password` |
| `backend/app/settings_store.py` | `JNC_TOKEN`, `JNC_TOKEN_EXPIRES_AT` |
| `backend/app/sources/registry.py` | build the source; stored-session loader |
| `backend/app/api/routes_sources.py` | sign-in, sign-out, session |
| `backend/app/handlers/chapter_discover.py` | store `available_until`; warn |
| `backend/app/api/routes_series.py` | `expiring`, and `available_until` on chapters |
| `backend/app/handlers/download_batch.py`, `download_chapter.py` | `NotConfigured` |
| `backend/app/handlers/progress_push.py` | cap for prose |
| `frontend/src/lib/api.ts`, `features/settings/SettingsPage.tsx`, `features/series/SeriesHeader.tsx`, `features/series/ChapterTable.tsx`, `features/library/CoverCard.tsx` | sign-in card and expiry display |
| `docs/features.md`, `docs/configuration.md`, `docs/data-model.md`, `.env.example` | docs |

---

### Task 1: Sign-in and the token keeper

**Files:**
- Create: `backend/app/sources/jnovel_auth.py`
- Test: `backend/tests/test_jnovel_auth.py`

**Interfaces:**
- Consumes: `NotConfigured` from `app.sources.base`.
- Produces:
  - `JncSession(token: str, expires_at: datetime)`, frozen.
  - `JncAuthError(RuntimeError)`.
  - `async login(client, login_name, password, *, ttl=1_209_600, now=...) -> JncSession`.
  - `async logout(client, token) -> None`.
  - `TokenKeeper(client, *, login_name="", password="", load_stored: Callable[[], Awaitable[JncSession | None]] | None = None, now=...)`, with:
    - `.via -> "env" | "settings" | "none"`
    - `async .token() -> str`
    - `async .invalidate(token: str) -> None`
  - Module constant `API = "https://labs.j-novel.club/app/v2"`.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_jnovel_auth.py`:

```python
"""J-Novel Club sign-in and the token keeper, against a mocked API."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.sources.base import NotConfigured
from app.sources.jnovel_auth import JncAuthError, JncSession, TokenKeeper, login

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_login_sends_the_body_the_web_app_sends_and_reads_the_token():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(201, json={"id": "tok-1", "ttl": "1209600s", "created": "x"})

    async with _client(handler) as client:
        # A protobuf Duration renders as "1209600s" in JSON.
        session = await login(client, "me@example.test", "pw", now=lambda: NOW)

    assert seen[0].url.path == "/app/v2/auth/login"
    assert seen[0].url.params["format"] == "json"
    assert json.loads(seen[0].content) == {
        "login": "me@example.test", "password": "pw", "slim": True, "ttl": 1209600,
    }
    assert session == JncSession("tok-1", NOW + timedelta(seconds=1209600))


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "wrong email or password"), (429, "too many sign-in attempts")],
)
async def test_login_refusals_say_why(status, message):
    async with _client(lambda request: httpx.Response(status)) as client:
        with pytest.raises(JncAuthError, match=message):
            await login(client, "me@example.test", "pw")


async def test_env_credentials_sign_in_once_for_concurrent_callers():
    logins = 0

    async def handler(request):
        nonlocal logins
        logins += 1
        await asyncio.sleep(0.01)
        return httpx.Response(201, json={"id": f"tok-{logins}", "ttl": 1209600})

    async with _client(handler) as client:
        keeper = TokenKeeper(client, login_name="me", password="pw", now=lambda: NOW)
        tokens = await asyncio.gather(*(keeper.token() for _ in range(5)))

    assert logins == 1
    assert set(tokens) == {"tok-1"}


async def test_env_credentials_renew_an_hour_before_expiry_and_after_a_refusal():
    clock = [NOW]
    logins = 0

    def handler(request):
        nonlocal logins
        logins += 1
        return httpx.Response(201, json={"id": f"tok-{logins}", "ttl": 7200})

    async with _client(handler) as client:
        keeper = TokenKeeper(client, login_name="me", password="pw", now=lambda: clock[0])
        assert await keeper.token() == "tok-1"
        clock[0] = NOW + timedelta(minutes=59)
        assert await keeper.token() == "tok-1"
        clock[0] = NOW + timedelta(minutes=61)
        assert await keeper.token() == "tok-2"
        await keeper.invalidate("tok-2")
        assert await keeper.token() == "tok-3"


async def test_a_stored_token_is_used_until_it_expires_then_asks_for_a_sign_in():
    clock = [NOW]

    async def load():
        return JncSession("saved", NOW + timedelta(days=3))

    async with _client(lambda request: httpx.Response(500)) as client:
        keeper = TokenKeeper(client, load_stored=load, now=lambda: clock[0])
        assert keeper.via == "settings"
        assert await keeper.token() == "saved"
        clock[0] = NOW + timedelta(days=4)
        with pytest.raises(NotConfigured, match="expired"):
            await keeper.token()


async def test_a_stored_token_the_server_refused_is_not_offered_again():
    async def load():
        return JncSession("saved", NOW + timedelta(days=3))

    async with _client(lambda request: httpx.Response(500)) as client:
        keeper = TokenKeeper(client, load_stored=load, now=lambda: NOW)
        await keeper.invalidate("saved")
        with pytest.raises(NotConfigured, match="sign in again"):
            await keeper.token()


async def test_no_credentials_and_nothing_stored_is_not_configured():
    async def load():
        return None

    async with _client(lambda request: httpx.Response(500)) as client:
        assert TokenKeeper(client).via == "none"
        with pytest.raises(NotConfigured, match="not signed in"):
            await TokenKeeper(client).token()
        with pytest.raises(NotConfigured, match="not signed in"):
            await TokenKeeper(client, load_stored=load).token()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovel_auth.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.sources.jnovel_auth'`.

- [ ] **Step 3: Implement.** `backend/app/sources/jnovel_auth.py`. This code was run against the test above during planning and passed:

```python
"""J-Novel Club sign-in, and the token every authenticated call carries.

J-Novel Club publishes no API documentation. The contract here was read from
its own web app (labs.j-novel.club/app/v2) and observed live: sign-in returns
a session whose `id` is a bearer token, and a call made with a token that has
lapsed answers 401 or 410.

A token comes from one of two places. Credentials in .env sign in and renew
forever. A token saved from Settings cannot be renewed - the password is never
stored - so when it lapses the only honest answer is to ask for a new sign-in.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.sources.base import NotConfigured

API = "https://labs.j-novel.club/app/v2"
DEFAULT_TTL_SECONDS = 1_209_600  # 14 days, what J-Novel Club's own web app asks for
RENEW_AHEAD = timedelta(hours=1)

log = logging.getLogger(__name__)


class JncAuthError(RuntimeError):
    """Sign-in refused, with a reason a person can act on."""


@dataclass(frozen=True)
class JncSession:
    token: str
    expires_at: datetime


async def login(client, login_name: str, password: str, *, ttl: int = DEFAULT_TTL_SECONDS,
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> JncSession:
    response = await client.post(
        f"{API}/auth/login",
        params={"format": "json"},
        json={"login": login_name, "password": password, "slim": True, "ttl": ttl},
    )
    if response.status_code == 401:
        raise JncAuthError("wrong email or password")
    if response.status_code == 429:
        raise JncAuthError("too many sign-in attempts, try again later")
    if response.status_code >= 400:
        raise JncAuthError(f"J-Novel Club refused the sign-in ({response.status_code})")
    body = response.json()
    # The ttl in the answer is what the server granted, which need not be what
    # was asked for, so it is the one to trust.
    granted = _seconds(body.get("ttl"), ttl)
    return JncSession(token=body["id"], expires_at=now() + timedelta(seconds=granted))


def _seconds(value, fallback: int) -> int:
    """A session ttl in whichever shape it arrives.

    The session is a protobuf message served as JSON, and protobuf's JSON form
    of a Duration is a string like "1209600s"; a plain number is accepted too.
    Anything else falls back to what was asked for.
    """
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.removesuffix("s")))
        except ValueError:
            pass
    return fallback


async def logout(client, token: str) -> None:
    try:
        await client.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {token}"})
    except Exception as exc:  # noqa: BLE001 - signing out locally must not depend on it
        log.warning("J-Novel Club logout failed: %s", exc)


StoredLoader = Callable[[], Awaitable[JncSession | None]]


class TokenKeeper:
    """One valid token, renewed once however many callers ask at the same time.

    Either credentials (from .env) or a loader of the session saved from
    Settings. The loader is asked each time a token is needed rather than once
    at construction: the workers build their registry at boot, and a sign-in
    made afterwards in the web interface would otherwise never reach them.
    """

    def __init__(
        self,
        client,
        *,
        login_name: str = "",
        password: str = "",
        load_stored: StoredLoader | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._login = login_name
        self._password = password
        self._load_stored = load_stored
        self._now = now
        self._session: JncSession | None = None
        self._rejected: str | None = None
        self._lock = asyncio.Lock()

    @property
    def via(self) -> str:
        if self._login and self._password:
            return "env"
        return "settings" if self._load_stored is not None else "none"

    async def token(self) -> str:
        async with self._lock:
            if self.via == "env":
                if self._session is None or self._session.expires_at - RENEW_AHEAD <= self._now():
                    self._session = await login(
                        self._client, self._login, self._password, now=self._now
                    )
                return self._session.token
            if self.via == "settings":
                stored = await self._load_stored()
                if stored is None:
                    raise NotConfigured("J-Novel Club is not signed in")
                if stored.expires_at <= self._now() or stored.token == self._rejected:
                    raise NotConfigured("J-Novel Club sign-in expired; sign in again in Settings")
                return stored.token
            raise NotConfigured("J-Novel Club is not signed in")

    async def invalidate(self, token: str) -> None:
        """The server refused this token. Credentials sign in again on the next
        call; a stored token is remembered as dead until a new one is saved."""
        async with self._lock:
            if self.via == "env":
                if self._session is not None and self._session.token == token:
                    self._session = None
            else:
                self._rejected = token
```

- [ ] **Step 4: Run it to verify it passes**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovel_auth.py -q`, then ruff.
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources/jnovel_auth.py backend/tests/test_jnovel_auth.py
git commit -m "feat(sources): sign in to J-Novel Club and keep its token valid"
```

---

### Task 2: The J-Novel Club source

**Files:**
- Modify: `backend/app/sources/base.py` (`ChapterRef`)
- Create: `backend/app/sources/jnovelclub.py`
- Create fixtures: `backend/tests/fixtures/sources/jnovelclub_search.json`, `jnovelclub_aggregate.json`, `jnovelclub_part.xhtml`
- Test: `backend/tests/test_source_jnovelclub.py`

**Interfaces:**
- Consumes: `TokenKeeper`, `JncSession` (Task 1); `ProseSource`, `ChapterText`, `ChapterRef`, `ChapterUnavailable`, `NotConfigured`, `PageRef`, `Candidate` (`app.sources.base`); `clean_chapter_html` (`app.sources.prose`); `SiteClient`, `CatalogueRow`, `get_client` (`app.sources.net`).
- Produces:
  - `ChapterRef.available_until: datetime | None = None`.
  - `expires_at(publishing: datetime) -> datetime`.
  - `JNovelClubSource(keeper=None, client=None, now=None)`, with `site = "jnovelclub"` and the pure parsers:
    - `parse_search(payload: dict, titles) -> list[Candidate]`
    - `parse_chapters(payload: dict) -> list[ChapterRef]`
    - `parse_chapter(xhtml: str, chapter_url: str) -> ChapterText`
  - Module constants `SITE`, `API_BASE = "https://labs.j-novel.club"`, `WEB_BASE = "https://j-novel.club"`.
  - Chapter URLs `https://j-novel.club/read/{part slug}`; series URLs `https://j-novel.club/series/{slug}`.

- [ ] **Step 1: Copy the fixtures**

```bash
F=/private/tmp/claude-501/-Users-jackson-mafra-Downloads-Projects-soshuhen/aa9ec06c-f56d-43b2-86eb-e4332ea25803/scratchpad/verify-jnc/tests/fixtures/sources
cp $F/jnovelclub_search.json $F/jnovelclub_aggregate.json $F/jnovelclub_part.xhtml backend/tests/fixtures/sources/
```

If they are missing, re-record them anonymously:

```bash
D=backend/tests/fixtures/sources
curl -s "https://labs.j-novel.club/app/v2/series?format=json&query=apothecary" -o $D/jnovelclub_search.json
curl -s "https://labs.j-novel.club/app/v2/series/the-apothecary-diaries/aggregate?format=json" -o $D/jnovelclub_aggregate.json
```

For `jnovelclub_part.xhtml`, use any preview part's `https://labs.j-novel.club/embed/v2/{partId}/data.xhtml`, then update the paragraph and image counts in the test to what that file holds.

- [ ] **Step 2: Add the field.** In `backend/app/sources/base.py`, add `from datetime import datetime` to the imports, and extend `ChapterRef`:

```python
@dataclass(frozen=True)
class ChapterRef:
    number: Decimal
    url: str
    title: str | None = None
    volume: str | None = None
    language: str = "en"
    # When a source stops serving this chapter to the signed-in account. None,
    # for every source but one, means it never expires.
    available_until: datetime | None = None
```

- [ ] **Step 3: Write the failing test.** `backend/tests/test_source_jnovelclub.py`:

```python
"""J-Novel Club, driven by responses recorded from the live API."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.sources.base import ChapterUnavailable, NotConfigured
from app.sources.jnovel_auth import JncSession, TokenKeeper
from app.sources.jnovelclub import JNovelClubSource, expires_at
from app.sources.net import CatalogueRow, SiteClient

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
PART_URL = "https://j-novel.club/read/the-apothecary-diaries-volume-16-part-1"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _source() -> JNovelClubSource:
    # client is never reached: these tests call the pure parsers.
    return JNovelClubSource(client=object(), now=lambda: NOW)


def test_search_offers_novels_only_best_first():
    found = _source().parse_search(json.loads(_read("jnovelclub_search.json")),
                                   ["The Apothecary Diaries"])
    assert found[0].title == "The Apothecary Diaries"
    assert found[0].source_url == "https://j-novel.club/series/the-apothecary-diaries"
    assert len(found) == 4
    assert {c.source_site for c in found} == {"jnovelclub"}
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_search_skips_manga():
    payload = {"series": [{"type": "MANGA", "slug": "x", "title": "The Apothecary Diaries"}]}
    assert _source().parse_search(payload, ["The Apothecary Diaries"]) == []


def test_parts_are_chapters_numbered_across_the_series():
    chapters = _source().parse_chapters(json.loads(_read("jnovelclub_aggregate.json")))
    assert len(chapters) == 216
    volume_16 = [c for c in chapters if c.volume == "16"]
    assert [c.number for c in volume_16] == [Decimal(n) for n in range(204, 217)]
    assert volume_16[0].url == PART_URL
    assert volume_16[0].title == "The Apothecary Diaries: Volume 16 Part 1"


def test_a_part_expires_from_its_volumes_publishing_date():
    chapters = _source().parse_chapters(json.loads(_read("jnovelclub_aggregate.json")))
    by_number = {c.number: c for c in chapters}
    # Volume 16 published 2026-05-29, on or after the 9th: the 15th of June.
    assert by_number[Decimal(205)].available_until == datetime(2026, 6, 15, 10, tzinfo=UTC)
    # A preview part never expires.
    assert by_number[Decimal(204)].available_until is None


def test_parts_not_launched_yet_are_not_listed():
    payload = {"volumes": [{
        "volume": {"number": 1, "publishing": "2027-01-01T00:00:00Z", "owned": False},
        "parts": [
            {"number": 1, "slug": "s-1", "title": "P1", "preview": True,
             "launch": "2026-10-01T00:00:00Z"},
            {"number": 2, "slug": "s-2", "title": "P2", "preview": False,
             "launch": "2026-10-20T00:00:00Z"},
        ],
    }]}
    assert [c.number for c in _source().parse_chapters(payload)] == [Decimal(1)]


def test_parts_of_an_owned_volume_never_expire():
    payload = {"volumes": [{
        "volume": {"number": 1, "publishing": "2026-05-29T05:00:00Z", "owned": True},
        "parts": [{"number": 1, "slug": "s-1", "title": "P1", "preview": False,
                   "launch": "2026-01-01T00:00:00Z"}],
    }]}
    assert _source().parse_chapters(payload)[0].available_until is None


@pytest.mark.parametrize(
    ("publishing", "expected"),
    [
        (datetime(2025, 9, 12, 5, tzinfo=UTC), datetime(2025, 10, 15, 10, tzinfo=UTC)),
        (datetime(2021, 2, 8, 5, tzinfo=UTC), datetime(2021, 2, 15, 10, tzinfo=UTC)),
        # 15 Feb 2026 is a Sunday: Monday the 16th.
        (datetime(2026, 1, 20, tzinfo=UTC), datetime(2026, 2, 16, 10, tzinfo=UTC)),
        # 15 Nov 2025 is a Saturday: Monday the 17th.
        (datetime(2025, 11, 3, tzinfo=UTC), datetime(2025, 11, 17, 10, tzinfo=UTC)),
        # December rolls into January of the next year.
        (datetime(2026, 12, 20, tzinfo=UTC), datetime(2027, 1, 15, 10, tzinfo=UTC)),
    ],
)
def test_expiry_follows_the_web_apps_rule(publishing, expected):
    assert expires_at(publishing) == expected


def test_a_part_body_keeps_its_text_and_illustrations():
    text = _source().parse_chapter(_read("jnovelclub_part.xhtml"), PART_URL)
    assert text.body.startswith("{{img:0}}<h1>Prologue</h1><p>In a world far, far away")
    assert text.body.count("<p>") == 305
    assert len(text.images) == 3
    assert text.images[0].headers == {"Referer": "https://j-novel.club/"}
    # The note asking readers not to build EPUBs is an HTML comment; it never
    # reaches the chapter.
    assert "build EPUBs" not in text.body


def _network(handler, keeper_factory):
    client = SiteClient(
        # A generous limit: these tests exercise status handling, not pacing.
        CatalogueRow(key="jnc-test", base_url="https://labs.j-novel.club",
                     rate_limit={"permits": 100, "period_seconds": 1}),
        transport=httpx.MockTransport(handler),
    )
    return JNovelClubSource(keeper=keeper_factory(client), client=client, now=lambda: NOW)


def _stored(token="saved"):
    async def load():
        return JncSession(token, datetime(2026, 10, 20, tzinfo=UTC))

    return lambda client: TokenKeeper(client, load_stored=load, now=lambda: NOW)


def _part_lookup(request):
    return httpx.Response(200, json={"id": "PRT-1", "slug": "x"})


async def test_fetch_sends_the_token_and_reads_the_part():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        return httpx.Response(200, text=_read("jnovelclub_part.xhtml"),
                              headers={"content-type": "application/xhtml+xml"})

    text = await _network(handler, _stored()).fetch_chapter(PART_URL)
    assert seen[-1].url.path == "/embed/v2/PRT-1/data.xhtml"
    assert seen[-1].headers["authorization"] == "Bearer saved"
    assert text.body.count("<p>") == 305


@pytest.mark.parametrize(
    ("status", "reason"),
    [(402, "purchase"), (403, "membership"), (410, "expired"), (451, "region")],
)
async def test_refusals_become_unavailable_with_the_reason(status, reason):
    def handler(request):
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        return httpx.Response(status, text="no")

    with pytest.raises(ChapterUnavailable, match=reason):
        await _network(handler, _stored()).fetch_chapter(PART_URL)


async def test_a_refused_stored_token_asks_for_a_new_sign_in():
    def handler(request):
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        return httpx.Response(401)

    with pytest.raises(NotConfigured, match="sign in again"):
        await _network(handler, _stored()).fetch_chapter(PART_URL)


async def test_env_credentials_sign_in_again_once_after_a_401():
    logins = 0
    embeds = 0

    def handler(request):
        nonlocal logins, embeds
        if request.url.path == "/app/v2/auth/login":
            logins += 1
            return httpx.Response(201, json={"id": f"tok-{logins}", "ttl": 1209600})
        if request.url.path.startswith("/app/v2/parts/"):
            return _part_lookup(request)
        embeds += 1
        if request.headers["authorization"] == "Bearer tok-1":
            return httpx.Response(401)
        return httpx.Response(200, text=_read("jnovelclub_part.xhtml"))

    source = _network(
        handler, lambda c: TokenKeeper(c, login_name="me", password="pw", now=lambda: NOW)
    )
    await source.fetch_chapter(PART_URL)
    assert (logins, embeds) == (2, 2)


async def test_listing_works_without_a_sign_in():
    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, text=_read("jnovelclub_aggregate.json"))

    source = _network(handler, lambda c: TokenKeeper(c, now=lambda: NOW))
    chapters = await source.list_chapters("https://j-novel.club/series/the-apothecary-diaries")
    assert len(chapters) == 216
```

- [ ] **Step 4: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_jnovelclub.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.sources.jnovelclub'`.

- [ ] **Step 5: Implement.** `backend/app/sources/jnovelclub.py`. This code was run against the test and fixtures above during planning and passed:

```python
"""J-Novel Club (j-novel.club): pre-publication parts of licensed light novels.

A publisher, not an aggregator. Its catalogue answers without signing in; a
part's text needs the Premium member's token (sources/jnovel_auth.py). Every
part's XHTML carries a note asking that it not be turned into EPUBs - the user
chose to, for personal reading, knowing that (see the design spec).

Part numbers already run across the whole series (The Apothecary Diaries
volume 16 is parts 204-216), so they are the chapter numbers as they come.
"""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    ChapterUnavailable,
    NotConfigured,
    PageRef,
    ProseSource,
)
from app.sources.jnovel_auth import TokenKeeper
from app.sources.net import CatalogueRow, get_client
from app.sources.prose import clean_chapter_html
from app.text_utils import best_similarity

SITE = "jnovelclub"
API_BASE = "https://labs.j-novel.club"
WEB_BASE = "https://j-novel.club"
JSON = {"format": "json"}

_SERIES_SLUG = re.compile(r"/series/([^/?#]+)")
_PART_SLUG = re.compile(r"/read/([^/?#]+)")

# J-Novel Club's own words for each refusal, so a skipped chapter says why.
REFUSALS = {
    402: "needs a purchase on J-Novel Club",
    403: "needs a J-Novel Club membership, or the sign-in no longer grants it",
    404: "is gone from J-Novel Club",
    410: "has expired on J-Novel Club",
    451: "is not available in your region",
}


def expires_at(publishing: datetime) -> datetime:
    """When a Premium member stops being able to read a volume's parts.

    The API's own `expiration` is null or wrong (null for every part of a
    volume published 2026-10-09). J-Novel Club's web app and jncep compute it
    from the volume's publishing date: the 15th, 10:00, of that month - or the
    next month once the volume publishes on the 9th or later - moved to Monday
    when that falls on a weekend. The web app builds the time in the browser's
    own timezone; jncep uses UTC, and so does this, since a warning given a
    week ahead does not depend on the hour.
    """
    year, month = publishing.year, publishing.month
    if publishing.day >= 9:
        month += 1
        if month == 13:
            year, month = year + 1, 1
    day = datetime(year, month, 15, 10, tzinfo=UTC)
    if day.weekday() == 5:
        day += timedelta(days=2)
    elif day.weekday() == 6:
        day += timedelta(days=1)
    return day


def _instant(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class JNovelClubSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("j-novel.club", "labs.j-novel.club")

    def __init__(self, keeper: TokenKeeper | None = None, client=None, now=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=API_BASE))
        self.keeper = keeper or TokenKeeper(self.client)
        self._now = now or (lambda: datetime.now(UTC))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            f"{API_BASE}/app/v2/series", params={**JSON, "query": query}
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        match = _SERIES_SLUG.search(urlsplit(url).path)
        if match is None:
            raise ChapterUnavailable(f"{url} is not a J-Novel Club series address")
        # Signed in, `owned` is filled in, and owned volumes' parts never
        # expire; anonymous still lists everything, so a lapsed sign-in does
        # not stop discovery.
        headers = await self._auth_headers(required=False)
        response = await self.client.get(
            f"{API_BASE}/app/v2/series/{match.group(1)}/aggregate", params=JSON, headers=headers
        )
        response.raise_for_status()
        return self.parse_chapters(response.json())

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        match = _PART_SLUG.search(urlsplit(chapter_url).path)
        if match is None:
            raise ChapterUnavailable(f"{chapter_url} is not a J-Novel Club part address")
        part = await self.client.get(f"{API_BASE}/app/v2/parts/{match.group(1)}", params=JSON)
        if part.status_code == 404:
            raise ChapterUnavailable(f"{chapter_url} {REFUSALS[404]}")
        part.raise_for_status()
        part_id = part.json()["id"]

        for attempt in (1, 2):
            token = await self.keeper.token()
            response = await self.client.get(
                f"{API_BASE}/embed/v2/{part_id}/data.xhtml",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code == 401 and attempt == 1:
                # A lapsed token: renew once (from .env) or learn that the
                # saved one is dead, which the next token() call then says.
                await self.keeper.invalidate(token)
                continue
            if response.status_code == 401:
                raise NotConfigured("J-Novel Club refused the sign-in; sign in again")
            if response.status_code in REFUSALS:
                raise ChapterUnavailable(f"{chapter_url} {REFUSALS[response.status_code]}")
            response.raise_for_status()
            return self.parse_chapter(response.text, chapter_url)
        raise AssertionError("unreachable")

    async def _auth_headers(self, *, required: bool) -> dict[str, str]:
        try:
            return {"Authorization": f"Bearer {await self.keeper.token()}"}
        except NotConfigured:
            if required:
                raise
            return {}

    def parse_search(self, payload: dict, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload.get("series") or []:
            # The same catalogue carries J-Novel Club's manga, often under the
            # very same title as the novel it adapts.
            if item.get("type") != "NOVEL" or not item.get("slug"):
                continue
            names = [n for n in (item.get("title"), item.get("shortTitle"),
                                 item.get("originalTitle")) if n]
            if not names:
                continue
            cover = (item.get("cover") or {}).get("thumbnailUrl") or None
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{WEB_BASE}/series/{item['slug']}",
                    title=names[0],
                    cover_url=cover,
                    alt_titles=names[1:],
                    score=round(max((best_similarity(names, t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, payload: dict) -> list[ChapterRef]:
        now = self._now()
        chapters: list[ChapterRef] = []
        for entry in payload.get("volumes") or []:
            volume = entry.get("volume") or {}
            publishing = _instant(volume.get("publishing"))
            for part in entry.get("parts") or []:
                launch = _instant(part.get("launch"))
                # A part announced but not out yet answers 403 to everyone;
                # listing it would queue a download that cannot succeed.
                if launch is not None and launch > now:
                    continue
                expiry = None
                if not part.get("preview") and not volume.get("owned") and publishing:
                    expiry = expires_at(publishing)
                chapters.append(
                    ChapterRef(
                        number=Decimal(part["number"]),
                        url=f"{WEB_BASE}/read/{part['slug']}",
                        title=part.get("title") or None,
                        volume=str(volume["number"]) if volume.get("number") is not None else None,
                        available_until=expiry,
                    )
                )
        return sorted(chapters, key=lambda c: c.number)

    def parse_chapter(self, xhtml: str, chapter_url: str) -> ChapterText:
        body = HTMLParser(xhtml).body
        if body is None:
            raise ChapterUnavailable(f"{chapter_url} returned no chapter body")
        text, images = clean_chapter_html(body.html, chapter_url)
        return ChapterText(
            title=None,
            body=text,
            images=[PageRef(url=url, headers={"Referer": f"{WEB_BASE}/"}) for url in images],
        )
```

- [ ] **Step 6: Run it to verify it passes**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_jnovelclub.py tests/test_sources_base.py tests/test_prose_contract.py -q`, then ruff.
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/sources/base.py backend/app/sources/jnovelclub.py backend/tests/test_source_jnovelclub.py backend/tests/fixtures/sources/jnovelclub_*
git commit -m "feat(sources): add J-Novel Club parts as a prose source"
```

---

### Task 3: Registry, configuration and catalogue row

**Files:**
- Modify: `backend/app/config.py` (after the MangaDex fields), `backend/app/settings_store.py` (key constants), `backend/app/sources/registry.py`, `.env.example`
- Create: `backend/alembic/versions/0021_seed_jnovelclub.py`
- Test: `backend/tests/test_jnovelclub_registry.py`

**Interfaces:**
- Consumes: Task 1 and Task 2.
- Produces:
  - `Settings.jnc_login: str`, `Settings.jnc_password: str`.
  - `settings_store.JNC_TOKEN = "jnc_token"`, `settings_store.JNC_TOKEN_EXPIRES_AT = "jnc_token_expires_at"`.
  - `registry.build_jnovelclub() -> JNovelClubSource`.
  - `async registry.load_stored_jnc_session() -> JncSession | None`.
  - `"jnovelclub"` in `CONFIGURED_NATIVES` and in the dict `_configured_natives` returns.
  - A `site_catalogue` row `jnovelclub` (native, `en`, `https://labs.j-novel.club`, rate limit `{"permits": 1, "period_seconds": 1}`) with `source_pref` enabled.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_jnovelclub_registry.py`:

```python
"""J-Novel Club is built by the registry, and finds its token wherever it lives."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import settings_store
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources import registry
from app.sources.base import NotConfigured, get_prose_source


@pytest.fixture(autouse=True)
async def clean(monkeypatch):
    monkeypatch.delenv("JNC_LOGIN", raising=False)
    monkeypatch.delenv("JNC_PASSWORD", raising=False)
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("delete from setting where key in ('jnc_token', 'jnc_token_expires_at')")
        )
        await session.commit()
    yield
    get_settings.cache_clear()


async def test_the_catalogue_row_is_seeded_and_enabled():
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text(
                    """
                    select c.template, c.base_url, c.rate_limit, p.enabled
                      from site_catalogue c join source_pref p on p.key = c.key
                     where c.key = 'jnovelclub'
                    """
                )
            )
        ).one()
    assert (row.template, row.base_url, row.enabled) == (
        "native", "https://labs.j-novel.club", True,
    )
    assert row.rate_limit == {"permits": 1, "period_seconds": 1}


async def test_env_credentials_make_an_env_keeper(monkeypatch):
    monkeypatch.setenv("JNC_LOGIN", "me@example.test")
    monkeypatch.setenv("JNC_PASSWORD", "pw")
    get_settings.cache_clear()
    assert registry.build_jnovelclub().keeper.via == "env"


async def test_without_env_the_keeper_reads_settings():
    assert registry.build_jnovelclub().keeper.via == "settings"
    with pytest.raises(NotConfigured, match="not signed in"):
        await registry.build_jnovelclub().keeper.token()


async def test_a_token_saved_after_the_registry_loaded_is_used():
    async with get_sessionmaker()() as session:
        await registry.reload(session)
    source = get_prose_source("jnovelclub")

    async with get_sessionmaker()() as session:
        await settings_store.set_value(session, settings_store.JNC_TOKEN, "late-token")
        await settings_store.set_value(
            session,
            settings_store.JNC_TOKEN_EXPIRES_AT,
            (datetime.now(UTC) + timedelta(days=5)).isoformat(),
        )
        await session.commit()

    assert await source.keeper.token() == "late-token"
```

The conftest's autouse `source_registry` fixture reloads the registry before each test, from rows that include the migrated `jnovelclub` row.

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovelclub_registry.py -q`
Expected: FAIL. No catalogue row, and `registry.build_jnovelclub` does not exist.

- [ ] **Step 3: Configuration.**

In `backend/app/config.py`, after `mangadex_password`:

```python
    # J-Novel Club sign-in. When both are set they sign in and renew by
    # themselves, and the Settings sign-in is disabled; when not, a token saved
    # from Settings is used instead. The password lives only here, never in
    # the database.
    jnc_login: str = ""
    jnc_password: str = ""
```

In `backend/app/settings_store.py`, next to `MANGAFIRE_WAF_PASS`:

```python
# The J-Novel Club token saved by the Settings sign-in, and when it lapses.
# Deliberately absent from all_settings(): the token is a credential, and
# GET /api/settings sends everything it lists to the browser.
JNC_TOKEN = "jnc_token"
JNC_TOKEN_EXPIRES_AT = "jnc_token_expires_at"
```

Do **not** add them to `all_settings()` or to `routes_settings.EDITABLE`. Also add to `.env.example`, next to the MangaDex lines:

```
# J-Novel Club Premium sign-in (optional). Leave empty to sign in from Settings instead.
JNC_LOGIN=
JNC_PASSWORD=
```

- [ ] **Step 4: Registry.** In `backend/app/sources/registry.py`, add the imports:

```python
from datetime import datetime

from app.config import get_settings
from app.db import get_sessionmaker
from app.sources.jnovel_auth import JncSession, TokenKeeper
from app.sources.jnovelclub import API_BASE as JNC_API_BASE
from app.sources.jnovelclub import SITE as JNC_SITE
from app.sources.jnovelclub import JNovelClubSource
```

Change `CONFIGURED_NATIVES = frozenset({"mangafire"})` to `frozenset({"mangafire", "jnovelclub"})`. Add `"jnovelclub": build_jnovelclub()` to the dict `_configured_natives` returns, and add the two functions below `_configured_natives`:

```python
def build_jnovelclub() -> JNovelClubSource:
    """J-Novel Club, signed in from .env when it says how, from Settings otherwise.

    The Settings token is looked up each time one is needed rather than read
    here: the workers build this registry once at boot, and a sign-in made in
    the web interface afterwards would otherwise never reach the download lane.
    """
    settings = get_settings()
    client = get_client(CatalogueRow(key=JNC_SITE, base_url=JNC_API_BASE))
    if settings.jnc_login and settings.jnc_password:
        keeper = TokenKeeper(client, login_name=settings.jnc_login, password=settings.jnc_password)
    else:
        keeper = TokenKeeper(client, load_stored=load_stored_jnc_session)
    return JNovelClubSource(keeper=keeper, client=client)


async def load_stored_jnc_session() -> JncSession | None:
    async with get_sessionmaker()() as session:
        token = await settings_store.stored(session, settings_store.JNC_TOKEN)
        expires = await settings_store.stored(session, settings_store.JNC_TOKEN_EXPIRES_AT)
    if not token or not expires:
        return None
    return JncSession(token=token, expires_at=datetime.fromisoformat(expires))
```

`get_client` and `CatalogueRow` are already imported in that module through `app.sources.net`. If not, import them from there.

- [ ] **Step 5: Seed migration.** `backend/alembic/versions/0021_seed_jnovelclub.py`, shaped after `0020_seed_prose_sources.py`. Check its column list against the live schema, including `rate_limit`.

```python
"""seed J-Novel Club as a prose source

Revision ID: 0021_seed_jnovelclub
Revises: 0020_seed_prose_sources
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_seed_jnovelclub"
down_revision: str | None = "0020_seed_prose_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enabled on arrival: its search needs no sign-in, so it answers for every
# light novel straight away, and downloading still waits for one. One request
# per second is the pace agreed in the design for a publisher's own API.
CATALOGUE = sa.text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, rate_limit, version, hand_ported)
    values ('jnovelclub', 'J-Novel Club', 'native', 'https://labs.j-novel.club', 'en', false,
            '{}'::jsonb, '{"permits": 1, "period_seconds": 1}'::jsonb, '1', true)
    on conflict (key) do nothing
    """
)
PREFERENCE = sa.text(
    "insert into source_pref (key, enabled) values ('jnovelclub', true) on conflict (key) do nothing"
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(CATALOGUE)
    bind.execute(PREFERENCE)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("delete from source_pref where key = 'jnovelclub'"))
    bind.execute(sa.text("delete from site_catalogue where key = 'jnovelclub'"))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovelclub_registry.py tests/test_source_registry.py tests/test_migration_chain.py tests/test_routes_sources.py -q`, then ruff.
Expected: PASS. If `test_source_registry.py` fails with a UniqueViolation on `fakemadara`, that's a known pre-existing leak. Clear it with `docker exec manga-pg-jnc psql -U manga -d manga -c "delete from source_pref where key='fakemadara'"` and rerun; do not fix it here.

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/settings_store.py backend/app/sources/registry.py backend/alembic/versions/0021_seed_jnovelclub.py backend/tests/test_jnovelclub_registry.py .env.example
git commit -m "feat(sources): register J-Novel Club with its sign-in from .env or Settings"
```

---

### Task 4: Sign-in, sign-out and session routes

**Files:**
- Modify: `backend/app/api/routes_sources.py`, `backend/app/sources/jnovelclub.py` (add `account_level`)
- Test: `backend/tests/test_jnovelclub_routes.py`

**Interfaces:**
- Consumes: `login`, `logout`, `JncAuthError` (Task 1); `JNovelClubSource` (Task 2); `settings_store.JNC_TOKEN`, `JNC_TOKEN_EXPIRES_AT`, `registry.reload` (Task 3).
- Produces:
  - `POST /api/sources/jnovelclub/sign-in` `{login, password}` → `{"signed_in": true, "expires_at": iso}`; 400 with the reason; 409 when `.env` is configured.
  - `DELETE /api/sources/jnovelclub/sign-in` → `{"signed_in": false}`.
  - `GET /api/sources/jnovelclub/session` → `{"via": "env" | "settings" | "none", "expires_at": iso | null, "level": str | null}`.
  - `JNovelClubSource.account_level() -> str | None` (`GET /app/v2/me?format=json` → `level`; `None` on any failure).

- [ ] **Step 1: Write the failing test.** `backend/tests/test_jnovelclub_routes.py`:

```python
"""The J-Novel Club sign-in keeps the token and nothing else."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api import routes_sources
from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources.jnovel_auth import JncAuthError, JncSession

pytestmark = pytest.mark.asyncio
EXPIRES = datetime(2026, 10, 28, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def clean(monkeypatch):
    monkeypatch.delenv("JNC_LOGIN", raising=False)
    monkeypatch.delenv("JNC_PASSWORD", raising=False)
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("delete from setting where key in ('jnc_token', 'jnc_token_expires_at')")
        )
        await session.commit()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
def accepted(monkeypatch):
    async def fake_login(client, login_name, password, **kwargs):
        logging.getLogger("test").info("login called")
        return JncSession("tok-abc", EXPIRES)

    monkeypatch.setattr(routes_sources.jnovel_auth, "login", fake_login)


async def _stored() -> dict[str, str]:
    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select key, value from setting"))).all()
    return dict(rows)


async def test_signing_in_stores_the_token_and_its_expiry(client, accepted):
    response = await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    assert response.status_code == 200
    assert response.json() == {"signed_in": True, "expires_at": EXPIRES.isoformat()}
    stored = await _stored()
    assert stored["jnc_token"] == "tok-abc"
    assert datetime.fromisoformat(stored["jnc_token_expires_at"]) == EXPIRES


async def test_the_password_is_neither_stored_nor_logged(client, accepted, caplog):
    caplog.set_level(logging.DEBUG)
    await client.post(
        "/api/sources/jnovelclub/sign-in",
        json={"login": "me@example.test", "password": "s3cret-pass"},
    )
    assert "s3cret-pass" not in (await _stored()).values()
    assert "s3cret-pass" not in caplog.text


async def test_the_token_never_reaches_get_settings(client, accepted):
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    body = (await client.get("/api/settings")).text
    assert "tok-abc" not in body
    assert "jnc_token" not in body


async def test_a_refused_sign_in_says_why(client, monkeypatch):
    async def refuse(*args, **kwargs):
        raise JncAuthError("wrong email or password")

    monkeypatch.setattr(routes_sources.jnovel_auth, "login", refuse)
    response = await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "x", "password": "y"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "wrong email or password"


async def test_signing_in_is_refused_when_env_signs_in(client, accepted, monkeypatch):
    monkeypatch.setenv("JNC_LOGIN", "me@example.test")
    monkeypatch.setenv("JNC_PASSWORD", "pw")
    get_settings.cache_clear()
    response = await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "x", "password": "y"}
    )
    assert response.status_code == 409


async def test_signing_out_clears_the_token(client, accepted, monkeypatch):
    async def fake_logout(client, token):
        return None

    monkeypatch.setattr(routes_sources.jnovel_auth, "logout", fake_logout)
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    response = await client.delete("/api/sources/jnovelclub/sign-in")
    assert response.json() == {"signed_in": False}
    assert "jnc_token" not in await _stored()


async def test_the_session_says_where_the_sign_in_comes_from(client, accepted, monkeypatch):
    async def level(self):
        return "PREMIUM_MEMBER"

    monkeypatch.setattr(routes_sources.JNovelClubSource, "account_level", level)
    assert (await client.get("/api/sources/jnovelclub/session")).json() == {
        "via": "none", "expires_at": None, "level": None,
    }
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    assert (await client.get("/api/sources/jnovelclub/session")).json() == {
        "via": "settings", "expires_at": EXPIRES.isoformat(), "level": "PREMIUM_MEMBER",
    }
    monkeypatch.setenv("JNC_LOGIN", "me@example.test")
    monkeypatch.setenv("JNC_PASSWORD", "pw")
    get_settings.cache_clear()
    session = (await client.get("/api/sources/jnovelclub/session")).json()
    assert session["via"] == "env"


async def test_an_expired_saved_token_reads_as_signed_out(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into setting (key, value) values ('jnc_token', 'old'),"
                " ('jnc_token_expires_at', :at)"
            ),
            {"at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        )
        await session.commit()
    session_info = (await client.get("/api/sources/jnovelclub/session")).json()
    assert session_info["via"] == "none"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovelclub_routes.py -q`
Expected: FAIL. 404/405 from routes that don't exist yet.

- [ ] **Step 3: `account_level`.** Add to `JNovelClubSource` in `backend/app/sources/jnovelclub.py`:

```python
    async def account_level(self) -> str | None:
        """The membership level of the signed-in account, for the Settings card.

        None for anything that goes wrong: the card is a convenience, and a
        failed lookup must not make the sign-in look broken.
        """
        try:
            headers = await self._auth_headers(required=True)
            response = await self.client.get(f"{API_BASE}/app/v2/me", params=JSON, headers=headers)
            response.raise_for_status()
            return response.json().get("level")
        except Exception:  # noqa: BLE001 - see the docstring
            return None
```

- [ ] **Step 4: Routes.** In `backend/app/api/routes_sources.py`, add the imports:

```python
from datetime import UTC, datetime

from app import settings_store
from app.config import get_settings
from app.sources import jnovel_auth
from app.sources.base import get_prose_source
from app.sources.jnovelclub import API_BASE as JNC_API_BASE
from app.sources.jnovelclub import SITE as JNC_SITE
from app.sources.jnovelclub import JNovelClubSource
from app.sources.net import CatalogueRow, get_client
```

Add the routes **above** the existing `@router.put("/{key}")`. FastAPI matches in declaration order, and the new paths have two segments, so they cannot collide with `/{key}` anyway; keeping them first makes that obvious.

```python
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
    await session.commit()
    await registry.reload(session)
    return {"signed_in": True, "expires_at": signed_in.expires_at.isoformat()}


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
```

If `Session` is not the name `routes_sources.py` uses for its database dependency, use the one it does.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovelclub_routes.py tests/test_routes_sources.py -q`, then ruff.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_sources.py backend/app/sources/jnovelclub.py backend/tests/test_jnovelclub_routes.py
git commit -m "feat(api): sign in to J-Novel Club from Settings, keeping only the token"
```

---

### Task 5: `chapter.available_until`, and the expiry warning

**Files:**
- Create: `backend/alembic/versions/0022_chapter_available_until.py`
- Modify: `backend/app/handlers/chapter_discover.py` (`upsert_chapters`, `handle`)
- Test: `backend/tests/test_chapter_expiry.py`

**Interfaces:**
- Consumes: `ChapterRef.available_until` (Task 2).
- Produces:
  - Column `chapter.available_until timestamptz null`.
  - `async expiring_soon(session, series_id: int) -> tuple[int, datetime | None]` in `chapter_discover`: the count and earliest date of chapters in `known`, `queued` or `failed` whose `available_until` falls within the next 7 days.
  - Module constant `EXPIRY_WARNING_DAYS = 7`.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_chapter_expiry.py`:

```python
"""Parts that expire are recorded, and the ones about to are called out."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.chapter_discover import expiring_soon, upsert_chapters
from app.sources.base import ChapterRef

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        await session.commit()


async def _series(session) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('N', 'n', false, '{}'::jsonb, 'prose') returning id"
            )
        )
    ).scalar_one()
    return int(series_id)


async def test_discovery_stores_and_updates_when_a_chapter_expires():
    first = datetime(2026, 11, 16, 10, tzinfo=UTC)
    moved = datetime(2026, 12, 15, 10, tzinfo=UTC)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(
            session, series_id, [ChapterRef(Decimal(1), "https://x/1", available_until=first)]
        )
        await upsert_chapters(
            session, series_id, [ChapterRef(Decimal(1), "https://x/1", available_until=moved)]
        )
        await upsert_chapters(session, series_id, [ChapterRef(Decimal(2), "https://x/2")])
        rows = dict(
            (
                await session.execute(
                    text("select number, available_until from chapter order by number")
                )
            ).all()
        )
    assert rows[Decimal("1.00")] == moved
    assert rows[Decimal("2.00")] is None


async def test_only_undownloaded_parts_within_a_week_are_called_out():
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(
            session,
            series_id,
            [
                ChapterRef(Decimal(1), "https://x/1", available_until=now + timedelta(days=3)),
                ChapterRef(Decimal(2), "https://x/2", available_until=now + timedelta(days=5)),
                ChapterRef(Decimal(3), "https://x/3", available_until=now + timedelta(days=30)),
                ChapterRef(Decimal(4), "https://x/4", available_until=now - timedelta(days=1)),
                ChapterRef(Decimal(5), "https://x/5", available_until=now + timedelta(days=2)),
            ],
        )
        await session.execute(
            text("update chapter set state = 'downloaded' where number = 5")
        )
        count, earliest = await expiring_soon(session, series_id)
    assert count == 2
    assert abs(earliest - (now + timedelta(days=3))) < timedelta(seconds=1)


async def test_nothing_expiring_is_nothing_to_report():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(session, series_id, [ChapterRef(Decimal(1), "https://x/1")])
        assert await expiring_soon(session, series_id) == (0, None)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_chapter_expiry.py -q`
Expected: FAIL. `ImportError: cannot import name 'expiring_soon'`.

- [ ] **Step 3: Migration.** `backend/alembic/versions/0022_chapter_available_until.py`:

```python
"""chapter.available_until: when a source stops serving a chapter

Revision ID: 0022_chapter_available_until
Revises: 0021_seed_jnovelclub
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_chapter_available_until"
down_revision: str | None = "0021_seed_jnovelclub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Null is "never expires", which is every chapter of every source but
    # J-Novel Club's pre-publication parts, so nothing is backfilled.
    op.add_column("chapter", sa.Column("available_until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("chapter", "available_until")
```

Add the matching attribute to the `Chapter` model in `backend/app/models.py`:

```python
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Discovery.** In `backend/app/handlers/chapter_discover.py`, replace the SQL and parameters in `upsert_chapters`:

```python
                insert into chapter (series_id, number, title, source_url, state,
                                     discovered_at, available_until)
                values (:series_id, :number, :title, :url, 'known', now(),
                        cast(:available_until as timestamptz))
                on conflict (series_id, number) do update
                   set title = coalesce(excluded.title, chapter.title),
                       source_url = excluded.source_url,
                       available_until = excluded.available_until
```

and add `"available_until": chapter.available_until` to the parameter dict. Then add, after `upsert_chapters`:

```python
# A week is long enough to notice and act, and short enough that the warning
# only ever names parts that genuinely need attention.
EXPIRY_WARNING_DAYS = 7

EXPIRING_SQL = """
select count(*) as count, min(available_until) as earliest
  from chapter
 where series_id = :series_id
   and state in ('known', 'queued', 'failed')
   and available_until > now()
   and available_until <= now() + make_interval(days => :days)
"""


async def expiring_soon(session: AsyncSession, series_id: int) -> tuple[int, datetime | None]:
    """How many chapters the source will stop serving within the week, and when
    the first of them goes. Downloading stays the user's decision; this is what
    makes sure they get to make it before the chance is gone."""
    row = (
        await session.execute(
            text(EXPIRING_SQL), {"series_id": series_id, "days": EXPIRY_WARNING_DAYS}
        )
    ).one()
    return int(row.count), row.earliest
```

Add `from datetime import datetime` to the imports. In `handle`, directly after `await upsert_chapters(ctx.session, series_id, chapters)`:

```python
    count, earliest = await expiring_soon(ctx.session, series_id)
    if count:
        await ctx.log(
            f"{count} parts expire on {earliest:%d %b} and are not downloaded", level="warning"
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_chapter_expiry.py tests/test_migration_chain.py tests/test_opt_in_downloads.py -q`, then ruff.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0022_chapter_available_until.py backend/app/models.py backend/app/handlers/chapter_discover.py backend/tests/test_chapter_expiry.py
git commit -m "feat(discover): record when parts expire and warn a week ahead"
```

---

### Task 6: Expiry in the series API

**Files:**
- Modify: `backend/app/api/routes_series.py` (`LIST_SQL`, `LIST_SQL_ONE`, `_row_to_series`, `series_detail`)
- Test: `backend/tests/test_chapter_expiry.py` (append)

**Interfaces:**
- Consumes: `chapter.available_until` (Task 5).
- Produces:
  - Every series object carries `"expiring": {"count": int, "earliest": iso} | null`.
  - Every chapter in `GET /api/series/{id}` carries `"available_until": iso | null`.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_chapter_expiry.py`:

```python
from httpx import ASGITransport, AsyncClient

from app.api.main import app


async def test_the_series_api_reports_what_is_about_to_expire():
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await upsert_chapters(
            session,
            series_id,
            [
                ChapterRef(Decimal(1), "https://x/1", available_until=now + timedelta(days=2)),
                ChapterRef(Decimal(2), "https://x/2"),
            ],
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{series_id}")).json()
        listed = (await http.get("/api/series")).json()

    assert detail["series"]["expiring"]["count"] == 1
    assert detail["chapters"][0]["available_until"] is not None
    assert detail["chapters"][1]["available_until"] is None
    row = next(item for item in listed if item["id"] == series_id)
    assert row["expiring"]["count"] == 1


async def test_two_list_entries_do_not_double_the_expiring_count():
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        for provider in ("mal", "anilist"):
            await session.execute(
                text(
                    """
                    insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                            status, user_progress_chapter, raw, updated_at)
                    values (:p, '1', :s, '[]'::jsonb, 'reading', 0, '{}'::jsonb, now())
                    """
                ),
                {"p": provider, "s": series_id},
            )
        await upsert_chapters(
            session,
            series_id,
            [ChapterRef(Decimal(1), "https://x/1", available_until=now + timedelta(days=2))],
        )
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{series_id}")).json()
    assert detail["series"]["expiring"]["count"] == 1


async def test_a_series_with_nothing_expiring_reports_null():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{series_id}")).json()
    assert detail["series"]["expiring"] is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_chapter_expiry.py -q`
Expected: FAIL. `KeyError: 'expiring'`.

- [ ] **Step 3: Implement.**

In `LIST_SQL`, add two columns to the per-series chapter subquery (`ch`), after `failed`:

```sql
             count(*) filter (where state in ('known', 'queued', 'failed')
                                and available_until > now()
                                and available_until <= now() + interval '7 days')
                 as expiring_count,
             min(available_until) filter (where state in ('known', 'queued', 'failed')
                                            and available_until > now()
                                            and available_until <= now() + interval '7 days')
                 as expiring_earliest
```

Add them to the outer select:

```sql
       coalesce(max(ch.expiring_count), 0) as expiring_count,
       max(ch.expiring_earliest) as expiring_earliest,
```

In `LIST_SQL_ONE`, which aggregates the `c` alias directly, add:

```sql
       count(distinct c.id) filter (where c.state in ('known', 'queued', 'failed')
                                      and c.available_until > now()
                                      and c.available_until <= now() + interval '7 days')
           as expiring_count,
       min(c.available_until) filter (where c.state in ('known', 'queued', 'failed')
                                        and c.available_until > now()
                                        and c.available_until <= now() + interval '7 days')
           as expiring_earliest,
```

`distinct` is required. `LIST_SQL_ONE` joins `chapter` and `list_entry` in the same `from`, so a series held by two lists sees every chapter row twice. The existing counts in that query have exactly this bug, which is tracked separately and not part of this task.

The 7 days repeats `EXPIRY_WARNING_DAYS` from `chapter_discover`. Leave a one-line comment pointing there, rather than interpolating it into SQL that is otherwise a constant.

In `_row_to_series`, after `"kind": row.kind,`:

```python
        "expiring": (
            {"count": row.expiring_count, "earliest": row.expiring_earliest.isoformat()}
            if row.expiring_count
            else None
        ),
```

In `series_detail`, add `available_until` to the chapter select (`select id, number, title, state, file_path, komga_book_id, available_until ...`) and to each chapter dict:

```python
                "available_until": c.available_until.isoformat() if c.available_until else None,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_chapter_expiry.py tests/test_series_list_counts.py tests/test_series_detail_links.py tests/test_series_kind_api.py -q`, then ruff.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_series.py backend/tests/test_chapter_expiry.py
git commit -m "feat(api): report parts about to expire on each series"
```

---

### Task 7: A lapsed sign-in leaves chapters waiting

**Files:**
- Modify: `backend/app/handlers/download_batch.py`, `backend/app/handlers/download_chapter.py`
- Test: `backend/tests/test_prose_download.py` (append)

**Interfaces:**
- Consumes: `NotConfigured` (`app.sources.base`).
- Produces:
  - When a source raises `NotConfigured` mid-batch, every chapter of that batch still in `downloading` goes back to `known`, and a Komga scan is queued if anything was placed. The job fails with `PermanentError(<the source's message>)`.
  - `download_chapter` likewise sets the chapter back to `known` and raises `PermanentError`.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_prose_download.py`. Reuse the module's `Stub`, `_series`, `_chapter`, `_catalogue`, `_context` and `_make_prose` helpers, and its `FakeProse` pattern:

```python
from app.sources.base import NotConfigured


class SignedOutProse(FakeProse):
    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotConfigured("J-Novel Club sign-in expired; sign in again in Settings")


async def test_an_expired_sign_in_leaves_the_chapters_known():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        install_registry({stub.key: RegisteredSource(SignedOutProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [
                await _chapter(session, series_id, str(n), u)
                for n, u in zip((1, 2), urls, strict=True)
            ]
            ctx = await _context(session, ids)
            with pytest.raises(PermanentError, match="sign in again"):
                await download_batch.handle(ctx)
            await session.commit()
            states = (
                await session.execute(text("select state from chapter order by number"))
            ).scalars().all()
        assert states == ["known", "known"]
    finally:
        stub.close()
```

Import `PermanentError` from `app.handlers.base` if the module does not already.

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_download.py -q`
Expected: FAIL. `NotConfigured` escapes and the chapters stay `downloading`.

- [ ] **Step 3: Implement.**

In `download_batch.py`, import `NotConfigured` from `app.sources.base`. Add a clause to the per-chapter `try`, before `except ChapterUnavailable`:

```python
            except NotConfigured as exc:
                # The source needs a sign-in it no longer has. Nothing is wrong
                # with these chapters: put back what this batch had not reached,
                # keep what it already saved, and say what to do. The next
                # download after a sign-in picks them up.
                await ctx.session.execute(
                    text(
                        "update chapter set state = 'known'"
                        " where id = any(cast(:ids as bigint[])) and state = 'downloading'"
                    ),
                    {"ids": [r["id"] for r in wanted.values()]},
                )
                if placed:
                    await ctx.enqueue(
                        JobType.KOMGA_SCAN,
                        {"series_id": first["series_id"]},
                        series_id=first["series_id"],
                        dedupe_key=f"komga_scan:{first['series_id']}",
                    )
                await ctx.session.commit()
                raise PermanentError(str(exc)) from exc
```

In `download_chapter.py`'s prose branch, next to its `except ChapterUnavailable`:

```python
        except NotConfigured as exc:
            await ctx.session.execute(
                text("update chapter set state = 'known' where id = :id"), {"id": chapter_id}
            )
            await ctx.session.commit()
            raise PermanentError(str(exc)) from exc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_download.py tests/test_download_batch_handler.py tests/test_download_chapter_handler.py -q`, then ruff.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/download_batch.py backend/app/handlers/download_chapter.py backend/tests/test_prose_download.py
git commit -m "fix(download): a lapsed sign-in leaves chapters waiting instead of failing them"
```

---

### Task 8: Cap light-novel progress at the list's total

**Files:**
- Modify: `backend/app/handlers/progress_push.py`
- Test: `backend/tests/test_progress_push.py` (append)

**Interfaces:**
- Consumes: `series.kind`, `list_entry.total_chapters`.
- Produces: `pushable_chapter(read_chapter: int, kind: str | None, total: int | None) -> int`. `entries_of` rows also carry `total_chapters`.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_progress_push.py`:

```python
from app.handlers.progress_push import pushable_chapter


def test_prose_progress_is_capped_at_the_lists_total():
    # J-Novel Club numbers parts across a series (part 216 of The Apothecary
    # Diaries); the list counts the novel's chapters its own way.
    assert pushable_chapter(216, "prose", 150) == 150
    assert pushable_chapter(120, "prose", 150) == 120


def test_prose_progress_without_a_known_total_is_pushed_as_read():
    assert pushable_chapter(216, "prose", None) == 216
    assert pushable_chapter(216, "prose", 0) == 216


def test_comic_progress_is_never_capped():
    # A provider's total lags a manga's release; capping would hold readers back.
    assert pushable_chapter(216, "comic", 150) == 216
    assert pushable_chapter(216, None, 150) == 216
```

- [ ] **Step 2: Run it to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_progress_push.py -q`
Expected: FAIL. `ImportError: cannot import name 'pushable_chapter'`.

- [ ] **Step 3: Implement.** In `progress_push.py`, add:

```python
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
```

In `entries_of`, add `e.total_chapters` to the select. In `handle`, select `kind` with `komga_series_id` (`select komga_series_id, kind from series where id = :id`). Then compute the chapter per entry inside the loop:

```python
    for entry in await entries_of(ctx.session, series_id):
        chapter = pushable_chapter(read_chapter, row.kind, entry.total_chapters)
        if chapter < read_chapter:
            await ctx.log(
                f"{entry.provider}: part {read_chapter} is past the list's {chapter} chapters,"
                f" sending {chapter}"
            )
        if forward_only(entry.user_progress_chapter, chapter) is None:
            continue
```

Then use `chapter` instead of `read_chapter` in that entry's `push_progress` call, `update list_entry` and log line. Leave `read_chapter` itself as is for whatever follows the loop (the progress event).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_progress_push.py tests/test_komga_completed.py tests/test_komga_list_progress.py -q`, then ruff.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/progress_push.py backend/tests/test_progress_push.py
git commit -m "fix(progress): cap light-novel progress at the list's chapter total"
```

---

### Task 9: Settings card for J-Novel Club

**Files:**
- Create: `frontend/src/features/settings/JNovelClubCard.tsx`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/features/settings/SettingsPage.tsx`

**Interfaces:**
- Consumes: the Task 4 routes.
- Produces:
  - `interface JncSession { via: 'env' | 'settings' | 'none'; expires_at: string | null; level: string | null }`.
  - `api.jncSession()`, `api.jncSignIn(login, password)`, `api.jncSignOut()`.
  - `<JNovelClubCard />`.

- [ ] **Step 1: API client.** In `frontend/src/lib/api.ts`, next to the other source calls:

```ts
export interface JncSession {
  via: 'env' | 'settings' | 'none'
  expires_at: string | null
  level: string | null
}
```

and in the `api` object:

```ts
  jncSession: () => request<JncSession>('/api/sources/jnovelclub/session'),
  jncSignIn: (login: string, password: string) =>
    request<{ signed_in: boolean; expires_at: string }>('/api/sources/jnovelclub/sign-in', {
      method: 'POST',
      body: JSON.stringify({ login, password }),
    }),
  jncSignOut: () =>
    request<{ signed_in: boolean }>('/api/sources/jnovelclub/sign-in', { method: 'DELETE' }),
```

- [ ] **Step 2: The card.** `frontend/src/features/settings/JNovelClubCard.tsx`. It reuses `SourceCard`, and copies input and button classes from the MangaFire card and the rest of this folder, so nothing new should need a class check. Confirm every class with the dist grep anyway.

```tsx
import { useCallback, useState } from 'react'

import { api, messageOf } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { Button } from '../../ui'
import { SourceCard } from './SourceCard'

const LEVEL_LABEL: Record<string, string> = {
  PREMIUM_MEMBER: 'Premium',
  MEMBER: 'Member',
  USER: 'Free account',
}

function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

// The password typed here goes to one request and nowhere else: the server
// keeps only the token it buys. When that lapses, this card asks again.
export function JNovelClubCard() {
  const load = useCallback(() => api.jncSession(), [])
  const { data: session, error, reload } = useAsyncData(load)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const signIn = async () => {
    setBusy(true)
    setFailure(null)
    try {
      await api.jncSignIn(login, password)
      setPassword('')
      reload()
    } catch (caught) {
      setFailure(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  const signOut = async () => {
    setBusy(true)
    try {
      await api.jncSignOut()
      reload()
    } catch (caught) {
      setFailure(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  const signedIn = session && session.via !== 'none'
  const level = session?.level ? (LEVEL_LABEL[session.level] ?? session.level) : null
  const statusLabel = !session
    ? error ?? 'Checking…'
    : session.via === 'env'
      ? 'Signed in from .env'
      : session.via === 'settings'
        ? [level, session.expires_at && `expires ${formatExpiry(session.expires_at)}`]
            .filter(Boolean)
            .join(' · ')
        : 'Not signed in'

  return (
    <SourceCard
      icon="book"
      title="J-Novel Club"
      subtitle="Premium parts of licensed light novels"
      tone={signedIn ? 'ok' : 'neutral'}
      statusLabel={statusLabel}
    >
      {session?.via === 'settings' && (
        <Button variant="secondary" onClick={signOut} disabled={busy}>
          Sign out
        </Button>
      )}
      {session?.via === 'none' && (
        <form
          className="flex flex-col gap-space-xs"
          onSubmit={(event) => {
            event.preventDefault()
            void signIn()
          }}
        >
          <input
            type="email"
            autoComplete="username"
            placeholder="email"
            value={login}
            onChange={(event) => setLogin(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-tertiary shadow-inner focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
          <input
            type="password"
            autoComplete="current-password"
            placeholder="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-tertiary shadow-inner focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
          <Button type="submit" disabled={busy || !login || !password}>
            Sign in
          </Button>
          <p className="text-body-sm text-on-surface-variant">
            Only the sign-in token is kept, for up to 14 days; the password is never stored. Or set
            <code className="mx-1 font-mono text-primary">JNC_LOGIN</code>
            and
            <code className="mx-1 font-mono text-primary">JNC_PASSWORD</code>
            in .env to stay signed in.
          </p>
        </form>
      )}
      {failure && <p className="font-mono text-label-sm text-error">{failure}</p>}
    </SourceCard>
  )
}
```

Before keeping it, check against `ui/Button.tsx` and `lib/api.ts`:
- Does `Button` accept `variant`, `type` and `disabled`? If not, use the props it has, and the way `DownloadControls.tsx` renders a secondary action.
- Is `messageOf` exported from `lib/api`? If not, copy the local helper `DownloadControls.tsx` defines.
- Is `"book"` an `IconName`?

- [ ] **Step 3: Place it.** In `SettingsPage.tsx`, render `<JNovelClubCard />` directly after the MangaFire `SourceCard`, and import it from `./JNovelClubCard`.

- [ ] **Step 4: Build and check the classes**

Run from `frontend/`: `npm run build`. Expected: `tsc -b` and Vite both succeed. For every class string in `JNovelClubCard.tsx`, confirm a hit in `dist/assets/*.css` (for example `grep -o 'shadow-inner' dist/assets/*.css | head -1`), and list them in the report.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/features/settings/JNovelClubCard.tsx frontend/src/features/settings/SettingsPage.tsx
git commit -m "feat(web): sign in to J-Novel Club from Settings"
```

---

### Task 10: Show what is about to expire

**Files:**
- Modify: `frontend/src/lib/api.ts`, `frontend/src/features/series/SeriesHeader.tsx`, `frontend/src/features/series/ChapterTable.tsx`, `frontend/src/features/library/CoverCard.tsx`

**Interfaces:**
- Consumes: `expiring` and `available_until` (Task 6).
- Produces:
  - `Series.expiring: { count: number; earliest: string } | null`.
  - `SeriesChapter.available_until: string | null`.

- [ ] **Step 1: Types.** In `api.ts`, add to `Series`:

```ts
  /** Parts the source stops serving within a week and that are not downloaded. */
  expiring: { count: number; earliest: string } | null
```

and to `SeriesChapter`:

```ts
  /** When the source stops serving this chapter. Null means it never expires. */
  available_until: string | null
```

- [ ] **Step 2: Header badge.** In `SeriesHeader.tsx`, next to the kind badge:

```tsx
        {series.expiring && (
          <Badge tone="warning">
            {series.expiring.count} {series.expiring.count === 1 ? 'part expires' : 'parts expire'}{' '}
            {new Date(series.expiring.earliest).toLocaleDateString(undefined, {
              day: 'numeric',
              month: 'short',
            })}
          </Badge>
        )}
```

- [ ] **Step 3: Library card.** In `CoverCard.tsx` `pipelineNote`, add as the **first** check, so it outranks every other note:

```tsx
  if (series.expiring) {
    const day = new Date(series.expiring.earliest).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
    })
    return { text: `${series.expiring.count} parts expire ${day}`, icon: 'warning', tone: 'text-warning' }
  }
```

The helper is duplicated rather than shared with `SeriesHeader`, because feature folders never import from each other.

- [ ] **Step 4: Chapter rows.** In `ChapterTable.tsx`, in the title cell, after the title, for chapters with a date:

```tsx
                  {chapter.available_until && (
                    <span className="font-mono text-label-sm text-outline">
                      until{' '}
                      {new Date(chapter.available_until).toLocaleDateString(undefined, {
                        day: 'numeric',
                        month: 'short',
                      })}
                    </span>
                  )}
```

Place it where the row already shows secondary metadata, and match that element's wrapper.

- [ ] **Step 5: Build and check the classes**

Run `npm run build` from `frontend/`, then grep `dist/assets/*.css` for `text-warning`, `text-outline` and every other class you used. `text-warning` is new to this codebase and the most likely to be missing. If it does not generate, use the class the `Badge` warning tone relies on, or `text-on-warning-container`, and say so in the report.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/features/series/SeriesHeader.tsx frontend/src/features/series/ChapterTable.tsx frontend/src/features/library/CoverCard.tsx
git commit -m "feat(web): flag light-novel parts that are about to expire"
```

---

### Task 11: Documentation

**Files:**
- Modify: `docs/features.md`, `docs/configuration.md`, `docs/data-model.md`

- [ ] **Step 1: Write**, keeping each file's voice and checking every claim against the code.
  - **`docs/features.md`**, in the Light novels section, add a J-Novel Club paragraph covering:
    - J-Novel Club pre-publication parts, with a Premium sign-in;
    - signing in from `.env` or from Settings, and that only the token is kept;
    - that the publisher's terms and its stated wish not to have parts made into EPUBs apply, and that this is for personal reading;
    - the 7-day expiry warning;
    - that progress past the list's chapter total is capped.
  - **`docs/configuration.md`:** `JNC_LOGIN`, `JNC_PASSWORD`, what they do, and that leaving them empty enables the Settings sign-in.
  - **`docs/data-model.md`:** `chapter.available_until` (null means never expires), and the two `setting` keys, noting they are never served by `GET /api/settings`.

- [ ] **Step 2: Commit**

```bash
git add docs/features.md docs/configuration.md docs/data-model.md
git commit -m "docs: describe J-Novel Club parts"
```

---

### Task 12: Full checks, then a live run with the user's go-ahead

- [ ] **Step 1: Full suite on a fresh database**

```bash
docker run -d --name manga-pg-jnc-fresh -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5435:5432 postgres:17-alpine
```

From `backend/`: `POSTGRES_HOST=localhost POSTGRES_PORT=5435 .venv/bin/python -m pytest tests -q` and ruff. From `frontend/`: `npm run build`. All must pass.

- [ ] **Step 2: Stop and ask the user before touching the live stack.**
  - Rebuilding applies migrations 0021 and 0022 to their live database. Back it up first with `pg_dump` into `data/backups/`.
  - The live check signs in with their J-Novel Club account; they type the credentials into the Settings card themselves.

- [ ] **Step 3: With their go-ahead:**
  1. `docker compose build api && docker compose up -d --force-recreate api worker worker-download web`.
  2. They sign in from Settings; check the card shows Premium and the expiry date.
  3. Map The Apothecary Diaries to J-Novel Club in Review.
  4. Download one preview part and one Premium part.
  5. Check Komga: series, numbers 204+ and the EPUB reader.
  6. Finish one part in Komga, run progress push, and check MAL or AniList moved and was capped if the total is lower.
  7. Report each step's result.
