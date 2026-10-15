# Volume Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a volume is read in Komga, by finishing its book or every part of a volume the user owns, each reading list's volumes-read moves forward to it, and its chapters-read moves to the volume's last part. Never backwards, never past the list's own totals.

**Architecture:**
- `list_entry` gains `user_progress_volume` and `total_volumes`, filled by list sync from fields the providers already return.
- `push_progress` gains an optional `volume`, still one request per entry. A provider that refuses a write raises `WriteRefused`.
- A pure module works out the furthest volume read.
- `progress_push` sends it with the chapter, and retries without the volume if a provider refuses it.
- `komga_scan` marks volume books read up to what the lists say.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Alembic, httpx, pytest; React + TypeScript + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-10-16-jnovelclub-volume-progress-design.md`. Read it first; its provider-contract table is the source for every field name below.

## Global Constraints

- Branch `feat/jnovelclub-volume-progress`, based on `feat/jnovelclub-volumes`. Commit there.
- Commits: English, one focused change per commit, **no assistant attribution of any kind**. The repo's `attribution-check` CI fails on it.
- Tests: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest <files> -q` from `backend/` (container `manga-pg-jnc`). Run the brief's tests plus the existing modules covering changed code; never the full suite (the last task runs it once).
- Ruff every task: `.venv/bin/python -m ruff check app/ tests/` from `backend/`.
- `asyncio_mode = "auto"`: no module-level `pytestmark = pytest.mark.asyncio` in modules with sync tests.
- `providers/`, `komga/` and `sources/` never touch the database; `handlers/` and `api/` do.
- asyncpg cannot infer a null parameter's type: `cast(:x as integer)` where a value may be null.
- Comments explain why a line exists, never what it does.
- **Field names are exactly the documented ones:**
  - MyAnimeList `num_volumes_read` / `num_volumes`;
  - AniList `progressVolumes` / `volumes`;
  - MangaBaka `progress_volume`.
- **Never send AniList `progressVolumes: null`:** it would clear the user's count.
- `push_progress(..., volume=None)` must send exactly today's request; existing callers stay unchanged.
- Comics never send a volume.
- Frontend: no hex, px or rem literals; every new class must be found by `grep` in `frontend/dist/` after `npm run build`. Never run `docker compose`, except in the last task after the user says go.

## Review Focus

1. **A provider refuses the volume.** Any of 400, 422 or an AniList GraphQL error. Expected: the chapter still lands, from one retry without the volume, and only `user_progress_chapter` is updated. Pinned in Task 4 (`test_a_refused_volume_is_retried_without_it`).
2. **The list already records a higher volume than Komga shows** (read elsewhere). Expected: no volume sent, and the chapter still pushed when it moves. Pinned in Task 4 (`test_a_list_already_past_the_volume_gets_no_volume`).
3. **Only a volume book is finished; no chapter book is.** Expected: the push still happens (today the job returns early when no chapter is finished), with chapter = the volume's last part. Pinned in Task 4 (`test_a_finished_volume_alone_pushes`).
4. **MyAnimeList's `num_volumes: 0`.** Expected: treated as unknown, no cap, and never capped to 0. Pinned in Task 1 (`test_mal_reads_volumes_and_treats_zero_total_as_unknown`) and Task 3 (`test_pushable_volume`).
5. **A list sync of an entry with no volume fields** (older fixtures, MangaBaka without totals). Expected: 0 and None, never a crash or a bind error. Pinned in Task 1 (`test_entries_without_volume_fields_default_safely`).

---

## File Structure

**Create:**
- `backend/alembic/versions/0024_list_entry_volumes.py`
- `backend/app/handlers/volume_progress.py`: `VolumeRow`, `furthest_volume`, `pushable_volume`. Pure.
- Tests: `tests/test_provider_volumes.py`, `tests/test_volume_progress.py`, `tests/test_volume_progress_push.py`.

**Modify:**

| File | Change |
|---|---|
| `backend/app/providers/base.py` | `ListEntryDTO` fields, `WriteRefused`, the `push_progress` signature |
| `backend/app/providers/mal.py`, `anilist.py`, `mangabaka.py`, `local.py` | parse and write volumes |
| `backend/app/models.py` | `ListEntry` columns |
| `backend/app/handlers/list_sync.py` | `upsert_entry` |
| `backend/app/handlers/progress_push.py` | volume computation, push and retry |
| `backend/app/handlers/komga_scan.py` | `mark_read_up_to_lists` |
| `backend/app/api/routes_series.py` | entries' `user_progress_volume` |
| `frontend/src/lib/api.ts`, `frontend/src/features/series/SyncTargets.tsx` | show the volume count |
| `docs/features.md`, `docs/data-model.md` | docs |

---

### Task 1: Providers read volume progress

**Files:**
- Modify: `backend/app/providers/base.py` (`ListEntryDTO`), `backend/app/providers/mal.py` (`parse_page`), `backend/app/providers/anilist.py` (`parse_list`), `backend/app/providers/mangabaka.py` (`parse_library`)
- Test: `backend/tests/test_provider_volumes.py`

**Interfaces:**
- Produces: `ListEntryDTO.progress_volume: int = 0` and `ListEntryDTO.total_volumes: int | None = None`.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_provider_volumes.py`:

```python
"""The providers' volume counts, read from the fields they already return.

Field names are the providers' own (spec, "Provider contracts"): MyAnimeList
num_volumes_read/num_volumes, AniList progressVolumes/volumes, MangaBaka
progress_volume.
"""

from app.providers.anilist import parse_list
from app.providers.mal import parse_page
from app.providers.mangabaka import parse_library


def test_mal_reads_volumes_and_treats_zero_total_as_unknown():
    page = {"data": [
        {"node": {"id": 1, "title": "A", "num_volumes": 16},
         "list_status": {"status": "reading", "num_chapters_read": 3, "num_volumes_read": 2}},
        {"node": {"id": 2, "title": "B", "num_volumes": 0},
         "list_status": {"status": "reading", "num_volumes_read": 0}},
    ]}
    first, second = parse_page(page)
    assert (first.progress_volume, first.total_volumes) == (2, 16)
    # MyAnimeList documents 0 as "unknown": it must never become a cap of 0.
    assert (second.progress_volume, second.total_volumes) == (0, None)


def test_anilist_reads_volumes():
    data = {"MediaListCollection": {"lists": [{"entries": [{
        "status": "CURRENT", "progress": 12, "progressVolumes": 3,
        "media": {"id": 7, "chapters": 40, "volumes": 10,
                  "title": {"romaji": "A", "english": None, "native": None}},
    }]}]}}
    [entry] = parse_list(data)
    assert (entry.progress_volume, entry.total_volumes) == (3, 10)


def test_mangabaka_reads_volume_progress_without_a_total():
    payload = {"data": [{
        "series_id": 5, "state": "reading", "progress_chapter": 4, "progress_volume": 2,
        "Series": {"id": 5, "title": "A", "type": "novel"},
    }]}
    [entry] = parse_library(payload)
    assert (entry.progress_volume, entry.total_volumes) == (2, None)


def test_entries_without_volume_fields_default_safely():
    [mal] = parse_page({"data": [{"node": {"id": 1, "title": "A"},
                                  "list_status": {"status": "reading"}}]})
    assert (mal.progress_volume, mal.total_volumes) == (0, None)
    anilist_data = {"MediaListCollection": {"lists": [{"entries": [{
        "status": "CURRENT", "progress": 1, "progressVolumes": None,
        "media": {"id": 7, "volumes": None, "title": {"romaji": "A"}},
    }]}]}}
    [anilist] = parse_list(anilist_data)
    assert (anilist.progress_volume, anilist.total_volumes) == (0, None)
```

Before running it, open `backend/tests/fixtures/mangabaka_library.json` and check the shape `parse_library` actually reads: the key holding the rows, and whether the series sits under `Series` or `series`. Adjust the MangaBaka payloads above to that shape, then note the adjustment in the report. The assertions do not change.

- [ ] **Step 2: Run it.** Expected: FAIL, `AttributeError: 'ListEntryDTO' object has no attribute 'progress_volume'`.

- [ ] **Step 3: Implement.**

In `providers/base.py` `ListEntryDTO`, after `total_chapters`:

```python
    # Volumes, beside chapters. 0 and None are the defaults a provider that
    # says nothing leaves; MyAnimeList's documented "0 means unknown" total is
    # turned into None by its parser, so it can never become a cap of zero.
    progress_volume: int = 0
    total_volumes: int | None = None
```

In `mal.py` `parse_page`, next to `progress_chapter=` and `total_chapters=`:

```python
                progress_volume=int(status.get("num_volumes_read") or 0),
                total_volumes=node.get("num_volumes") or None,
```

and add `num_volumes` to the list request's `fields` string if it is not already there (the module comment lists it; confirm it in the fields constant).

In `anilist.py` `parse_list`:

```python
                    progress_volume=int(entry.get("progressVolumes") or 0),
                    total_volumes=media.get("volumes") or None,
```

In `mangabaka.py` `parse_library`:

```python
                progress_volume=int(row.get("progress_volume") or 0),
```

MangaBaka's library schema has no volume total, so `total_volumes` keeps its default.

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_provider_volumes.py tests/test_providers_parse.py tests/test_mangabaka_provider.py -q`, then ruff. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/base.py backend/app/providers/mal.py backend/app/providers/anilist.py backend/app/providers/mangabaka.py backend/tests/test_provider_volumes.py
git commit -m "feat(providers): read volume progress and totals from every list"
```

---

### Task 2: Store volume progress on list entries

**Files:**
- Create: `backend/alembic/versions/0024_list_entry_volumes.py`
- Modify: `backend/app/models.py` (`ListEntry`), `backend/app/handlers/list_sync.py` (`upsert_entry`)
- Test: `backend/tests/test_provider_volumes.py` (append)

**Interfaces:**
- Consumes: Task 1's DTO fields.
- Produces: the columns `list_entry.user_progress_volume integer null` and `list_entry.total_volumes integer null`.

- [ ] **Step 1: Write the failing test.** Append:

```python
import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.handlers.list_sync import upsert_entry
from app.providers.base import ListEntryDTO


@pytest.fixture
async def series_id():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        sid = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('A', 'a', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        await session.commit()
    return int(sid)


async def test_list_sync_stores_volume_progress(series_id):
    dto = ListEntryDTO(provider=Provider.MAL, media_id="1", status=ListStatus.READING,
                       progress_volume=2, total_volumes=16)
    async with get_sessionmaker()() as session:
        await upsert_entry(session, dto, series_id)
        await session.commit()
        row = (
            await session.execute(
                text("select user_progress_volume, total_volumes from list_entry")
            )
        ).one()
    assert (row.user_progress_volume, row.total_volumes) == (2, 16)


async def test_an_unknown_total_is_stored_as_null(series_id):
    dto = ListEntryDTO(provider=Provider.MAL, media_id="1", status=ListStatus.READING)
    async with get_sessionmaker()() as session:
        await upsert_entry(session, dto, series_id)
        await session.commit()
        row = (
            await session.execute(
                text("select user_progress_volume, total_volumes from list_entry")
            )
        ).one()
    assert (row.user_progress_volume, row.total_volumes) == (0, None)
```

Move the imports to the module top.

- [ ] **Step 2: Run it.** Expected: FAIL, `column "user_progress_volume" does not exist`.

- [ ] **Step 3: Implement.** `backend/alembic/versions/0024_list_entry_volumes.py`:

```python
"""list_entry volumes: volumes read and the list's own volume count

Revision ID: 0024_list_entry_volumes
Revises: 0023_volume
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_list_entry_volumes"
down_revision: str | None = "0023_volume"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both nullable and not backfilled: the next list sync fills them, and
    # until then the forward-only guard reads null as 0 and the cap as none.
    op.add_column("list_entry", sa.Column("user_progress_volume", sa.Integer()))
    op.add_column("list_entry", sa.Column("total_volumes", sa.Integer()))


def downgrade() -> None:
    op.drop_column("list_entry", "total_volumes")
    op.drop_column("list_entry", "user_progress_volume")
```

In `models.py` `ListEntry`, after `total_chapters`:

```python
    user_progress_volume: Mapped[int | None] = mapped_column(Integer)
    total_volumes: Mapped[int | None] = mapped_column(Integer)
```

In `list_sync.upsert_entry`:
- Add `user_progress_volume, total_volumes` to the column list.
- Add `:progress_volume, cast(:total_volumes as integer)` to `values`.
- Add `user_progress_volume = excluded.user_progress_volume, total_volumes = excluded.total_volumes` to the `do update set`.
- Add `"progress_volume": dto.progress_volume, "total_volumes": dto.total_volumes` to the parameters.

Leave `upsert_entry_status` alone: the Discovery path must not touch progress.

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_provider_volumes.py tests/test_series_kind_sync.py tests/test_cross_reference_dedupe.py tests/test_migration_chain.py -q`, then ruff. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0024_list_entry_volumes.py backend/app/models.py backend/app/handlers/list_sync.py backend/tests/test_provider_volumes.py
git commit -m "feat(sync): keep each list's volume progress and volume count"
```

---

### Task 3: Write volume progress, and say when a provider refuses

**Files:**
- Modify: `backend/app/providers/base.py`, `mal.py`, `anilist.py`, `mangabaka.py`, `local.py`
- Create: `backend/app/handlers/volume_progress.py`
- Test: `backend/tests/test_volume_progress.py`

**Interfaces:**
- Produces:
  - `class WriteRefused(RuntimeError)` in `app.providers.base`.
  - `push_progress(self, access_token, media_id, chapter: int, volume: int | None = None) -> None` on every provider. It raises `WriteRefused` on a 400 or 422 (or an AniList GraphQL error) for a progress write.
  - `VolumeRow`, `furthest_volume`, `pushable_volume` in `app.handlers.volume_progress` (verified in planning).

- [ ] **Step 1: Write the failing tests.** `backend/tests/test_volume_progress.py`:

```python
"""Which volume Komga reading amounts to, and what each list may be sent."""

from decimal import Decimal

from app.handlers.volume_progress import VolumeRow, furthest_volume, pushable_volume
from app.komga.client import KomgaBook


def _book(book_id, completed=True):
    return KomgaBook(id=book_id, series_id="S", name=book_id, path=f"/m/{book_id}",
                     completed=completed, page=0)


V15 = VolumeRow(Decimal(15), Decimal(193), Decimal(203), "V15")
V16 = VolumeRow(Decimal(16), Decimal(204), Decimal(216), "V16")


def _parts(first, last, *, read=True, missing_book=None, missing_row=None):
    rows = {}
    for n in range(first, last + 1):
        if n == missing_row:
            continue
        rows[Decimal(n)] = None if n == missing_book else f"P{n}"
    books = [_book(f"P{n}", completed=read) for n in range(first, last + 1)]
    return rows, books


def test_a_finished_volume_book_is_read():
    assert furthest_volume([_book("V16")], [V15, V16], {}) == (16, Decimal(216))


def test_an_unfinished_volume_book_is_not():
    assert furthest_volume([_book("V16", completed=False)], [V16], {}) == (None, None)


def test_every_part_finished_reads_the_volume():
    rows, books = _parts(204, 216)
    assert furthest_volume(books, [V16], rows) == (16, Decimal(216))


def test_one_unread_part_keeps_the_volume_unread():
    rows, books = _parts(204, 216)
    books[-1] = _book("P216", completed=False)
    assert furthest_volume(books, [V16], rows) == (None, None)


def test_a_part_never_downloaded_keeps_the_volume_unread():
    rows, books = _parts(204, 216, missing_book=210)
    assert furthest_volume(books, [V16], rows) == (None, None)


def test_a_part_never_discovered_keeps_the_volume_unread():
    rows, books = _parts(204, 216, missing_row=210)
    assert furthest_volume(books, [V16], rows) == (None, None)


def test_a_volume_without_a_known_range_needs_its_book():
    no_range = VolumeRow(Decimal(16), None, None, "V16")
    rows, books = _parts(204, 216)
    assert furthest_volume(books, [no_range], rows) == (None, None)


def test_the_furthest_wins_and_a_half_volume_counts_as_the_one_below():
    half = VolumeRow(Decimal("15.5"), None, Decimal(210), "V15.5")
    assert furthest_volume([_book("V15"), _book("V15.5")], [V15, half], {}) == (15, Decimal(210))


def test_comics_have_no_volumes():
    assert furthest_volume([_book("C1")], [], {Decimal(1): "C1"}) == (None, None)


def test_pushable_volume():
    assert pushable_volume(16, 20, 3) == 16
    assert pushable_volume(16, 12, 3) == 12  # capped at the list's total
    assert pushable_volume(16, None, 3) == 16  # no total, no cap
    assert pushable_volume(16, 0, None) == 16  # 0 is unknown, not a cap
    assert pushable_volume(16, None, 16) is None  # not forward
    assert pushable_volume(None, 20, 3) is None


# --- provider request bodies -------------------------------------------------

import json  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.providers.anilist import AniListSource  # noqa: E402
from app.providers.base import WriteRefused  # noqa: E402
from app.providers.mal import MyAnimeListSource  # noqa: E402
from app.providers.mangabaka import MangaBakaSource  # noqa: E402


def _recorder(status=200, body=None):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    return seen, httpx.MockTransport(handler)


async def test_mal_sends_volumes_only_when_given():
    seen, transport = _recorder()
    async with httpx.AsyncClient(transport=transport) as client:
        await MyAnimeListSource(client).push_progress("t", "1", 12)
        await MyAnimeListSource(client).push_progress("t", "1", 12, volume=3)
    assert dict(httpx.QueryParams(seen[0].content.decode())) == {"num_chapters_read": "12"}
    assert dict(httpx.QueryParams(seen[1].content.decode())) == {
        "num_chapters_read": "12", "num_volumes_read": "3",
    }


async def test_anilist_never_sends_a_null_volume():
    body = {"data": {"SaveMediaListEntry": {"id": 1, "progress": 12}}}
    seen, transport = _recorder(body=body)
    async with httpx.AsyncClient(transport=transport) as client:
        await AniListSource(client).push_progress("t", "7", 12)
        await AniListSource(client).push_progress("t", "7", 12, volume=3)
    first, second = (json.loads(r.content) for r in seen)
    assert first["variables"] == {"mediaId": 7, "progress": 12}
    assert "progressVolumes" not in first["query"]
    assert second["variables"] == {"mediaId": 7, "progress": 12, "progressVolumes": 3}


async def test_mangabaka_sends_volume_progress():
    seen, transport = _recorder(body={"status": 200, "data": []})
    async with httpx.AsyncClient(transport=transport) as client:
        await MangaBakaSource(client).push_progress("k", "5", 12, volume=3)
    assert json.loads(seen[0].content) == [
        {"series_id": 5, "progress_chapter": 12, "progress_volume": 3}
    ]


@pytest.mark.parametrize("status", [400, 422])
async def test_a_refused_write_says_so(status):
    _, transport = _recorder(status=status)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(WriteRefused):
            await MyAnimeListSource(client).push_progress("t", "1", 12, volume=99)
        with pytest.raises(WriteRefused):
            await MangaBakaSource(client).push_progress("k", "5", 12, volume=99)


async def test_an_anilist_graphql_error_is_a_refusal():
    _, transport = _recorder(body={"errors": [{"message": "validation"}], "data": None})
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(WriteRefused):
            await AniListSource(client).push_progress("t", "7", 12, volume=99)
```

Rewrite the mid-file imports as one top-level import block when you write the file (the `noqa` markers only keep the snippet valid as shown). If `MangaBakaSource._upsert` reads the response body, give the MockTransport the shape it needs (read `_upsert` first).

- [ ] **Step 2: Run it.** Expected: FAIL, `ModuleNotFoundError: app.handlers.volume_progress`.

- [ ] **Step 3: The pure module.** `backend/app/handlers/volume_progress.py`. It was run against the tests above during planning and passed:

```python
"""Which volume the reading in Komga amounts to, and what each list may be sent.

Pure: Komga books, volume rows and chapter rows in, numbers out. The handler
reads them and writes the result.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class VolumeRow:
    number: Decimal
    first_part: Decimal | None
    last_part: Decimal | None
    komga_book_id: str | None


def furthest_volume(
    books, volumes: list[VolumeRow], chapter_books: dict[Decimal, str | None]
) -> tuple[int | None, Decimal | None]:
    """The furthest volume read, and the last part it collects.

    A volume is read when its own book is finished, or when every part in its
    range is: each part has a chapter row, each row has a Komga book, and every
    one of those books is finished. A part never downloaded, or never even
    discovered, keeps the volume unread.

    Every list takes a whole count, so a half volume counts as the one below.
    """
    completed = {book.id for book in books if book.completed}
    best: VolumeRow | None = None
    for volume in volumes:
        if not (_book_read(volume, completed) or _parts_read(volume, completed, chapter_books)):
            continue
        if best is None or volume.number > best.number:
            best = volume
    if best is None:
        return None, None
    return int(best.number), best.last_part


def _book_read(volume: VolumeRow, completed: set[str]) -> bool:
    return volume.komga_book_id is not None and volume.komga_book_id in completed


def _parts_read(
    volume: VolumeRow, completed: set[str], chapter_books: dict[Decimal, str | None]
) -> bool:
    if volume.first_part is None or volume.last_part is None:
        return False
    in_range = [
        book for number, book in chapter_books.items()
        if volume.first_part <= number <= volume.last_part
    ]
    # Fewer rows than parts in the range means some part was never discovered.
    expected = int(volume.last_part - volume.first_part) + 1
    if len(in_range) < expected:
        return False
    return all(book is not None and book in completed for book in in_range)


def pushable_volume(read_volume: int | None, total: int | None, current: int | None) -> int | None:
    """The volume to send one list entry, or None when it would not move forward.

    Capped at the list's own total when it states one: no provider documents
    what it does with a count past it.
    """
    if read_volume is None:
        return None
    volume = min(read_volume, total) if total else read_volume
    return volume if volume > (current or 0) else None
```

- [ ] **Step 4: Providers.**

In `providers/base.py`:

```python
class WriteRefused(RuntimeError):
    """The provider answered a write with a validation refusal (400/422, or an
    AniList GraphQL error) rather than failing to be reached. Progress pushing
    retries a refused volume without it, so chapters never stall on a volume
    count a provider will not take."""
```

and change the abstract signature to `push_progress(self, access_token: str, media_id: str, chapter: int, volume: int | None = None) -> None`.

In `mal.py` `push_progress`:

```python
        data = {"num_chapters_read": chapter}
        if volume is not None:
            data["num_volumes_read"] = volume
```

After the request, before `raise_for_status()`:

```python
        if response.status_code in (400, 422):
            raise WriteRefused(f"MyAnimeList refused the progress write: {response.text[:200]}")
```

In `anilist.py`, add a second mutation:

```python
# A separate document rather than a nullable variable: SaveMediaListEntry
# writes whatever it is handed, and a null progressVolumes would clear the
# volume count the user keeps on their own account.
PROGRESS_WITH_VOLUMES_MUTATION = """
mutation ($mediaId: Int, $progress: Int, $progressVolumes: Int) {
  SaveMediaListEntry(mediaId: $mediaId, progress: $progress, progressVolumes: $progressVolumes) {
    id progress progressVolumes
  }
}
"""
```

`push_progress` uses it with `progressVolumes` only when `volume is not None`, and `PROGRESS_MUTATION` otherwise. For the refusal, wrap the `_post` call:

```python
        try:
            await self._post(access_token, query, variables)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 422):
                raise WriteRefused(f"AniList refused the progress write: {exc}") from exc
            raise
        except RuntimeError as exc:
            if str(exc).startswith("anilist error"):
                raise WriteRefused(str(exc)) from exc
            raise
```

In `mangabaka.py`:

```python
    async def push_progress(
        self, access_token: str, media_id: str, chapter: int, volume: int | None = None
    ) -> None:
        fields: dict[str, Any] = {"progress_chapter": chapter}
        if volume is not None:
            fields["progress_volume"] = volume
        try:
            await self._upsert(access_token, media_id, fields)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 422):
                raise WriteRefused(f"MangaBaka refused the progress write: {exc}") from exc
            raise
```

In `local.py`, add the `volume: int | None = None` parameter. The body stays a no-op: the handler writes the row.

Import `WriteRefused` where it is used.

- [ ] **Step 5: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_volume_progress.py tests/test_progress_write.py tests/test_mangabaka_provider.py tests/test_list_write.py -q`, then ruff. Expected: PASS. `test_progress_write` pins that the volume-less call is unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/ backend/app/handlers/volume_progress.py backend/tests/test_volume_progress.py
git commit -m "feat(providers): write volumes read beside chapters, and flag a refused write"
```

---

### Task 4: Push volume progress from Komga reading

**Files:**
- Modify: `backend/app/handlers/progress_push.py`
- Test: `backend/tests/test_volume_progress_push.py`

**Interfaces:**
- Consumes: `furthest_volume`, `pushable_volume`, `VolumeRow` (Task 3); `WriteRefused` (Task 3); `pushable_chapter` (existing); `list_entry.user_progress_volume` and `total_volumes` (Task 2); the `volume` table.
- Produces: `async volume_rows(session, series_id) -> list[VolumeRow]`; `async chapter_books(session, series_id) -> dict[Decimal, str | None]`.

- [ ] **Step 1: Write the failing test.** `backend/tests/test_volume_progress_push.py`:

```python
"""Komga reading moves each list's volumes forward, beside its chapters."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import progress_push
from app.handlers.base import JobContext
from app.komga.client import KomgaBook
from app.providers.base import WriteRefused
from app.queue import repo


class FakeKomgaClient:
    has_credentials = True

    def __init__(self, books):
        self.books = books

    async def books_of_series(self, series_id):
        return self.books


class RecordingProvider:
    def __init__(self, refuse_volume=False):
        self.calls: list[tuple] = []
        self.refuse_volume = refuse_volume

    async def push_progress(self, token, media_id, chapter, volume=None):
        if volume is not None and self.refuse_volume:
            raise WriteRefused("no")
        self.calls.append((media_id, chapter, volume))


def _book(book_id, completed=True):
    return KomgaBook(id=book_id, series_id="K", name=book_id, path=f"/m/{book_id}",
                     completed=completed, page=0)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()


async def _series(session, *, kind="prose", progress_chapter=0, progress_volume=None,
                  total_volumes=None) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind,"
                " komga_series_id) values ('A', 'a', false, '{}'::jsonb, :k, 'K') returning id"
            ),
            {"k": kind},
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, synonyms, status,
                                    user_progress_chapter, user_progress_volume, total_volumes,
                                    raw)
            values ('local', 'L1', :s, '[]'::jsonb, 'reading', :c,
                    cast(:v as integer), cast(:t as integer), '{}'::jsonb)
            """
        ),
        {"s": series_id, "c": progress_chapter, "v": progress_volume, "t": total_volumes},
    )
    await session.execute(
        text(
            "insert into volume (series_id, number, source_volume_id, status, first_part,"
            " last_part, state, komga_book_id)"
            " values (:s, 16, 'VOL-16', 'owned', 204, 216, 'downloaded', 'V16')"
        ),
        {"s": series_id},
    )
    await session.commit()
    return int(series_id)


async def _run(session, monkeypatch, series_id, books, provider):
    monkeypatch.setattr(progress_push, "from_settings", lambda: FakeKomgaClient(books))
    monkeypatch.setattr(progress_push, "get_source", lambda p: provider)

    async def token(session, p):
        return "t"

    monkeypatch.setattr(progress_push, "access_token_for", token)
    await repo.enqueue(session, JobType.PROGRESS_PUSH, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.PROGRESS_PUSH)])
    await session.commit()
    await progress_push.handle(JobContext(session=session, job=job))
    await session.commit()


async def _entry(session):
    return (
        await session.execute(
            text("select user_progress_chapter, user_progress_volume from list_entry")
        )
    ).one()


async def test_a_finished_volume_alone_pushes(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, 16)]
        assert tuple(await _entry(session)) == (216, 16)


async def test_a_list_already_past_the_volume_gets_no_volume(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_volume=20)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, None)]


async def test_a_volume_only_move_sends_the_current_chapter(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_chapter=300, progress_volume=3)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 300, 16)]


async def test_the_volume_is_capped_at_the_lists_total(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session, total_volumes=12)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, 12)]


async def test_a_refused_volume_is_retried_without_it(monkeypatch):
    provider = RecordingProvider(refuse_volume=True)
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _run(session, monkeypatch, series_id, [_book("V16")], provider)
        assert provider.calls == [("L1", 216, None)]
        assert tuple(await _entry(session)) == (216, None)


async def test_nothing_read_sends_nothing(monkeypatch):
    provider = RecordingProvider()
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _run(session, monkeypatch, series_id, [_book("V16", completed=False)], provider)
        assert provider.calls == []
```

The `local` provider is a push target with no token, as `entries_of` shows. If `entries_of` excludes `local` in this branch, use a `mal` entry and insert a `provider_token` row for `mal` in `_series`; read `entries_of` first. If `progress_push` imports `from_settings`, `get_source` or `access_token_for` under other names, patch those.

- [ ] **Step 2: Run it.** Expected: FAIL. `test_a_finished_volume_alone_pushes` returns early ("nothing marked read in komga") with no calls, and the others fail the same way.

- [ ] **Step 3: Implement.** In `progress_push.py`:

1. Imports: `from decimal import Decimal` (if missing); `from app.handlers.volume_progress import VolumeRow, furthest_volume, pushable_volume`; `from app.providers.base import WriteRefused`.
2. Add:

```python
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
```

3. In `entries_of`, add `e.user_progress_volume, e.total_volumes` to the select.
4. In `handle`, replace everything from `furthest = highest_completed(books, numbers)` to the end of the entry loop with:

```python
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
            await ctx.log(
                f"{provider} refused volume {volume}, sent chapter only", level="warning"
            )
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
```

Keep the existing `if pushed: progress_events.record(...)` block and the final log line after the loop unchanged.

- [ ] **Step 5: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_volume_progress_push.py tests/test_progress_push.py tests/test_komga_completed.py tests/test_komga_list_progress.py tests/test_progress_events.py -q`, then ruff. Expected: PASS. The existing comic tests are unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/handlers/progress_push.py backend/tests/test_volume_progress_push.py
git commit -m "feat(progress): push volumes read from Komga, beside chapters"
```

---

### Task 5: Komga catches up with the lists' volumes

**Files:**
- Modify: `backend/app/handlers/komga_scan.py` (`mark_read_up_to_lists`)
- Test: `backend/tests/test_volume_progress_push.py` (append)

**Interfaces:**
- Consumes: `list_entry.user_progress_volume` (Task 2); `volume.komga_book_id`.

- [ ] **Step 1: Write the failing test.** Append:

```python
from app.handlers.komga_scan import mark_read_up_to_lists


class MarkingClient:
    def __init__(self):
        self.marked: list[str] = []

    async def set_read_progress(self, book_id, *, page, completed):
        self.marked.append(book_id)


async def test_volume_books_the_lists_count_as_read_are_marked(monkeypatch):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_volume=16)
        await session.execute(
            text(
                "insert into volume (series_id, number, source_volume_id, status, state,"
                " komga_book_id) values (:s, 17, 'VOL-17', 'owned', 'downloaded', 'V17')"
            ),
            {"s": series_id},
        )
        await session.commit()
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=[str(JobType.KOMGA_SCAN)])
        await session.commit()
        client = MarkingClient()
        books = [_book("V16", completed=False), _book("V17", completed=False)]
        await mark_read_up_to_lists(JobContext(session=session, job=job), client, series_id, books)
        assert client.marked == ["V16"]
```

Move the import to the module top.

- [ ] **Step 2: Run it.** Expected: FAIL, `[] == ['V16']`. Today only chapter books are considered, and with no chapter progress it returns 0 early.

- [ ] **Step 3: Implement.** In `mark_read_up_to_lists`, replace the early return and the `behind` query with:

```python
    furthest = await progress_events.furthest_read(ctx.session, series_id)
    volume_read = (
        await ctx.session.execute(
            text("select max(user_progress_volume) from list_entry where series_id = :s"),
            {"s": series_id},
        )
    ).scalar_one()
    if furthest <= 0 and not volume_read:
        return 0
    result = await ctx.session.execute(
        text(
            """
            select komga_book_id from chapter
             where series_id = :s and komga_book_id is not null and number <= :furthest
            union
            select komga_book_id from volume
             where series_id = :s and komga_book_id is not null
               and number <= cast(:volume as integer)
            """
        ),
        {"s": series_id, "furthest": furthest, "volume": volume_read},
    )
    behind = {row[0] for row in result.all()}
```

Then extend the docstring with one sentence: "Volume books follow the lists' volume count the same way."

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_volume_progress_push.py tests/test_komga_completed.py tests/test_komga_volumes.py -q`, then ruff. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/komga_scan.py backend/tests/test_volume_progress_push.py
git commit -m "feat(komga): mark volume books read up to the lists' volume count"
```

---

### Task 6: Show the lists' volume counts

**Files:**
- Modify: `backend/app/api/routes_series.py` (`series_detail` entries), `frontend/src/lib/api.ts` (`SeriesEntry`), `frontend/src/features/series/SyncTargets.tsx`
- Test: `backend/tests/test_volume_progress_push.py` (append)

**Interfaces:**
- Produces: each entry in `GET /api/series/{id}` carries `"user_progress_volume": int | null`.

- [ ] **Step 1: Write the failing test.** Append:

```python
from httpx import ASGITransport, AsyncClient

from app.api.main import app


async def test_series_detail_entries_carry_the_volume_count():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, progress_volume=16)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        detail = (await http.get(f"/api/series/{series_id}")).json()
    assert detail["entries"][0]["user_progress_volume"] == 16
```

Move the imports to the top.

- [ ] **Step 2: Run it.** Expected: FAIL, `KeyError: 'user_progress_volume'`.

- [ ] **Step 3: Implement.**
  - In `series_detail`, add `e.user_progress_volume` to the entries select, and `"user_progress_volume": e.user_progress_volume` to each entry dict.
  - In `api.ts` `SeriesEntry`, add:

    ```ts
      /** Volumes read as the list records them. Null when the list never said. */
      user_progress_volume: number | null
    ```

  - In `SyncTargets.tsx`, after `Ch {formatChapter(entry.user_progress_chapter)}`, add:

    ```tsx
                      {entry.user_progress_volume ? <> · Vol {entry.user_progress_volume}</> : null}
    ```

- [ ] **Step 4: Run it.** `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_volume_progress_push.py tests/test_series_detail_links.py -q`, ruff, then `npm run build` from `frontend/`. Expected: PASS and build ok; no new class was added.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_series.py backend/tests/test_volume_progress_push.py frontend/src/lib/api.ts frontend/src/features/series/SyncTargets.tsx
git commit -m "feat(web): show each list's volumes read beside its chapters"
```

---

### Task 7: Documentation

- [ ] **Step 1: Write.**
  - `docs/features.md`, in the J-Novel Club section: reading a volume in Komga, either its book or every part of an owned volume, moves volumes read on MyAnimeList, AniList and MangaBaka. Chapters move to the volume's last part. Never backwards, and capped at the list's own volume count. A list that refuses the volume still gets the chapter.
  - `docs/data-model.md`, in `list_entry`: `user_progress_volume` and `total_volumes` (MyAnimeList's 0 is stored as null).
- [ ] **Step 2: Commit.** `git add docs/features.md docs/data-model.md && git commit -m "docs: describe volume progress to the reading lists"`

---

### Task 8: Full checks, then the live check with the user's go-ahead

- [ ] **Step 1:** Run the full suite on a new database:
  - `docker run -d --name manga-pg-vp-fresh -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5435:5432 postgres:17-alpine`
  - From `backend/`: `POSTGRES_HOST=localhost POSTGRES_PORT=5435 .venv/bin/python -m pytest tests -q`, then ruff.
  - From `frontend/`: `npm run build`.

  All must pass.
- [ ] **Step 2: Stop and ask the user.** Then:
  1. Back up the live database into `data/backups/`.
  2. Rebuild and recreate `api`, `worker`, `worker-download` and `web` (applies 0024).
  3. Run a list sync for MyAnimeList, AniList and MangaBaka through the app.
  4. Check that the light-novel entries now have `total_volumes` and `user_progress_volume` filled. This is a read only.
  5. Report that a real volume push stays unverified until an owned volume is finished in Komga.
