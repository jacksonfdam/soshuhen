# J-Novel Club Owned Volumes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every volume the user owns on J-Novel Club, for a series mapped to J-Novel Club, is downloaded as J-Novel Club's own EPUB. It sits in that series' Komga folder right after its parts, numbered and locked through Komga's API, and is downloaded again when J-Novel Club revises it.

**Architecture:**
- A new `volume` table, kept apart from `chapter`.
- A fetch-lane job `jnc_library_sync` (cron, sign-in, button) reads the library, upserts volumes for mapped series, and queues a download-lane job `volume_download` for anything new or revised.
- `volume_download` reads a fresh link, checks the bytes are an EPUB, and places the file unmodified.
- `komga_scan` matches `Vol.` files to volume rows and locks their number and sort position.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Alembic, httpx, pytest; React + TypeScript + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-10-15-jnovelclub-volumes-design.md`. Read it first.

## Global Constraints

- Branch `feat/jnovelclub-volumes`, based on `feat/jnovelclub-parts`. Commit there.
- Commits: English, one focused change per commit, **no assistant attribution of any kind**. The repo's `attribution-check` CI fails on it.
- Tests run against a throwaway Postgres, `manga-pg-jnc` on port 5434: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest <files> -q` from `backend/`. Run the brief's tests plus the existing modules covering changed code; never the full suite (the last task runs it once).
- Ruff every task: `.venv/bin/python -m ruff check app/ tests/` from `backend/`.
- `sources/`, `downloader/` and `komga/` never touch the database. Only `handlers/`, `api/` and `sources/registry.py` do.
- asyncpg cannot infer a null parameter's type: `cast(:x as text)` / `timestamptz` / `numeric` where a value may be null.
- Comments explain why a line exists, never what it does.
- **The bearer token never goes to a download link's host.** The link carries its own authorisation; `fetch_volume` sends no Authorization header.
- **Download links are never stored.** They are read fresh from the library each time.
- **J-Novel Club's EPUB is never modified.** Number and sort position are set through Komga's API.
- **Nothing is deleted, with one exception:** the previous file of the same volume after a revision has been placed under a new name.
- `chapter` is not changed by this plan.
- Frontend: no hex, px or rem literals; every new class must be found by `grep` in `frontend/dist/` after `npm run build`; feature folders never import from each other. Never run `docker compose` except in the last task, and only after the user says go.
- Known pre-existing test leak: if `tests/test_source_registry.py` fails with a UniqueViolation on `fakemadara`, run `docker exec manga-pg-jnc psql -U manga -d manga -c "delete from source_pref where key='fakemadara'"`. (The fix for it is now on this branch, so this should no longer happen.)

## Review Focus

1. **Running the library sync twice with nothing changed.** Expected: no new jobs, no state reset. A downloaded volume stays `downloaded` with its `file_path`. Pinned in Task 4 (`test_a_second_sync_with_nothing_new_queues_nothing`).
2. **The link answers with an HTML page** (an expired signature, often with 200). Expected: nothing placed, the job errors into the retry ladder, and the row is not marked downloaded. Pinned in Task 5 (`test_an_html_answer_places_nothing`).
3. **A revision whose title changed.** Expected: the new file is placed first, then the old one is removed, and only that one. Pinned in Task 5 (`test_a_renamed_revision_replaces_the_old_file`).
4. **Signed out, or a free account.** Expected: the cron finishes as done with a log line, never failed. Pinned in Task 4 (`test_not_signed_in_is_done_not_failed`).
5. **A volume book Komga already numbered and locked.** Expected: no PATCH on every scan. Pinned in Task 6 (`test_a_volume_already_in_place_is_not_patched_again`).

---

## File Structure

**Create:**

| File | Purpose |
|---|---|
| `backend/alembic/versions/0023_volume.py` | the `volume` table |
| `backend/app/handlers/jnc_library_sync.py` | the library-sync job |
| `backend/app/handlers/volume_download.py` | the download job |
| `frontend/src/features/series/VolumesPanel.tsx` | the series-page panel |
| `tests/test_volume_files.py`, `tests/test_jnovelclub_library.py` | pure tests |
| `tests/test_jnc_library_sync.py`, `tests/test_volume_download.py`, `tests/test_komga_volumes.py` | handler and Komga tests |

**Modify:**

| File | Change |
|---|---|
| `backend/app/downloader/paths.py` | volume paths |
| `backend/app/downloader/epub.py` | `is_epub` |
| `backend/app/sources/jnovelclub.py` | library, part ranges, `fetch_volume` |
| `backend/app/models.py` | `Volume` |
| `backend/app/enums.py` | job types and lane |
| `backend/app/settings_store.py`, `backend/app/api/routes_settings.py`, `backend/app/cron.py`, `backend/app/worker/main.py` | the cron |
| `backend/app/api/routes_sources.py` | `POST /library-sync`; sign-in queues a sync |
| `backend/app/komga/client.py`, `backend/app/handlers/komga_scan.py` | volume reconciliation |
| `backend/app/api/routes_series.py` | `volumes` on series detail |
| `frontend/src/lib/api.ts`, `features/series/SeriesDetailPage.tsx`, `features/settings/JNovelClubCard.tsx`, `features/settings/PipelineFields.tsx` | panel, sync button, cron field |
| `docs/features.md`, `docs/data-model.md` | docs |

---

### Task 1: Volume paths and the EPUB check

**Files:**
- Modify: `backend/app/downloader/paths.py` (append), `backend/app/downloader/epub.py` (add `import io`, append)
- Test: `backend/tests/test_volume_files.py`

**Interfaces:**
- Produces:
  - `volume_filename(series_slug, number: Decimal, title: str | None = None) -> str`
  - `volume_path(library_root: Path, series_slug, number, title=None) -> Path`
  - `volume_number_from_filename(filename) -> Decimal | None`
  - `is_epub(data: bytes) -> bool`

- [ ] **Step 1: Write the failing test.** `backend/tests/test_volume_files.py`:

```python
"""Where a volume lives on disk, and how a downloaded one is recognised."""

import io
import zipfile
from decimal import Decimal
from pathlib import Path

from app.downloader.epub import is_epub
from app.downloader.paths import (
    number_from_filename,
    volume_filename,
    volume_number_from_filename,
    volume_path,
)


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def test_a_volume_is_named_apart_from_its_chapters():
    assert volume_filename("apothecary", Decimal(16), "Volume 16") == (
        "apothecary - Vol.0016 - Volume 16.epub"
    )
    assert volume_filename("apothecary", Decimal(3)) == "apothecary - Vol.0003.epub"
    assert volume_path(Path("/m"), "apothecary", Decimal(3)) == Path(
        "/m/apothecary/apothecary - Vol.0003.epub"
    )


def test_volume_numbers_read_back_and_never_as_chapters():
    name = volume_filename("apothecary", Decimal(16), "Volume 16")
    assert volume_number_from_filename(name) == Decimal(16)
    assert number_from_filename(name) is None
    assert volume_number_from_filename("apothecary - Ch.0016.epub") is None


def test_an_epub_is_recognised_by_its_container():
    good = _zip([("mimetype", b"application/epub+zip"), ("OEBPS/content.opf", b"<x/>")])
    assert is_epub(good)


def test_an_html_page_is_not_an_epub():
    assert not is_epub(b"<!DOCTYPE html><html>Link expired</html>")


def test_a_zip_without_the_mimetype_first_is_not_an_epub():
    assert not is_epub(_zip([("OEBPS/content.opf", b"<x/>")]))
    assert not is_epub(_zip([("OEBPS/a", b"x"), ("mimetype", b"application/epub+zip")]))
    assert not is_epub(_zip([("mimetype", b"application/zip")]))
```

- [ ] **Step 2: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_volume_files.py -q`. Expected: FAIL, `ImportError: cannot import name 'is_epub'`.

- [ ] **Step 3: Implement.** Append to `backend/app/downloader/paths.py` (it already imports `re`, `Decimal` and `Path`):

```python
def volume_filename(series_slug: str, number: Decimal, title: str | None = None) -> str:
    """A whole volume, named apart from the chapters beside it.

    `Vol.` rather than `Ch.` so number_from_filename never reads a volume as a
    chapter: reconciliation matches books to chapter rows by that number, and
    volume 16 would otherwise claim chapter 16's row.
    """
    stem = f"{series_slug} - Vol.{format_number(number)}"
    if title:
        safe = safe_component(title)
        if safe:
            stem = f"{stem} - {safe}"
    return f"{stem}.epub"


def volume_path(
    library_root: Path, series_slug: str, number: Decimal, title: str | None = None
) -> Path:
    return series_dir(library_root, series_slug) / volume_filename(series_slug, number, title)


_VOLUME_IN_NAME = re.compile(r"\bVol\.(\d+(?:\.\d+)?)")


def volume_number_from_filename(filename: str) -> Decimal | None:
    """Inverse of volume_filename, for the books Komga reports."""
    match = _VOLUME_IN_NAME.search(filename)
    return Decimal(match.group(1)) if match else None
```

In `backend/app/downloader/epub.py`, add `import io` above `import os`, then append:

```python
def is_epub(data: bytes) -> bool:
    """Whether these bytes are an EPUB, read from the bytes and not the headers.

    A signed link that has lapsed answers with an HTML page, often with a 200;
    saved under a .epub name it would look like a working download until
    someone opened it. The container format is the test: a zip whose first
    entry is `mimetype`, holding exactly `application/epub+zip`.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if not entries or entries[0].filename != "mimetype":
                return False
            return archive.read("mimetype") == b"application/epub+zip"
    except zipfile.BadZipFile:
        return False
```

Both were run against the test above during planning and passed.

- [ ] **Step 4: Run it.** Same command, then ruff. Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/downloader/paths.py backend/app/downloader/epub.py backend/tests/test_volume_files.py
git commit -m "feat(downloader): name volume files and recognise a real EPUB"
```

---

### Task 2: Reading the J-Novel Club library

**Files:**
- Modify: `backend/app/sources/jnovelclub.py`
- Test: `backend/tests/test_jnovelclub_library.py`

**Interfaces:**
- Consumes: `SignInRequired`, `TokenKeeper` (already on the branch), and `_instant`, `JSON`, `API_BASE` (already in the module).
- Produces:
  - `OwnedVolume(series_slug, volume_id, number: Decimal, title, status: "owned" | "preorder", last_updated: datetime | None, epub_link: str | None)`, frozen.
  - `parse_library(payload) -> tuple[list[OwnedVolume], bool]` (the bool says whether this was the last page).
  - `parse_part_ranges(payload) -> dict[Decimal, tuple[Decimal, Decimal]]`.
  - `JNovelClubSource.library() -> list[OwnedVolume]`, which raises `SignInRequired` when not signed in or on 401/410.
  - `JNovelClubSource.part_ranges(series_slug)`.
  - `JNovelClubSource.fetch_volume(link) -> bytes`, with no Authorization header.
  - Constant `LIBRARY_PAGE = 100`.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_jnovelclub_library.py`:

```python
"""The J-Novel Club library, read from a payload built from its message definitions.

No live library page has been seen: the account this was built with owned
nothing. The shape follows J-Novel Club's LibraryBook and Download messages
and the field names the clients that download owned books rely on.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.sources.base import SignInRequired
from app.sources.jnovel_auth import JncSession, TokenKeeper
from app.sources.jnovelclub import (
    JNovelClubSource,
    OwnedVolume,
    parse_library,
    parse_part_ranges,
)
from app.sources.net import CatalogueRow, SiteClient

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def _book(number, *, slug="the-apothecary-diaries", status="OWNED", downloads=None):
    return {
        "id": f"LIB-{number}",
        "volume": {"id": f"VOL-{number}", "number": number, "title": f"Volume {number}"},
        "serie": {"slug": slug, "title": "The Apothecary Diaries"},
        "status": status,
        "lastUpdated": "2026-09-01T12:00:00Z",
        "downloads": downloads
        if downloads is not None
        else [
            {"link": "https://cdn.example/v.pdf", "type": "PDF", "label": "PDF"},
            {"link": f"https://cdn.example/v{number}.epub?sig=x", "type": "EPUB", "label": "EPUB"},
        ],
    }


def test_a_library_page_becomes_owned_volumes():
    volumes, last = parse_library(
        {"books": [_book(16)], "pagination": {"limit": 100, "skip": 0, "lastPage": True}}
    )
    assert last is True
    assert volumes == [
        OwnedVolume(
            series_slug="the-apothecary-diaries",
            volume_id="VOL-16",
            number=Decimal(16),
            title="Volume 16",
            status="owned",
            last_updated=datetime(2026, 9, 1, 12, tzinfo=UTC),
            epub_link="https://cdn.example/v16.epub?sig=x",
        )
    ]


def test_a_preorder_and_a_book_without_an_epub_are_kept_but_flagged():
    volumes, _ = parse_library(
        {"books": [_book(17, status="PREORDER"), _book(18, downloads=[])]}
    )
    assert [(v.number, v.status, v.epub_link) for v in volumes] == [
        (Decimal(17), "preorder", "https://cdn.example/v17.epub?sig=x"),
        (Decimal(18), "owned", None),
    ]


def test_an_empty_library_is_one_last_page():
    assert parse_library({"books": [], "pagination": {"lastPage": True}}) == ([], True)


def test_part_ranges_come_from_the_aggregate():
    ranges = parse_part_ranges(json.loads((FIXTURES / "jnovelclub_aggregate.json").read_text()))
    assert ranges[Decimal(16)] == (Decimal(204), Decimal(216))
    assert ranges[Decimal(1)][0] == Decimal(1)


def _source(handler, keeper_factory):
    client = SiteClient(
        CatalogueRow(key="jnc-lib-test", base_url="https://labs.j-novel.club",
                     rate_limit={"permits": 100, "period_seconds": 1}),
        transport=httpx.MockTransport(handler),
    )
    return JNovelClubSource(keeper=keeper_factory(client), client=client, now=lambda: NOW)


def _stored(client):
    async def load():
        return JncSession("saved", datetime(2026, 10, 20, tzinfo=UTC))

    return TokenKeeper(client, load_stored=load, now=lambda: NOW)


async def test_the_library_is_paged_until_the_last_page():
    seen = []

    def handler(request):
        seen.append(int(request.url.params["skip"]))
        last = request.url.params["skip"] == "1"
        number = 1 if not last else 2
        return httpx.Response(
            200, json={"books": [_book(number)], "pagination": {"lastPage": last}}
        )

    volumes = await _source(handler, _stored).library()
    assert seen == [0, 1]
    assert [v.number for v in volumes] == [Decimal(1), Decimal(2)]


async def test_reading_the_library_needs_a_sign_in():
    def handler(request):
        raise AssertionError("no request without a token")

    with pytest.raises(SignInRequired):
        await _source(handler, lambda c: TokenKeeper(c, now=lambda: NOW)).library()


async def test_a_rejected_token_on_the_library_asks_for_a_sign_in():
    with pytest.raises(SignInRequired):
        await _source(lambda request: httpx.Response(401), _stored).library()


async def test_a_volume_is_fetched_without_the_token():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"epub-bytes")

    data = await _source(handler, _stored).fetch_volume("https://cdn.example/v16.epub?sig=x")
    assert data == b"epub-bytes"
    assert "authorization" not in seen[0].headers
    assert seen[0].url.host == "cdn.example"
```

- [ ] **Step 2: Run it.** Expected: FAIL, `ImportError: cannot import name 'OwnedVolume'`.

- [ ] **Step 3: Implement.** In `backend/app/sources/jnovelclub.py`:

1. Add `from dataclasses import dataclass` to the imports.
2. Directly under `JSON = {"format": "json"}`, add:

```python
# The page size the web app asks the library for.
LIBRARY_PAGE = 100
```

3. Directly above `class JNovelClubSource(ProseSource):`, insert:

```python
@dataclass(frozen=True)
class OwnedVolume:
    """One volume in the signed-in account's J-Novel Club library."""

    series_slug: str
    volume_id: str
    number: Decimal
    title: str | None
    status: str  # "owned" or "preorder"
    last_updated: datetime | None
    epub_link: str | None


def parse_library(payload: dict) -> tuple[list[OwnedVolume], bool]:
    """One page of the library, and whether it was the last.

    Field names come from J-Novel Club's own message definitions (LibraryBook,
    Download) and from the clients that already download owned books; the
    account this was built with owned none, so no live page was seen.
    """
    volumes: list[OwnedVolume] = []
    for book in payload.get("books") or []:
        volume = book.get("volume") or {}
        serie = book.get("serie") or {}
        if not volume.get("id") or volume.get("number") is None or not serie.get("slug"):
            continue
        link = next(
            (d.get("link") for d in book.get("downloads") or [] if d.get("type") == "EPUB"),
            None,
        )
        volumes.append(
            OwnedVolume(
                series_slug=serie["slug"],
                volume_id=volume["id"],
                number=Decimal(str(volume["number"])),
                title=volume.get("title") or None,
                status="preorder" if book.get("status") == "PREORDER" else "owned",
                last_updated=_instant(book.get("lastUpdated")),
                epub_link=link or None,
            )
        )
    last = bool((payload.get("pagination") or {}).get("lastPage", True))
    return volumes, last


def parse_part_ranges(payload: dict) -> dict[Decimal, tuple[Decimal, Decimal]]:
    """Each volume number's first and last part, from the series aggregate."""
    ranges: dict[Decimal, tuple[Decimal, Decimal]] = {}
    for entry in payload.get("volumes") or []:
        volume = entry.get("volume") or {}
        numbers = [Decimal(p["number"]) for p in entry.get("parts") or [] if "number" in p]
        if volume.get("number") is None or not numbers:
            continue
        ranges[Decimal(str(volume["number"]))] = (min(numbers), max(numbers))
    return ranges
```

4. Inside `JNovelClubSource`, directly above `async def _session_alive`, insert:

```python
    async def library(self) -> list[OwnedVolume]:
        """Every volume the signed-in account owns or has pre-ordered."""
        volumes: list[OwnedVolume] = []
        skip = 0
        while True:
            token = await self.keeper.token()
            response = await self.client.get(
                f"{API_BASE}/app/v2/me/library",
                params={**JSON, "include": "serie", "limit": LIBRARY_PAGE, "skip": skip},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code in (401, 410):
                await self.keeper.invalidate(token)
                raise SignInRequired("J-Novel Club refused the sign-in; sign in again")
            response.raise_for_status()
            page, last = parse_library(response.json())
            volumes.extend(page)
            if last or not page:
                return volumes
            skip += len(page)

    async def part_ranges(self, series_slug: str) -> dict[Decimal, tuple[Decimal, Decimal]]:
        response = await self.client.get(
            f"{API_BASE}/app/v2/series/{series_slug}/aggregate", params=JSON
        )
        response.raise_for_status()
        return parse_part_ranges(response.json())

    async def fetch_volume(self, link: str) -> bytes:
        """The volume's EPUB, fetched from the link the library handed out.

        No Authorization header: the link carries its own, and the bearer
        token must never travel to whatever host the link points at.
        """
        response = await self.client.get(link, follow_redirects=True)
        response.raise_for_status()
        return response.content
```

All of this was run against the test above during planning and passed.

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnovelclub_library.py tests/test_source_jnovelclub.py -q`, then ruff. Expected: all pass (8 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources/jnovelclub.py backend/tests/test_jnovelclub_library.py
git commit -m "feat(sources): read the J-Novel Club library and fetch an owned volume"
```

---

### Task 3: The `volume` table and its job types

**Files:**
- Create: `backend/alembic/versions/0023_volume.py`
- Modify: `backend/app/models.py`, `backend/app/enums.py`
- Test: `backend/tests/test_jnc_library_sync.py` (created here, extended in Task 4)

**Interfaces:**
- Produces:
  - The table `volume` (spec §1).
  - The ORM class `Volume`.
  - `JobType.JNC_LIBRARY_SYNC = "jnc_library_sync"` and `JobType.VOLUME_DOWNLOAD = "volume_download"`.
  - `VOLUME_DOWNLOAD` in the download lane.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_jnc_library_sync.py`:

```python
"""The J-Novel Club library becomes volume rows, and new or revised ones download."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, lane_of

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


def test_volume_downloads_run_where_files_are_written():
    assert lane_of(JobType.VOLUME_DOWNLOAD) == Lane.DOWNLOAD
    assert lane_of(JobType.JNC_LIBRARY_SYNC) == Lane.FETCH


async def test_a_volume_is_unique_per_series_and_number():
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('A', 'a', false, '{}'::jsonb, 'prose') returning id"
                )
            )
        ).scalar_one()
        insert = text(
            "insert into volume (series_id, number, source_volume_id, status)"
            " values (:s, 16, :v, 'owned')"
        )
        await session.execute(insert, {"s": series_id, "v": "VOL-16"})
        with pytest.raises(Exception, match="unique|duplicate"):
            await session.execute(insert, {"s": series_id, "v": "VOL-OTHER"})
```

`lane_of` is the helper `enums.py` exports (`Lane.DOWNLOAD if job_type in _DOWNLOAD_LANE else Lane.FETCH`).

- [ ] **Step 2: Run it.** Expected: FAIL, `AttributeError: JNC_LIBRARY_SYNC`, or `relation "volume" does not exist`.

- [ ] **Step 3: Implement.**

In `backend/app/enums.py`, add to `JobType`:

```python
    JNC_LIBRARY_SYNC = "jnc_library_sync"
    VOLUME_DOWNLOAD = "volume_download"
```

and add `JobType.VOLUME_DOWNLOAD` to `_DOWNLOAD_LANE`. Volume downloads write the library, and only `worker-download` may.

`backend/alembic/versions/0023_volume.py`:

```python
"""volume: J-Novel Club volumes the user owns, kept apart from chapters

Revision ID: 0023_volume
Revises: 0022_chapter_available_until
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_volume"
down_revision: str | None = "0022_chapter_available_until"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Its own table, not chapter rows with a unit column: everything that counts
    # chapters or turns a Komga book into a chapter number would otherwise need
    # a filter, and the one forgotten would count volume 16 as chapter 16.
    op.create_table(
        "volume",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "series_id",
            sa.BigInteger(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Numeric(8, 2), nullable=False),
        sa.Column("source_volume_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True)),
        sa.Column("downloaded_updated", sa.DateTime(timezone=True)),
        sa.Column("first_part", sa.Numeric(8, 2)),
        sa.Column("last_part", sa.Numeric(8, 2)),
        sa.Column("state", sa.Text(), nullable=False, server_default="known"),
        sa.Column("file_path", sa.Text()),
        sa.Column("komga_book_id", sa.Text()),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("series_id", "number", name="volume_series_number_key"),
        sa.UniqueConstraint("series_id", "source_volume_id", name="volume_series_source_key"),
        sa.CheckConstraint("status in ('owned', 'preorder')", name="volume_status_check"),
        sa.CheckConstraint(
            "state in ('known', 'queued', 'downloading', 'downloaded', 'failed')",
            name="volume_state_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("volume")
```

In `backend/app/models.py`, after `class Chapter`:

```python
class Volume(Base):
    """A J-Novel Club volume the user owns or has pre-ordered.

    Kept apart from Chapter on purpose; see migration 0023.
    """

    __tablename__ = "volume"
    __table_args__ = (
        UniqueConstraint("series_id", "number", name="volume_series_number_key"),
        UniqueConstraint("series_id", "source_volume_id", name="volume_series_source_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    source_volume_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last_updated of the file on disk: older than last_updated means the
    # volume was revised and downloads again.
    downloaded_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_part: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    last_part: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="known")
    file_path: Mapped[str | None] = mapped_column(Text)
    komga_book_id: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[datetime] = _now()
```

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnc_library_sync.py tests/test_migration_chain.py tests/test_lanes.py -q`, then ruff. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0023_volume.py backend/app/models.py backend/app/enums.py backend/tests/test_jnc_library_sync.py
git commit -m "feat(db): a volume table for J-Novel Club volumes the user owns"
```

---

### Task 4: The library sync job, its cron and its triggers

**Files:**
- Create: `backend/app/handlers/jnc_library_sync.py`
- Modify:
  - `backend/app/settings_store.py`: `CRON_JNC_LIBRARY_SYNC`, the default, `_fallback`, `all_settings`
  - `backend/app/api/routes_settings.py`: `EDITABLE` and the `cron_changed` set
  - `backend/app/cron.py`: `CRON_JOBS`
  - `backend/app/worker/main.py`: the handler import and `ENQUEUERS`
  - `backend/app/api/routes_sources.py`: sign-in queues a sync, and `POST /library-sync`
- Test: `backend/tests/test_jnc_library_sync.py` (append), `backend/tests/test_jnovelclub_routes.py` (append)

**Interfaces:**
- Consumes: `OwnedVolume`, `library()`, `part_ranges()` (Task 2); `volume` (Task 3).
- Produces:
  - `needs_download(*, status, has_link, state, downloaded_updated, last_updated) -> bool`
  - `series_by_slug(session) -> dict[str, int]`
  - The handler for `JobType.JNC_LIBRARY_SYNC`.
  - `settings_store.CRON_JNC_LIBRARY_SYNC = "cron_jnc_library_sync"`, default `"0 */6 * * *"`.
  - `POST /api/sources/jnovelclub/library-sync` → `{"ok": true, "job_id": int | null}`.

- [ ] **Step 1: Write the failing tests.** Append to `backend/tests/test_jnc_library_sync.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from app.handlers.base import JobContext
from app.handlers.jnc_library_sync import handle, needs_download
from app.queue import repo
from app.sources.base import ProseSource, RegisteredSource, SignInRequired, install_registry
from app.sources.jnovelclub import OwnedVolume

OLD = datetime(2026, 9, 1, tzinfo=UTC)
NEW = datetime(2026, 10, 1, tzinfo=UTC)


def test_what_needs_downloading():
    base = {"status": "owned", "has_link": True, "state": "known",
            "downloaded_updated": None, "last_updated": OLD}
    assert needs_download(**base)
    assert not needs_download(**{**base, "status": "preorder"})
    assert not needs_download(**{**base, "has_link": False})
    assert not needs_download(**{**base, "state": "queued"})
    assert not needs_download(**{**base, "state": "downloading"})
    assert not needs_download(**{**base, "state": "downloaded", "downloaded_updated": OLD})
    assert needs_download(**{**base, "state": "downloaded", "downloaded_updated": OLD,
                             "last_updated": NEW})


class FakeJnc(ProseSource):
    site = "jnovelclub"
    domains = ("j-novel.club",)

    def __init__(self, owned=None, signed_in=True):
        self.owned = owned or []
        self.signed_in = signed_in

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotImplementedError

    async def library(self):
        if not self.signed_in:
            raise SignInRequired("J-Novel Club is not signed in")
        return self.owned

    async def part_ranges(self, series_slug):
        return {Decimal(16): (Decimal(204), Decimal(216))}


def _owned(number=16, *, slug="the-apothecary-diaries", status="owned", updated=OLD):
    return OwnedVolume(slug, f"VOL-{number}", Decimal(number), f"Volume {number}", status,
                       updated, "https://cdn.example/v.epub?sig=x")


async def _mapped_series(session, slug="the-apothecary-diaries") -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('The Apothecary Diaries', 'apothecary', false, '{}'::jsonb, 'prose')"
                " returning id"
            )
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active)"
            " values (:s, 'jnovelclub', :u, true)"
        ),
        {"s": series_id, "u": f"https://j-novel.club/series/{slug}"},
    )
    await session.commit()
    return int(series_id)


async def _run(session, source) -> JobContext:
    install_registry({"jnovelclub": RegisteredSource(source, "https://labs.j-novel.club")})
    await repo.enqueue(session, JobType.JNC_LIBRARY_SYNC, {})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.JNC_LIBRARY_SYNC)])
    await session.commit()
    ctx = JobContext(session=session, job=job)
    await handle(ctx)
    await session.commit()
    return ctx


async def _volumes(session):
    return (
        await session.execute(
            text("select number, status, state, first_part, last_part from volume order by number")
        )
    ).all()


async def _queued(session) -> int:
    return (
        await session.execute(text("select count(*) from job where type = 'volume_download'"))
    ).scalar_one()


async def test_an_owned_volume_of_a_mapped_series_is_recorded_and_queued():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        rows = await _volumes(session)
        assert [(r.number, r.status, r.state, r.first_part, r.last_part) for r in rows] == [
            (Decimal("16.00"), "owned", "queued", Decimal("204.00"), Decimal("216.00"))
        ]
        assert await _queued(session) == 1


async def test_a_preorder_is_recorded_but_not_queued():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned(status="preorder")]))
        assert [r.state for r in await _volumes(session)] == ["known"]
        assert await _queued(session) == 0


async def test_an_unmapped_series_is_reported_not_recorded():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        ctx = await _run(session, FakeJnc([_owned(slug="some-other-series")]))
        assert await _volumes(session) == []
        log = (
            await session.execute(
                text("select string_agg(message, ' ') from job_event where job_id = :j"),
                {"j": ctx.job.id},
            )
        ).scalar_one()
        assert "some-other-series" in log


async def test_not_signed_in_is_done_not_failed():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc(signed_in=False))
        assert await _volumes(session) == []


async def test_a_second_sync_with_nothing_new_queues_nothing():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        await session.execute(
            text(
                "update volume set state = 'downloaded', file_path = '/m/a.epub',"
                " downloaded_updated = :d"
            ),
            {"d": OLD},
        )
        await session.execute(text("delete from job where type = 'volume_download'"))
        await session.commit()
        await _run(session, FakeJnc([_owned()]))
        row = (await session.execute(text("select state, file_path from volume"))).one()
        assert (row.state, row.file_path) == ("downloaded", "/m/a.epub")
        assert await _queued(session) == 0


async def test_a_revised_volume_is_queued_again():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        await session.execute(
            text("update volume set state = 'downloaded', downloaded_updated = :d"), {"d": OLD}
        )
        await session.execute(text("delete from job where type = 'volume_download'"))
        await session.commit()
        await _run(session, FakeJnc([_owned(updated=NEW)]))
        assert [r.state for r in await _volumes(session)] == ["queued"]
        assert await _queued(session) == 1
```

`repo.lease`'s signature: check it in `tests/test_download_batch_handler.py` (`repo.lease(session, types=EVERY_TYPE)`) and pass the type list the same way.

Append to `backend/tests/test_jnovelclub_routes.py`:

```python
async def test_signing_in_queues_a_library_sync(client, accepted):
    await client.post(
        "/api/sources/jnovelclub/sign-in", json={"login": "me@example.test", "password": "pw"}
    )
    async with get_sessionmaker()() as session:
        queued = (
            await session.execute(
                text("select count(*) from job where type = 'jnc_library_sync'")
            )
        ).scalar_one()
    assert queued == 1


async def test_the_sync_button_queues_one_sync(client):
    first = (await client.post("/api/sources/jnovelclub/library-sync")).json()
    second = (await client.post("/api/sources/jnovelclub/library-sync")).json()
    assert first["ok"] is True and first["job_id"] is not None
    # Deduped: a second press while one is waiting adds nothing.
    assert second["job_id"] is None
```

That module's `clean` fixture must also clear jobs: add `await session.execute(text("delete from job where type = 'jnc_library_sync'"))` to it.

- [ ] **Step 2: Run them.** Expected: FAIL, `ModuleNotFoundError: app.handlers.jnc_library_sync`, plus 404s on the routes.

- [ ] **Step 3: The handler.** `backend/app/handlers/jnc_library_sync.py`:

```python
"""Read the J-Novel Club library and keep volume rows and downloads in step.

Buying a volume is the decision to have it, so an owned volume of a series
mapped to J-Novel Club downloads without being asked - unlike chapters, which
wait for a range or auto_download. Volumes of series no list holds are only
named in the log: a series is created by a reading list, never by a shop.
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType
from app.handlers.base import JobContext, register
from app.sources.base import SignInRequired, get_prose_source

SITE = "jnovelclub"
_SERIES_SLUG = re.compile(r"/series/([^/?#]+)")

UPSERT = """
insert into volume (series_id, number, source_volume_id, title, status, last_updated,
                    first_part, last_part)
values (:series_id, :number, :volume_id, :title, :status, cast(:last_updated as timestamptz),
        cast(:first_part as numeric), cast(:last_part as numeric))
on conflict (series_id, source_volume_id) do update
   set number = excluded.number,
       title = excluded.title,
       status = excluded.status,
       last_updated = excluded.last_updated,
       first_part = excluded.first_part,
       last_part = excluded.last_part
returning id, state, downloaded_updated, last_updated
"""


def needs_download(
    *,
    status: str,
    has_link: bool,
    state: str,
    downloaded_updated: datetime | None,
    last_updated: datetime | None,
) -> bool:
    """Owned, downloadable, not already on its way, and not on disk at this revision."""
    if status != "owned" or not has_link or state in ("queued", "downloading"):
        return False
    if downloaded_updated is None:
        return True
    return last_updated is not None and downloaded_updated < last_updated


async def series_by_slug(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text(
                "select series_id, source_url from source_mapping"
                " where active and source_site = :site"
            ),
            {"site": SITE},
        )
    ).all()
    found: dict[str, int] = {}
    for row in rows:
        match = _SERIES_SLUG.search(row.source_url or "")
        if match:
            found[match.group(1)] = row.series_id
    return found


@register(JobType.JNC_LIBRARY_SYNC)
async def handle(ctx: JobContext) -> None:
    try:
        source = get_prose_source(SITE)
    except (ValueError, TypeError):
        await ctx.log("J-Novel Club is not enabled; skipping the library")
        return
    try:
        owned = await source.library()
    except SignInRequired:
        # Done, not failed: a free account or a signed-out install would
        # otherwise turn this cron red every six hours for nothing.
        await ctx.log("J-Novel Club is not signed in; skipping the library", pct=100)
        return

    mapped = await series_by_slug(ctx.session)
    by_slug: dict[str, list[Any]] = defaultdict(list)
    for volume in owned:
        by_slug[volume.series_slug].append(volume)

    unmapped: list[str] = []
    queued = revised = preorders = 0
    for slug, volumes in by_slug.items():
        series_id = mapped.get(slug)
        if series_id is None:
            unmapped.append(slug)
            continue
        ranges = await source.part_ranges(slug)
        for volume in volumes:
            first, last = ranges.get(volume.number, (None, None))
            row = (
                await ctx.session.execute(
                    text(UPSERT),
                    {
                        "series_id": series_id,
                        "number": volume.number,
                        "volume_id": volume.volume_id,
                        "title": volume.title,
                        "status": volume.status,
                        "last_updated": volume.last_updated,
                        "first_part": first,
                        "last_part": last,
                    },
                )
            ).one()
            if volume.status == "preorder":
                preorders += 1
            if not needs_download(
                status=volume.status,
                has_link=volume.epub_link is not None,
                state=row.state,
                downloaded_updated=row.downloaded_updated,
                last_updated=row.last_updated,
            ):
                continue
            if row.downloaded_updated is not None:
                revised += 1
            await ctx.session.execute(
                text("update volume set state = 'queued' where id = :id"), {"id": row.id}
            )
            await ctx.enqueue(
                JobType.VOLUME_DOWNLOAD,
                {"volume_id": row.id},
                series_id=series_id,
                dedupe_key=f"volume_download:{row.id}",
            )
            queued += 1

    await ctx.session.commit()
    summary = f"{len(owned)} owned on J-Novel Club, {queued} queued"
    if revised:
        summary += f" ({revised} revised)"
    if preorders:
        summary += f", {preorders} pre-orders waiting"
    if unmapped:
        summary += f"; owned but not mapped: {', '.join(sorted(unmapped))}"
    await ctx.log(summary, pct=100)
```

- [ ] **Step 4: The cron.**
  - **`settings_store.py`:**
    - Add `CRON_JNC_LIBRARY_SYNC = "cron_jnc_library_sync"` next to the other `CRON_*` constants.
    - Add `cron_jnc_library_sync: str = "0 */6 * * *"` to `Defaults`.
    - Add `case k if k == CRON_JNC_LIBRARY_SYNC: return DEFAULTS.cron_jnc_library_sync` to `_fallback`.
    - Add the key to the list in `all_settings()`.
  - **`routes_settings.py`:** add `settings_store.CRON_JNC_LIBRARY_SYNC` to `EDITABLE` and to the `cron_changed` set.
  - **`cron.py`:** add `CronJob("jnc_library_sync", settings_store.CRON_JNC_LIBRARY_SYNC)` to `CRON_JOBS`.
  - **`worker/main.py`:** add `jnc_library_sync` and `volume_download` to the `from app.handlers import (...)` list (`volume_download` lands in Task 5; until then, import only `jnc_library_sync`). Then add an enqueuer:

```python
async def enqueue_jnc_library_sync() -> None:
    async with get_sessionmaker()() as session:
        await repo.enqueue(
            session, JobType.JNC_LIBRARY_SYNC, {}, dedupe_key="jnc_library_sync"
        )
        await session.commit()
    log.info("cron: queued J-Novel Club library sync")
```

  Add `"jnc_library_sync": enqueue_jnc_library_sync` to `ENQUEUERS`. Match the session-opening style of the enqueuers around it.

- [ ] **Step 5: The routes.** In `routes_sources.py`, import `JobType` from `app.enums` and `repo` from `app.queue`. In `jnc_sign_in`, before `await session.commit()`, add:

```python
    # A fresh sign-in is when the library is most likely to hold something
    # new; waiting up to six hours for the cron would look broken.
    await repo.enqueue(session, JobType.JNC_LIBRARY_SYNC, {}, dedupe_key="jnc_library_sync")
```

and add the route:

```python
@router.post("/jnovelclub/library-sync")
async def jnc_library_sync(session: Session) -> dict[str, Any]:
    job_id = await repo.enqueue(
        session, JobType.JNC_LIBRARY_SYNC, {}, dedupe_key="jnc_library_sync"
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}
```

- [ ] **Step 6: Run the tests.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_jnc_library_sync.py tests/test_jnovelclub_routes.py tests/test_api.py tests/test_dashboard_api.py -q`, then ruff. Expected: PASS. `test_dashboard_api` lists the crons; if it pins their exact set, add `jnc_library_sync` to its expectation.

- [ ] **Step 7: Commit**

```bash
git add backend/app/handlers/jnc_library_sync.py backend/app/settings_store.py backend/app/api/routes_settings.py backend/app/cron.py backend/app/worker/main.py backend/app/api/routes_sources.py backend/tests/test_jnc_library_sync.py backend/tests/test_jnovelclub_routes.py
git commit -m "feat(jnovelclub): sync the owned library into volumes and queue their downloads"
```

---

### Task 5: Downloading a volume

**Files:**
- Create: `backend/app/handlers/volume_download.py`
- Modify: `backend/app/worker/main.py` (import `volume_download`)
- Test: `backend/tests/test_volume_download.py`

**Interfaces:**
- Consumes: `library()`, `fetch_volume()` (Task 2); `is_epub`, `volume_path` (Task 1); `place_file` (`app.downloader.cbz`).
- Produces: the handler for `JobType.VOLUME_DOWNLOAD` (payload `{"volume_id": int}`).

- [ ] **Step 1: Write the failing test.** `backend/tests/test_volume_download.py`:

```python
"""An owned volume lands in the library as J-Novel Club's own EPUB."""

import io
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError
from app.handlers.volume_download import handle
from app.queue import repo
from app.sources.base import ProseSource, RegisteredSource, SignInRequired, install_registry
from app.sources.jnovelclub import OwnedVolume

pytestmark = pytest.mark.asyncio
OLD = datetime(2026, 9, 1, tzinfo=UTC)
NEW = datetime(2026, 10, 1, tzinfo=UTC)


def _epub(marker: bytes = b"v1") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr("OEBPS/marker", marker)
    return buffer.getvalue()


class FakeJnc(ProseSource):
    site = "jnovelclub"
    domains = ("j-novel.club",)

    def __init__(self, *, owned=True, body=None, title="Volume 16", updated=OLD, signed_in=True):
        self.owned, self.body, self.title = owned, body, title
        self.updated, self.signed_in = updated, signed_in

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotImplementedError

    async def library(self):
        if not self.signed_in:
            raise SignInRequired("J-Novel Club sign-in expired; sign in again in Settings")
        if not self.owned:
            return []
        return [OwnedVolume("the-apothecary-diaries", "VOL-16", Decimal(16), self.title,
                            "owned", self.updated, "https://cdn.example/v16.epub?sig=x")]

    async def fetch_volume(self, link):
        return self.body if self.body is not None else _epub()


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    yield
    get_settings.cache_clear()


async def _volume(session, *, file_path=None, downloaded_updated=None) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('The Apothecary Diaries', 'apothecary', false, '{}'::jsonb, 'prose')"
                " returning id"
            )
        )
    ).scalar_one()
    volume_id = (
        await session.execute(
            text(
                """
                insert into volume (series_id, number, source_volume_id, title, status,
                                    last_updated, last_part, state, file_path,
                                    downloaded_updated)
                values (:s, 16, 'VOL-16', 'Volume 16', 'owned', :u, 216, 'queued',
                        cast(:f as text), cast(:d as timestamptz))
                returning id
                """
            ),
            {"s": series_id, "u": OLD, "f": file_path, "d": downloaded_updated},
        )
    ).scalar_one()
    await session.commit()
    return int(volume_id)


async def _run(session, source, volume_id):
    install_registry({"jnovelclub": RegisteredSource(source, "https://labs.j-novel.club")})
    await repo.enqueue(session, JobType.VOLUME_DOWNLOAD, {"volume_id": volume_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.VOLUME_DOWNLOAD)])
    await session.commit()
    await handle(JobContext(session=session, job=job))
    await session.commit()


async def _row(session, volume_id):
    return (
        await session.execute(
            text("select state, file_path, downloaded_updated from volume where id = :id"),
            {"id": volume_id},
        )
    ).one()


async def test_an_owned_volume_is_placed_and_scanned():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await _run(session, FakeJnc(), volume_id)
        row = await _row(session, volume_id)
        assert row.state == "downloaded"
        assert row.file_path.endswith("apothecary - Vol.0016 - Volume 16.epub")
        assert Path(row.file_path).read_bytes() == _epub()
        assert row.downloaded_updated == OLD
        scans = (
            await session.execute(text("select count(*) from job where type = 'komga_scan'"))
        ).scalar_one()
        assert scans == 1


async def test_a_revision_replaces_the_file_in_place():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await _run(session, FakeJnc(), volume_id)
        await _run(session, FakeJnc(body=_epub(b"v2"), updated=NEW), volume_id)
        row = await _row(session, volume_id)
        assert Path(row.file_path).read_bytes() == _epub(b"v2")


async def test_a_renamed_revision_replaces_the_old_file():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        await _run(session, FakeJnc(), volume_id)
        old = Path((await _row(session, volume_id)).file_path)
        await _run(session, FakeJnc(title="Volume 16: Revised", updated=NEW), volume_id)
        new = Path((await _row(session, volume_id)).file_path)
        assert new != old
        assert new.exists()
        assert not old.exists()
        # Only that one file: the folder holds exactly the new edition.
        assert sorted(p.name for p in new.parent.iterdir()) == [new.name]


async def test_an_html_answer_places_nothing():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(Exception, match="not an EPUB"):
            await _run(session, FakeJnc(body=b"<html>expired</html>"), volume_id)
        await session.rollback()
        row = await _row(session, volume_id)
        assert row.state != "downloaded"
        assert row.file_path is None


async def test_a_volume_gone_from_the_library_fails_for_good():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(PermanentError, match="no longer in your J-Novel Club library"):
            await _run(session, FakeJnc(owned=False), volume_id)
        await session.rollback()
        assert (await _row(session, volume_id)).state == "known"


async def test_a_lapsed_sign_in_leaves_the_volume_waiting():
    async with get_sessionmaker()() as session:
        volume_id = await _volume(session)
        with pytest.raises(PermanentError, match="sign in again"):
            await _run(session, FakeJnc(signed_in=False), volume_id)
        await session.rollback()
        assert (await _row(session, volume_id)).state == "known"
```

- [ ] **Step 2: Run it.** Expected: FAIL, `ModuleNotFoundError: app.handlers.volume_download`.

- [ ] **Step 3: Implement.** `backend/app/handlers/volume_download.py`:

```python
"""Download one owned volume, exactly as J-Novel Club serves it.

The link is read fresh from the library every time: it carries its own
authorisation, J-Novel Club asks that it not be stored, and one read hours ago
may have lapsed. The file is placed untouched - its number and position in
Komga are set through Komga's API, never by rewriting the publisher's EPUB.
"""

import os
import tempfile
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.downloader.cbz import place_file
from app.downloader.epub import is_epub
from app.downloader.paths import volume_path
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.sources.base import SignInRequired, get_prose_source

SITE = "jnovelclub"


async def _set_state(ctx: JobContext, volume_id: int, state: str) -> None:
    await ctx.session.execute(
        text("update volume set state = :state where id = :id"), {"state": state, "id": volume_id}
    )
    await ctx.session.commit()


@register(JobType.VOLUME_DOWNLOAD)
async def handle(ctx: JobContext) -> None:
    volume_id = int(ctx.payload["volume_id"])
    row = (
        await ctx.session.execute(
            text(
                """
                select v.id, v.series_id, v.number, v.source_volume_id, v.title, v.file_path,
                       v.last_updated, s.slug
                  from volume v join series s on s.id = v.series_id
                 where v.id = :id
                """
            ),
            {"id": volume_id},
        )
    ).first()
    if row is None:
        raise PermanentError(f"volume {volume_id} no longer exists")
    await _set_state(ctx, volume_id, "downloading")

    source = get_prose_source(SITE)
    try:
        owned = await source.library()
    except SignInRequired as exc:
        await _set_state(ctx, volume_id, "known")
        raise PermanentError(str(exc)) from exc

    entry = next((v for v in owned if v.volume_id == row.source_volume_id), None)
    if entry is None or entry.epub_link is None:
        await _set_state(ctx, volume_id, "known")
        reason = "is no longer in your J-Novel Club library" if entry is None else (
            "has no EPUB download"
        )
        raise PermanentError(f"volume {row.number} {reason}")

    try:
        data = await source.fetch_volume(entry.epub_link)
        if not is_epub(data):
            raise RuntimeError(f"J-Novel Club's answer for volume {row.number} is not an EPUB")
    except Exception:
        # Back to known for the screens; the retry ladder runs the job again,
        # and the next attempt reads a fresh link.
        await _set_state(ctx, volume_id, "known")
        raise

    title = entry.title or row.title
    destination = volume_path(Path(get_settings().library_path), row.slug, row.number, title)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, scratch_name = tempfile.mkstemp(dir=destination.parent, suffix=".epub.part")
    with os.fdopen(handle_fd, "wb") as scratch:
        scratch.write(data)
    await place_file(Path(scratch_name), destination)
    # A revision whose title changed lands under a new name; the previous file
    # is that same volume's older edition, and it goes only once the new one
    # is in place.
    if row.file_path and row.file_path != str(destination):
        Path(row.file_path).unlink(missing_ok=True)

    await ctx.session.execute(
        text(
            """
            update volume
               set state = 'downloaded', file_path = :path, title = :title,
                   downloaded_updated = cast(:updated as timestamptz)
             where id = :id
            """
        ),
        {
            "id": volume_id,
            "path": str(destination),
            "title": title,
            "updated": entry.last_updated or row.last_updated,
        },
    )
    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": row.series_id},
        series_id=row.series_id,
        dedupe_key=f"komga_scan:{row.series_id}",
    )
    await ctx.session.commit()
    await ctx.log(f"saved volume {row.number}", pct=100)
```

Add `volume_download` to `worker/main.py`'s handler import list.

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_volume_download.py tests/test_lanes.py -q`, then ruff. Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/volume_download.py backend/app/worker/main.py backend/tests/test_volume_download.py
git commit -m "feat(jnovelclub): download an owned volume as J-Novel Club's own EPUB"
```

---

### Task 6: Komga places volumes after their parts

**Files:**
- Modify: `backend/app/komga/client.py` (`KomgaBook`, `parse_books`, `update_book_metadata`), `backend/app/handlers/komga_scan.py`
- Test: `backend/tests/test_komga_volumes.py`

**Interfaces:**
- Consumes: `volume_number_from_filename` (Task 1); `volume` (Task 3).
- Produces:
  - `KomgaBook.number`, `.number_sort`, `.number_lock`, `.number_sort_lock`, all defaulted.
  - `KomgaClient.update_book_metadata(book_id, body)`.
  - `wanted_volume_metadata(number, last_part) -> dict`.
  - `async reconcile_volumes(ctx, client, series_id, books) -> int`.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_komga_volumes.py`:

```python
"""Volume books sit right after their own parts in Komga, numbered and locked."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext
from app.handlers.komga_scan import reconcile_volumes, wanted_volume_metadata
from app.komga.client import KomgaBook, parse_books
from app.queue import repo

pytestmark = pytest.mark.asyncio


def test_a_volume_sorts_just_after_its_last_part():
    assert wanted_volume_metadata(Decimal(16), Decimal(216)) == {
        "number": "Vol. 16", "numberLock": True, "numberSort": 216.5, "numberSortLock": True,
    }


def test_a_volume_without_known_parts_sorts_last():
    assert wanted_volume_metadata(Decimal(3), None)["numberSort"] == 100003.0


def test_book_numbers_and_locks_are_read():
    [book] = parse_books({"content": [{
        "id": "B1", "seriesId": "S1", "name": "x", "url": "/manga/a/a - Vol.0016.epub",
        "metadata": {"number": "Vol. 16", "numberSort": 216.5,
                     "numberLock": True, "numberSortLock": True},
    }]})
    assert (book.number, book.number_sort, book.number_lock, book.number_sort_lock) == (
        "Vol. 16", 216.5, True, True,
    )


class FakeKomga:
    def __init__(self):
        self.patched: list[tuple[str, dict]] = []

    async def update_book_metadata(self, book_id, body):
        self.patched.append((book_id, body))


def _book(book_id, filename, **metadata):
    return KomgaBook(id=book_id, series_id="S1", name=filename, path=f"/manga/a/{filename}",
                     completed=False, page=0, **metadata)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


async def _ctx(session) -> tuple[JobContext, int]:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('A', 'a', false, '{}'::jsonb, 'prose') returning id"
            )
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into volume (series_id, number, source_volume_id, status, last_part, state)"
            " values (:s, 16, 'VOL-16', 'owned', 216, 'queued')"
        ),
        {"s": series_id},
    )
    await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
    await session.commit()
    return JobContext(session=session, job=job), int(series_id)


async def test_volume_books_are_matched_and_numbered():
    async with get_sessionmaker()() as session:
        ctx, series_id = await _ctx(session)
        komga = FakeKomga()
        books = [_book("B1", "a - Vol.0016 - Volume 16.epub"), _book("B2", "a - Ch.0204.epub")]
        assert await reconcile_volumes(ctx, komga, series_id, books) == 1
        row = (await session.execute(text("select komga_book_id, state from volume"))).one()
        assert (row.komga_book_id, row.state) == ("B1", "downloaded")
        assert komga.patched == [("B1", wanted_volume_metadata(Decimal(16), Decimal(216)))]


async def test_a_volume_already_in_place_is_not_patched_again():
    async with get_sessionmaker()() as session:
        ctx, series_id = await _ctx(session)
        komga = FakeKomga()
        books = [_book("B1", "a - Vol.0016.epub", number="Vol. 16", number_sort=216.5,
                       number_lock=True, number_sort_lock=True)]
        await reconcile_volumes(ctx, komga, series_id, books)
        assert komga.patched == []
```

- [ ] **Step 2: Run it.** Expected: FAIL, `ImportError: cannot import name 'reconcile_volumes'`.

- [ ] **Step 3: Komga client.** In `backend/app/komga/client.py`, extend `KomgaBook` with defaults, so every existing constructor keeps working:

```python
    number: str | None = None
    number_sort: float | None = None
    number_lock: bool = False
    number_sort_lock: bool = False
```

In `parse_books`, read `metadata = item.get("metadata") or {}` and pass:

```python
                number=metadata.get("number"),
                number_sort=metadata.get("numberSort"),
                number_lock=bool(metadata.get("numberLock")),
                number_sort_lock=bool(metadata.get("numberSortLock")),
```

Add to `KomgaClient`:

```python
    async def update_book_metadata(self, book_id: str, body: dict[str, Any]) -> None:
        """PATCH a book's metadata. Fields left out of `body` are unchanged
        (Komga BookController, PATCH /api/v1/books/{bookId}/metadata)."""
        response = await self._request("PATCH", f"{API}/books/{book_id}/metadata", json=body)
        response.raise_for_status()
```

- [ ] **Step 4: The scan step.** In `backend/app/handlers/komga_scan.py`, import `volume_number_from_filename` from `app.downloader.paths`, plus `Decimal` if missing, and add:

```python
# A volume whose parts are unknown goes after every part: 100000 is past any
# part number a series reaches, and adding the volume number keeps volumes in
# order among themselves.
UNPLACED_VOLUME_SORT = 100000


def wanted_volume_metadata(number: Decimal, last_part: Decimal | None) -> dict:
    """Where a volume sits among its series' parts: right after the last one."""
    sort = float(last_part) + 0.5 if last_part is not None else UNPLACED_VOLUME_SORT + float(number)
    shown = format(number.normalize(), "f")
    return {"number": f"Vol. {shown}", "numberLock": True, "numberSort": sort, "numberSortLock": True}


async def reconcile_volumes(ctx: JobContext, client, series_id: int, books) -> int:
    """Match volume books to volume rows, and number them in Komga.

    Locked, so Komga's own import of J-Novel Club's metadata cannot move the
    book back; checked first, so a book already in place costs no request.
    Failures are logged, not raised - chapters are this job's real work.
    """
    rows = (
        await ctx.session.execute(
            text("select id, number, last_part from volume where series_id = :s"),
            {"s": series_id},
        )
    ).all()
    by_number = {Decimal(str(row.number)): row for row in rows}
    matched = 0
    for book in books:
        number = volume_number_from_filename(book.filename)
        row = by_number.get(number) if number is not None else None
        if row is None:
            continue
        matched += 1
        await ctx.session.execute(
            text(
                """
                update volume
                   set komga_book_id = :book, state = 'downloaded',
                       file_path = coalesce(file_path, :path)
                 where id = :id
                """
            ),
            {"book": book.id, "path": book.path, "id": row.id},
        )
        last_part = Decimal(str(row.last_part)) if row.last_part is not None else None
        want = wanted_volume_metadata(number, last_part)
        current = (book.number, book.number_sort, book.number_lock, book.number_sort_lock)
        if current == (want["number"], want["numberSort"], True, True):
            continue
        try:
            await client.update_book_metadata(book.id, want)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            await ctx.log(f"could not place volume {number} in Komga: {exc}", level="warning")
    return matched
```

In `handle`, right after the commit that follows `adopt_book_ids`, add:

```python
    volumes = await reconcile_volumes(ctx, client, series_id, books)
    if volumes:
        await ctx.log(f"{volumes} volumes matched")
    await ctx.session.commit()
```

and change the cover call to skip volume books, which carry J-Novel Club's own cover:

```python
    chapter_books = [b for b in books if volume_number_from_filename(b.filename) is None]
    await ensure_book_covers(ctx, client, series_id, chapter_books)
```

- [ ] **Step 5: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_komga_volumes.py tests/test_komga_client.py tests/test_komga_cover.py tests/test_komga_book_cover.py tests/test_komga_completed.py -q`, then ruff. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/komga/client.py backend/app/handlers/komga_scan.py backend/tests/test_komga_volumes.py
git commit -m "feat(komga): place owned volumes right after their parts, numbered and locked"
```

---

### Task 7: Volumes in the series API

**Files:**
- Modify: `backend/app/api/routes_series.py` (`series_detail`)
- Test: `backend/tests/test_komga_volumes.py` (append)

**Interfaces:**
- Produces: `GET /api/series/{id}` → `"volumes": [{"number": float, "title", "status", "state", "last_updated": iso | null, "revised": bool, "komga_book_id"}]`, ordered by number.

- [ ] **Step 1: Write the failing test.** Append:

```python
from httpx import ASGITransport, AsyncClient

from app.api.main import app


async def test_series_detail_lists_its_volumes():
    async with get_sessionmaker()() as session:
        ctx, series_id = await _ctx(session)
        await session.execute(
            text(
                "update volume set state = 'downloaded', last_updated = now(),"
                " downloaded_updated = now() - interval '1 day'"
            )
        )
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{series_id}")).json()
    [volume] = detail["volumes"]
    assert (volume["number"], volume["status"], volume["state"], volume["revised"]) == (
        16.0, "owned", "downloaded", True,
    )


async def test_a_series_without_volumes_has_an_empty_list():
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('B', 'b', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{series_id}")).json()
    assert detail["volumes"] == []
```

Move the two new imports to the top of the module.

- [ ] **Step 2: Run it.** Expected: FAIL, `KeyError: 'volumes'`.

- [ ] **Step 3: Implement.** In `series_detail`, after the chapters query:

```python
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
```

and, in the result dict after `"chapters"`:

```python
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
```

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_komga_volumes.py tests/test_series_detail_links.py tests/test_chapter_expiry.py -q`, then ruff. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_series.py backend/tests/test_komga_volumes.py
git commit -m "feat(api): list a series' owned volumes"
```

---

### Task 8: Frontend: Volumes panel, sync button, cron field

**Files:**
- Create: `frontend/src/features/series/VolumesPanel.tsx`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/features/series/SeriesDetailPage.tsx`, `frontend/src/features/settings/JNovelClubCard.tsx`, `frontend/src/features/settings/PipelineFields.tsx`

**Interfaces:**
- Consumes: Task 7's `volumes`; Task 4's `POST /library-sync` and `cron_jnc_library_sync`.
- Produces:
  - `interface SeriesVolume { number: number; title: string | null; status: 'owned' | 'preorder'; state: string; last_updated: string | null; revised: boolean; komga_book_id: string | null }`
  - `SeriesDetail.volumes: SeriesVolume[]`
  - `api.jncLibrarySync()`
  - `<VolumesPanel volumes komgaBaseUrl />`

- [ ] **Step 1: Types and client.** In `api.ts`:
  - Add the `SeriesVolume` interface above `SeriesDetail`.
  - Add `volumes: SeriesVolume[]` to `SeriesDetail`.
  - Add `jncLibrarySync: () => request<{ ok: boolean; job_id: number | null }>('/api/sources/jnovelclub/library-sync', { method: 'POST' })` next to `jncSignOut`.

- [ ] **Step 2: The panel.** `frontend/src/features/series/VolumesPanel.tsx`. Copy the card shell and heading classes from `SynopsisPanel.tsx` or `SyncTargets.tsx`, and the link classes from the "Read in Komga" anchor in `ChapterTable.tsx`, so nothing new needs a class check. Confirm with the dist grep anyway.

```tsx
import { Badge, Card, Icon } from '../../ui'
import type { SeriesVolume } from '../../lib/api'
import { externalBase } from '../../lib/externalUrl'

// The volumes the user owns on J-Novel Club. They download by themselves -
// buying one is the decision - so this panel only reports where each stands.
function stateBadge(volume: SeriesVolume) {
  if (volume.status === 'preorder') return <Badge tone="tertiary">Pre-order</Badge>
  if (volume.state === 'downloaded') return <Badge tone="secondary">Downloaded</Badge>
  if (volume.state === 'failed') return <Badge tone="error">Failed</Badge>
  if (volume.revised) return <Badge tone="warning">Updated, downloading again</Badge>
  return <Badge tone="primary">Queued</Badge>
}

export function VolumesPanel({
  volumes,
  komgaBaseUrl,
}: {
  volumes: SeriesVolume[]
  komgaBaseUrl: string
}) {
  const komgaHref = externalBase(komgaBaseUrl)
  if (volumes.length === 0) return null
  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <h2 className="text-title-md text-on-surface">Volumes</h2>
      <ul className="flex flex-col gap-space-xs">
        {volumes.map((volume) => (
          <li key={volume.number} className="flex flex-wrap items-center justify-between gap-space-sm">
            <span className="text-body-sm text-on-surface">
              Vol. {volume.number}
              {volume.title && <span className="text-on-surface-variant"> · {volume.title}</span>}
            </span>
            <span className="inline-flex items-center gap-space-xs">
              {stateBadge(volume)}
              {komgaHref && volume.komga_book_id && volume.state === 'downloaded' && (
                <a
                  href={`${komgaHref}/book/${volume.komga_book_id}/read-epub`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg px-space-sm py-1 font-mono text-label-sm text-primary transition-colors hover:bg-primary/[0.12]"
                >
                  <Icon name="book" className="h-3.5 w-3.5" />
                  Read in Komga
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
```

Check that `Card` accepts `as` and `elevated` (Task 15 of the light-novels branch used them in `KindControl`), and that a `failed` volume and a queued one are distinguishable. The order above matters: a revised volume is `known`, so its check comes after `downloaded` and `failed`.

- [ ] **Step 3: Place it.** In `SeriesDetailPage.tsx`, render `<VolumesPanel volumes={volumes} komgaBaseUrl={komgaPublicUrl} />` in the aside, directly under `<MappingPanel …/>`. Take `volumes` and the Komga URL the same way the page already gets `chapters` and `komga_public_url`.

- [ ] **Step 4: Sync button.** In `JNovelClubCard.tsx`, when `session?.via !== 'none'`, render next to Sign out (or alone when `via === 'env'`):

```tsx
        <Button variant="surface" onClick={syncLibrary} disabled={busy}>
          Sync library now
        </Button>
```

with

```tsx
  const syncLibrary = async () => {
    setBusy(true)
    setFailure(null)
    try {
      await api.jncLibrarySync()
    } catch (caught) {
      setFailure(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }
```

- [ ] **Step 5: Cron field.** In `PipelineFields.tsx`, add a `FieldCard` after "Chapter Discovery", copying that card's shape exactly:
  - label "J-Novel Club library";
  - description "Download volumes you own on J-Novel Club (`cron_jnc_library_sync`).";
  - `<CronInput settingKey="cron_jnc_library_sync" … />`.

- [ ] **Step 6: Build and check.** `npm run build` from `frontend/`; then grep every class used in `VolumesPanel.tsx` in `dist/assets/*.css`, and list the hits in the report.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/features/series/VolumesPanel.tsx frontend/src/features/series/SeriesDetailPage.tsx frontend/src/features/settings/JNovelClubCard.tsx frontend/src/features/settings/PipelineFields.tsx
git commit -m "feat(web): show owned J-Novel Club volumes and sync the library on demand"
```

---

### Task 9: Documentation

- [ ] **Step 1:** Write the docs.
  - `docs/features.md`, in the J-Novel Club section, add a paragraph covering:
    - owned volumes download by themselves for mapped series, as J-Novel Club's own EPUB;
    - they sit in the same Komga series right after their parts;
    - a revised volume replaces the old file;
    - pre-orders wait;
    - owned volumes of series that aren't mapped are named in the library-sync log;
    - the "Sync library now" button and the 6-hour cron.
  - `docs/data-model.md`, a `### volume` section under "Reading and downloading":
    - its columns, and that it is kept apart from `chapter`;
    - `downloaded_updated` versus `last_updated`;
    - download links are never stored.
- [ ] **Step 2: Commit.** `git add docs/features.md docs/data-model.md && git commit -m "docs: describe owned J-Novel Club volumes"`

---

### Task 10: Full checks, then the live run with the user's go-ahead

- [ ] **Step 1:** Run the full suite on a new database:
  - `docker run -d --name manga-pg-vol-fresh -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5435:5432 postgres:17-alpine`
  - From `backend/`: `POSTGRES_HOST=localhost POSTGRES_PORT=5435 .venv/bin/python -m pytest tests -q`, then ruff.
  - From `frontend/`: `npm run build`.

  All must pass.
- [ ] **Step 2: Stop and ask the user.** Then:
  1. `pg_dump` the live database into `data/backups/`.
  2. `docker compose build api web && docker compose up -d --force-recreate api worker worker-download web`, which applies 0023.
  3. Press "Sync library now".
  4. Expect the job to finish done, with "0 owned on J-Novel Club, 0 queued", no rows and no failed job.
  5. Report that a real volume download stays unverified until the account owns one.
