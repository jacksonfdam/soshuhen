# Web Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read any chapter in the browser, including ones not yet downloaded. Streamed pages become the download, the page position is kept for resuming, and finishing a chapter moves the lists and Komga forward.

**Architecture:**
- **Serving pages.** A new `/api/reader` router serves a chapter from its CBZ when it is in the library. Otherwise it fetches the page from the source through a filesystem cache (`reader-cache` volume).
- **Turning the cache into an archive.** When the cache holds every page, `api` queues `download_chapter{from_cache: true}`. The `worker-download` lane then builds the CBZ from the cache without touching the network, so it stays the only writer of the library.
- **Interface.** The React reader is a full-screen route outside `AppShell`. It has two chromes split at `xl` (tablet after Mihon, desktop after MangaDex) and four reading modes.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, Alembic, pytest-asyncio against a real Postgres, httpx; React 19, react-router 7, Tailwind 3, TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-13-web-reader-design.md`

## Global Constraints

- Backend tests run as `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest …` from `backend/`. The suite migrates the database itself (`tests/conftest.py`).
- Lint: `.venv/bin/python -m ruff check app/ tests/` must pass at the end of every backend task.
- `providers/`, `sources/`, `downloader/`, `komga/` and the new `app/reader/` never touch the database. DB reads and writes for the reader live in `app/api/reader_service.py` and `app/handlers/reader_cache.py`.
- `sources/` never imports from `downloader/`.
- asyncpg cannot type a null parameter: write `cast(:x as text) is null`, never `:x is null`.
- `chapter.state` and `progress_event.source` are `String(20)` columns, not Postgres enums. New values need no migration of the type.
- Frontend: no hex, px or rem literal outside `frontend/tailwind.config.ts`. No class name built by string interpolation; use a static lookup map. Opacity modifiers off the scale need brackets (`/[0.12]`). After every frontend task, `npm run build` passes and every new class is found by `grep` in `frontend/dist/assets/*.css`.
- Feature folders never import from each other. Shared pieces go in `ui/` or `lib/`.
- No screen renders a number the API does not serve.
- Comments say why a line exists, never what it does.
- Commits: English, one focused change each, no assistant attribution of any kind (user's global rule overrides the default trailer).
- Page indexes are zero-based everywhere: API path, `reading_position.page`, `?page=` in the reader URL. Only the label shown to a person adds one.

## Review Focus

1. **Fractional chapter numbers.** Finishing Ch. 23.5 must write 23 to the lists, never 24 or 23.5. Covered by Task 6, `test_a_fractional_chapter_completes_its_whole_number`.
2. **Two requests racing for the last page.** Two tabs, or a preload racing a page turn, must queue exactly one assembly job. Covered by Task 4, `test_the_last_cached_page_queues_exactly_one_assembly`.
3. **Archives not written by Soshuhen.** Komga-adopted files have `Page 2.jpg` / `Page 10.jpg` names, folders and `ComicInfo.xml`. Pages must come out in natural order, images only. Covered by Task 2, `test_page_names_are_images_in_natural_order`.
4. **A chapter downloaded while it is being read.** Once `file_path` exists the reader must serve from the archive. An assembly job finding the archive already there must only clear the cache. Covered by Task 4, `test_a_chapter_that_reaches_the_library_is_served_from_the_archive`, and Task 7, `test_assembly_of_a_chapter_already_in_the_library_only_clears_the_cache`.
5. **A page list that goes stale mid-reading.** A list stored hours ago can name pages a CDN no longer serves. A 404 re-lists once, then fails the page, never the chapter. Covered by Task 4, `test_a_stale_page_list_is_fetched_again_once`.

## Spec corrections made while planning

These were found while reading the code. The spec is updated in Task 1 so the two agree.

1. **Per-site limit.** Only `worker-download` uses `source_semaphore` today, and a download batch holds its slot for the whole batch. A shared Postgres limit would have let two batches lock the reader out for minutes. Instead the reader gets **one slot of its own per site**, in-process in `api` (`reader_semaphore`), so a site sees at most `per_source_concurrency + 1`. There is no Postgres advisory lock.
2. **Cache cleanup.** The cleanup runs in `worker-download`'s existing reclaim loop, which is the only worker that mounts the cache. There is no new cron entry or job type.
3. **Komga convergence.** `komga_scan` marks every indexed book whose chapter is at or below the series' furthest list progress as read in Komga. This covers chapters read in Soshuhen before Komga indexed them, and chapters read in Mihon too. `progress_event.source = reader` is still recorded, for the stats.
4. **Streaming indicator.** A job progress tick on the SSE stream carries no chapter id, so "saving 12/40" would be an invented number. The reader states that the chapter is streamed and will be saved once every page has loaded, with no count.
5. **Long strip.** Long strip uses native lazy image loading rather than virtualisation.
6. **Two routes the spec did not name.**
   - `GET /api/reader/series/{id}/resume` serves *Continue reading*.
   - `PUT /api/reader/defaults` writes the global default from the settings panel.
7. **`api` runs as `PUID:PGID`.** It writes files that `worker-download` then deletes. The image creates `/reader-cache` world-writable so a fresh named volume inherits that.

---

## File Structure

**Backend — create**

| Path | Responsibility |
|---|---|
| `backend/alembic/versions/0018_reader.py` | `reading_position`, `series_reader_pref`, `chapter_page_list` |
| `backend/app/reader/__init__.py` | Package marker |
| `backend/app/reader/archive.py` | Read page N out of a CBZ (pure) |
| `backend/app/reader/cache.py` | Filesystem page cache: write, find, count, read all, remove, stale (pure) |
| `backend/app/reader/pages.py` | `PageRef` ⇄ JSON (pure) |
| `backend/app/handlers/reader_cache.py` | Stored page list read/write, cache pruning (DB) |
| `backend/app/handlers/komga_read_progress.py` | Job: mark one Komga book read |
| `backend/app/api/progress_queue.py` | `chapter_ceiling`, `progress_bounds`, `queue_progress_write` shared by two routers |
| `backend/app/api/reader_service.py` | Chapter lookup, page serving, assembly trigger, prefs, position |
| `backend/app/api/routes_reader.py` | HTTP surface of the reader |
| `backend/tests/test_reader_units.py` | archive, cache, pages, reader slot |
| `backend/tests/test_reader_api.py` | Reader routes against Postgres and a stub source |
| `backend/tests/test_reader_progress.py` | Completion, progress_write source, Komga job |
| `backend/tests/test_reader_cache_prune.py` | Cleanup of abandoned caches |
| `backend/tests/test_komga_list_progress.py` | `komga_scan` convergence |

**Backend — modify**

| Path | Change |
|---|---|
| `backend/app/enums.py` | `ChapterState.STREAMING`, `ProgressSource.READER`, `JobType.KOMGA_READ_PROGRESS` |
| `backend/app/models.py` | three models |
| `backend/app/config.py` | `reader_cache_path` |
| `backend/app/settings_store.py` | three `reader_default_*` keys |
| `backend/app/downloader/limits.py` | `reader_semaphore` |
| `backend/app/api/main.py` | include reader router |
| `backend/app/api/routes_series.py` | use `progress_queue`; detail chapters carry `id` |
| `backend/app/handlers/progress_write.py` | progress source from payload |
| `backend/app/handlers/download_chapter.py` | `from_cache` path |
| `backend/app/handlers/download_batch.py` | skip `streaming` chapters |
| `backend/app/handlers/komga_scan.py` | mark books read up to list progress |
| `backend/app/worker/main.py` | import new handlers |
| `backend/app/worker/runner.py` | prune cache in reclaim loop |
| `backend/Dockerfile` | create `/reader-cache` |
| `docker-compose.yml` | volume, `api` user and mounts |

**Frontend — create** (`frontend/src/features/reader/`)

| Path | Responsibility |
|---|---|
| `ReaderPage.tsx` | Route `/read/:chapterId`: owns manifest, page, prefs, panels |
| `ResumePage.tsx` | Route `/read/series/:seriesId`: asks where to resume, redirects |
| `ReaderMessage.tsx` | Full-screen message (loading, failure, nothing to read) |
| `PageImage.tsx` | One page `<img>` with a retry placeholder |
| `PagedView.tsx` | Paged LTR, RTL, double, with tap zones |
| `StripView.tsx` | Long strip, current page by `IntersectionObserver` |
| `EndOfChapter.tsx` | Transition to the next chapter |
| `TabletChrome.tsx` | Chrome below `xl` |
| `DesktopChrome.tsx` | Chrome at `xl` and above |
| `PageSlider.tsx` | Range input with page labels |
| `ReaderSheet.tsx` | Bottom sheet below `xl`, centred modal at `xl` |
| `SettingsPanel.tsx` | Layout / Image tabs |
| `ChapterPanel.tsx` | Chapter list |
| `lib/spreads.ts` | Page grouping per mode (pure) |
| `lib/useReaderKeys.ts` | Keyboard |
| `lib/usePreload.ts` | Image preloading |
| `lib/usePositionSaver.ts` | Debounced position save |
| `lib/styles.ts` | Static class maps for background and scale |

**Frontend — modify**

| Path | Change |
|---|---|
| `frontend/tailwind.config.ts` | `reader-black`, `reader-gray`, `reader-white` |
| `frontend/src/ui/Icon.tsx` | `arrow_back`, `chevron_left`, `chevron_right`, `fullscreen`, `close`, `home` |
| `frontend/src/lib/api.ts` | reader types and endpoints, `SeriesChapter.id` |
| `frontend/src/app/routes.tsx` | two routes outside the shell |
| `frontend/src/features/series/ChapterTable.tsx` | **Read** opens the reader |
| `frontend/src/features/home/ContinueReading.tsx` | **Continue** opens the reader |

The library's `ContinueReading` row is one `<Link>` around the whole card. A second link inside it would be invalid markup, so it keeps opening the series page, where **Read** is one click away.

**Docs — modify:** `docs/features.md`, `docs/configuration.md`, `docs/data-model.md`, `docs/architecture.md`, `docs/jobs.md`, `CLAUDE.md`, and the spec.

---

### Task 1: Schema, enums, settings and spec corrections

**Files:**
- Create: `backend/alembic/versions/0018_reader.py`
- Modify: `backend/app/enums.py`, `backend/app/models.py`, `backend/app/config.py`, `backend/app/settings_store.py`, `docs/superpowers/specs/2026-10-13-web-reader-design.md`
- Test: `backend/tests/test_reader_units.py` (created here, grown in Tasks 2–3)

**Interfaces:**
- Produces:
  - `ChapterState.STREAMING = "streaming"`, `ProgressSource.READER = "reader"`, `JobType.KOMGA_READ_PROGRESS = "komga_read_progress"`. The new job type falls in the fetch lane by omission.
  - Models `ReadingPosition`, `SeriesReaderPref`, `ChapterPageList`.
  - `Settings.reader_cache_path: Path = Path("/reader-cache")`.
  - `settings_store.READER_DEFAULT_MODE`, `READER_DEFAULT_SCALE`, `READER_DEFAULT_BACKGROUND`, with defaults `"paged_rtl"`, `"fit_screen"` and `"black"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_reader_units.py`:

```python
"""The reader's pure pieces and the schema they rest on."""

import pytest
from sqlalchemy import text

from app import settings_store
from app.db import get_sessionmaker
from app.enums import ChapterState, JobType, Lane, ProgressSource, lane_of

pytestmark = pytest.mark.asyncio


async def test_the_reader_tables_exist():
    async with get_sessionmaker()() as session:
        for table in ("reading_position", "series_reader_pref", "chapter_page_list"):
            found = await session.execute(
                text("select to_regclass(:name) is not null"), {"name": table}
            )
            assert found.scalar_one(), table


async def test_the_new_states_and_job_are_named():
    assert ChapterState.STREAMING == "streaming"
    assert ProgressSource.READER == "reader"
    # A short write to Komga; it must never wait behind archives.
    assert lane_of(JobType.KOMGA_READ_PROGRESS) is Lane.FETCH


async def test_reader_defaults_have_packaged_values():
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from setting where key like 'reader_default_%'"))
        await session.commit()
        assert await settings_store.get(session, settings_store.READER_DEFAULT_MODE) == "paged_rtl"
        assert await settings_store.get(session, settings_store.READER_DEFAULT_SCALE) == "fit_screen"
        assert (
            await settings_store.get(session, settings_store.READER_DEFAULT_BACKGROUND) == "black"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_units.py -q`
Expected: FAIL. `ImportError` on `ChapterState.STREAMING`, or `AttributeError` on `READER_DEFAULT_MODE`.

- [ ] **Step 3: Enums**

In `backend/app/enums.py`, add to `ChapterState` after `SKIPPED`:

```python
    #: Pages are arriving in the reader cache because someone is reading it.
    #: Batches leave it alone so the source is not asked for it twice.
    STREAMING = "streaming"
```

Add to `JobType` after `NOTES_WRITE`:

```python
    KOMGA_READ_PROGRESS = "komga_read_progress"
```

Add to `ProgressSource` after `MANUAL`:

```python
    READER = "reader"
```

- [ ] **Step 4: Models**

In `backend/app/models.py`, append:

```python
class ReadingPosition(Base):
    """Where reading stands inside a chapter, kept by this installation only.

    Apart from list_entry.user_progress_chapter on purpose: that column is a
    list's view of progress and every sync overwrites it, and no list holds a
    page number.
    """

    __tablename__ = "reading_position"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapter.id", ondelete="CASCADE"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = _now()


class SeriesReaderPref(Base):
    """How one series is shown. No row means the global default applies."""

    __tablename__ = "series_reader_pref"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    scale: Mapped[str] = mapped_column(String(20), nullable=False)
    background: Mapped[str] = mapped_column(String(20), nullable=False)


class ChapterPageList(Base):
    """A streamed chapter's page list, kept so a restart of `api` does not
    spend the rate limit asking for it again."""

    __tablename__ = "chapter_page_list"

    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapter.id", ondelete="CASCADE"), primary_key=True
    )
    pages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = _now()
```

The spec listed a `page_count` column on `reading_position`. It is dropped: the manifest serves the page count, and a stored copy would disagree with it the first time a chapter is re-downloaded with a different count.

- [ ] **Step 5: Migration**

Create `backend/alembic/versions/0018_reader.py`:

```python
"""the reader: page position, per-series display, streamed page lists

Revision ID: 0018_reader
Revises: 0017_removed_entry
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018_reader"
down_revision: str | None = "0017_removed_entry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_position",
        sa.Column(
            "series_id",
            sa.BigInteger,
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "chapter_id",
            sa.BigInteger,
            sa.ForeignKey("chapter.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "series_reader_pref",
        sa.Column(
            "series_id",
            sa.BigInteger,
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("scale", sa.String(20), nullable=False),
        sa.Column("background", sa.String(20), nullable=False),
    )
    op.create_table(
        "chapter_page_list",
        sa.Column(
            "chapter_id",
            sa.BigInteger,
            sa.ForeignKey("chapter.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pages", JSONB, nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("chapter_page_list")
    op.drop_table("series_reader_pref")
    op.drop_table("reading_position")
```

Check the type of `series.id` and `chapter.id` in an earlier migration with `grep -n "BigInteger" backend/alembic/versions/0001*`. If they were created as `sa.Integer`, use `sa.Integer` for the foreign keys too.

- [ ] **Step 6: Config and settings**

In `backend/app/config.py`, under `library_path`:

```python
    # Pages a reader streamed before the chapter was downloaded. Written by
    # `api`, turned into an archive and emptied by `worker-download`.
    reader_cache_path: Path = Path("/reader-cache")
```

In `backend/app/settings_store.py`:
- Add the constants after `MANGAFIRE_WAF_PASS`:

```python
READER_DEFAULT_MODE = "reader_default_mode"
READER_DEFAULT_SCALE = "reader_default_scale"
READER_DEFAULT_BACKGROUND = "reader_default_background"
```

- Add fields to `Defaults` after `mangafire_waf_pass`:

```python
    # Right to left because most of what this library holds is manga; a
    # webtoon is one tap away and remembered per series after that.
    reader_default_mode: str = "paged_rtl"
    reader_default_scale: str = "fit_screen"
    reader_default_background: str = "black"
```

- Add cases to `_fallback` before `case _`:

```python
        case k if k == READER_DEFAULT_MODE:
            return DEFAULTS.reader_default_mode
        case k if k == READER_DEFAULT_SCALE:
            return DEFAULTS.reader_default_scale
        case k if k == READER_DEFAULT_BACKGROUND:
            return DEFAULTS.reader_default_background
```

Do not add them to `all_settings`. The Settings screen renders that list, and these belong to the reader's own panel.

- [ ] **Step 7: Correct the spec**

In `docs/superpowers/specs/2026-10-13-web-reader-design.md`, apply the seven corrections listed under "Spec corrections made while planning" above:
- Replace the section "A per-site limit shared across processes" with a section "A reader slot per site", stating correction 1.
- In "From the cache to the library":
  - Replace the "Abandoned chapters" paragraph with correction 2.
  - Replace the mount table with: `api` read-write as `PUID:PGID`; `worker-download` read-write.
- In "Finishing a chapter", replace the sentence about `komga_scan` and `progress_event` with correction 3.
- In "Behaviour", replace the streaming indicator bullet with correction 4.
- In "Structure", replace `StripView`'s description with correction 5.
- In the API table, add the two routes from correction 6.
- In "Data model", remove `page_count` from `reading_position`.

- [ ] **Step 8: Run test to verify it passes**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_units.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: 3 passed, ruff clean.

- [ ] **Step 9: Commit**

```bash
git add backend/alembic/versions/0018_reader.py backend/app/enums.py backend/app/models.py \
  backend/app/config.py backend/app/settings_store.py backend/tests/test_reader_units.py \
  docs/superpowers/specs/2026-10-13-web-reader-design.md
git commit -m "feat(reader): schema for page position, display preferences and page lists"
```

---

### Task 2: Reading archives and the page cache

**Files:**
- Create: `backend/app/reader/__init__.py` (empty), `backend/app/reader/archive.py`, `backend/app/reader/cache.py`
- Test: `backend/tests/test_reader_units.py`

**Interfaces:**
- Produces:
  - `archive.page_names(path: Path) -> list[str]`
  - `archive.read_page(path: Path, index: int) -> tuple[bytes, str]`, which raises `IndexError`
  - `archive.inside(path: Path, root: Path) -> bool`
  - `cache.write_page(root: Path, chapter_id: int, index: int, data: bytes) -> Path`
  - `cache.find_page(root, chapter_id, index) -> Path | None`
  - `cache.cached_count(root, chapter_id) -> int`
  - `cache.read_all(root, chapter_id, page_count) -> list[bytes | None]`
  - `cache.remove(root, chapter_id) -> None`
  - `cache.stale_chapters(root: Path, max_age_seconds: float, *, now: float | None = None) -> list[int]`
  - `cache.touch(root, chapter_id) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_reader_units.py`:

```python
import os
import time
import zipfile

from app.reader import archive, cache

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _cbz(path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_page_names_are_images_in_natural_order(tmp_path):
    """Komga-adopted archives were not written by us: `Page 10` must not sort
    before `Page 2`, and ComicInfo.xml or a folder entry is not a page."""
    path = _cbz(
        tmp_path / "c.cbz",
        {
            "ComicInfo.xml": b"<x/>",
            "pages/": b"",
            "pages/Page 10.jpg": JPEG + b"10",
            "pages/Page 2.jpg": JPEG + b"2",
            "pages/Page 1.png": PNG,
        },
    )
    assert archive.page_names(path) == ["pages/Page 1.png", "pages/Page 2.jpg", "pages/Page 10.jpg"]


def test_read_page_returns_bytes_and_their_real_format(tmp_path):
    path = _cbz(tmp_path / "c.cbz", {"001.jpg": JPEG, "002.jpg": PNG})
    data, extension = archive.read_page(path, 1)
    assert data == PNG
    # The extension comes from the bytes, not the member name.
    assert extension == "png"


def test_read_page_past_the_end_raises_index_error(tmp_path):
    path = _cbz(tmp_path / "c.cbz", {"001.jpg": JPEG})
    with pytest.raises(IndexError):
        archive.read_page(path, 1)


def test_inside_refuses_a_path_outside_the_library(tmp_path):
    library = tmp_path / "manga"
    library.mkdir()
    assert archive.inside(library / "a" / "b.cbz", library)
    assert not archive.inside(tmp_path / "elsewhere.cbz", library)
    assert not archive.inside(library / ".." / "elsewhere.cbz", library)


def test_cache_writes_finds_counts_and_reads_back(tmp_path):
    cache.write_page(tmp_path, 7, 0, JPEG)
    cache.write_page(tmp_path, 7, 2, PNG)
    assert cache.find_page(tmp_path, 7, 0).name == "000.jpg"
    assert cache.find_page(tmp_path, 7, 1) is None
    assert cache.cached_count(tmp_path, 7) == 2
    assert cache.read_all(tmp_path, 7, 3) == [JPEG, None, PNG]


def test_cache_counts_nothing_for_a_chapter_never_streamed(tmp_path):
    assert cache.cached_count(tmp_path, 99) == 0


def test_a_half_written_page_is_neither_found_nor_counted(tmp_path):
    directory = tmp_path / "7"
    directory.mkdir()
    (directory / "tmpabc.part").write_bytes(JPEG[:3])
    assert cache.cached_count(tmp_path, 7) == 0
    assert cache.find_page(tmp_path, 7, 0) is None


def test_remove_deletes_the_chapter_directory(tmp_path):
    cache.write_page(tmp_path, 7, 0, JPEG)
    cache.remove(tmp_path, 7)
    assert not (tmp_path / "7").exists()
    cache.remove(tmp_path, 7)  # Removing twice is not an error.


def test_stale_chapters_are_judged_by_their_newest_page(tmp_path):
    now = time.time()
    cache.write_page(tmp_path, 1, 0, JPEG)
    cache.write_page(tmp_path, 2, 0, JPEG)
    old = now - 8 * 86400
    for path in [tmp_path / "1", *(tmp_path / "1").iterdir()]:
        os.utime(path, (old, old))
    (tmp_path / "not-a-chapter").mkdir()
    assert cache.stale_chapters(tmp_path, 7 * 86400, now=now) == [1]


def test_stale_chapters_of_a_missing_root_is_empty(tmp_path):
    assert cache.stale_chapters(tmp_path / "absent", 1) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_units.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.reader'`.

- [ ] **Step 3: Implement `archive.py`**

Create `backend/app/reader/__init__.py` empty, and `backend/app/reader/archive.py`:

```python
"""Pages read straight out of a chapter archive already in the library.

Values in, values out: this takes a path and returns bytes, and never learns
which chapter the path belongs to.
"""

import re
import zipfile
from pathlib import Path

from app.downloader.cbz import page_extension

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")


def _natural(name: str) -> list[object]:
    # Archives Komga adopted were written by other tools, and plain sorting
    # puts "Page 10" before "Page 2".
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def page_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and name.lower().endswith(_IMAGE_SUFFIXES)
        ]
    return sorted(names, key=_natural)


def read_page(path: Path, index: int) -> tuple[bytes, str]:
    names = page_names(path)
    if not 0 <= index < len(names):
        raise IndexError(index)
    with zipfile.ZipFile(path) as archive:
        data = archive.read(names[index])
    return data, page_extension(data)


def inside(path: Path, root: Path) -> bool:
    """Whether a stored file path really points into the library.

    file_path is ours rather than the visitor's, but it is also what Komga
    reported, and serving whatever a row names is how a bad row becomes a file
    read anywhere on the host.
    """
    return path.resolve().is_relative_to(root.resolve())
```

- [ ] **Step 4: Implement `cache.py`**

Create `backend/app/reader/cache.py`:

```python
"""Where a streamed chapter's pages wait to become an archive.

One directory per chapter id, one file per page named by its index. Pages are
written to a scratch file and renamed into place, so the worker that builds
the archive never reads half a page.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from app.downloader.cbz import page_extension

_SCRATCH = ".part"


def chapter_dir(root: Path, chapter_id: int) -> Path:
    return root / str(chapter_id)


def write_page(root: Path, chapter_id: int, index: int, data: bytes) -> Path:
    directory = chapter_dir(root, chapter_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{index:03d}.{page_extension(data)}"
    handle, scratch = tempfile.mkstemp(dir=directory, suffix=_SCRATCH)
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    os.replace(scratch, destination)
    return destination


def find_page(root: Path, chapter_id: int, index: int) -> Path | None:
    directory = chapter_dir(root, chapter_id)
    if not directory.is_dir():
        return None
    for candidate in directory.glob(f"{index:03d}.*"):
        if not candidate.name.endswith(_SCRATCH):
            return candidate
    return None


def cached_count(root: Path, chapter_id: int) -> int:
    directory = chapter_dir(root, chapter_id)
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if not path.name.endswith(_SCRATCH))


def read_all(root: Path, chapter_id: int, page_count: int) -> list[bytes | None]:
    pages: list[bytes | None] = []
    for index in range(page_count):
        found = find_page(root, chapter_id, index)
        pages.append(found.read_bytes() if found is not None else None)
    return pages


def touch(root: Path, chapter_id: int) -> None:
    """A page served from the cache is still a chapter being read."""
    directory = chapter_dir(root, chapter_id)
    if directory.is_dir():
        os.utime(directory)


def remove(root: Path, chapter_id: int) -> None:
    shutil.rmtree(chapter_dir(root, chapter_id), ignore_errors=True)


def stale_chapters(root: Path, max_age_seconds: float, *, now: float | None = None) -> list[int]:
    """Chapters nobody has read from for longer than `max_age_seconds`.

    Judged by the newest file rather than the directory alone: writing a page
    updates the directory, but reading one back from the cache does not, and
    `touch` is what covers that case.
    """
    if not root.is_dir():
        return []
    current = time.time() if now is None else now
    stale: list[int] = []
    for directory in root.iterdir():
        if not directory.is_dir() or not directory.name.isdigit():
            continue
        newest = max(
            [directory.stat().st_mtime, *(path.stat().st_mtime for path in directory.iterdir())]
        )
        if current - newest > max_age_seconds:
            stale.append(int(directory.name))
    return sorted(stale)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_units.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/reader backend/tests/test_reader_units.py
git commit -m "feat(reader): read pages out of an archive and keep streamed pages in a cache"
```

---

### Task 3: Page list serialisation and the reader's own slot

**Files:**
- Create: `backend/app/reader/pages.py`, `backend/app/handlers/reader_cache.py`
- Modify: `backend/app/downloader/limits.py`
- Test: `backend/tests/test_reader_units.py`

**Interfaces:**
- Produces:
  - `pages.dump(pages: list[PageRef]) -> list[dict]`
  - `pages.load(raw: list[dict]) -> list[PageRef]`
  - `limits.reader_semaphore(site: str) -> asyncio.Semaphore`, with one slot per site, separate from `source_semaphore(site, n)`
  - `reader_cache.stored_page_list(session, chapter_id) -> list[PageRef] | None`
  - `reader_cache.store_page_list(session, chapter_id, pages) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_reader_units.py`:

```python
from app.downloader.limits import reader_semaphore, source_semaphore
from app.handlers import reader_cache
from app.reader import pages as page_json
from app.sources.base import PageRef


def test_page_refs_round_trip_through_json():
    original = [PageRef(url="https://a/1.jpg", headers={"Referer": "https://a/"}), PageRef(url="/2.jpg")]
    assert page_json.load(page_json.dump(original)) == original


async def test_the_reader_has_one_slot_of_its_own_per_site():
    """A download batch holds its slot for the whole batch; sharing those would
    leave someone staring at a blank page for minutes."""
    reader = await reader_semaphore("site-a")
    assert reader is await reader_semaphore("site-a")
    assert reader is not await source_semaphore("site-a", 2)
    assert reader._value == 1


async def test_a_stored_page_list_round_trips():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', 's-pages', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text("insert into chapter (series_id, number) values (:s, 1) returning id"),
                {"s": series_id},
            )
        ).scalar_one()
        assert await reader_cache.stored_page_list(session, chapter_id) is None

        listed = [PageRef(url="/1.jpg"), PageRef(url="/2.jpg", headers={"Referer": "x"})]
        await reader_cache.store_page_list(session, chapter_id, listed)
        await reader_cache.store_page_list(session, chapter_id, listed[:1])
        await session.commit()

        assert await reader_cache.stored_page_list(session, chapter_id) == listed[:1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_units.py -q`
Expected: FAIL with `ImportError: cannot import name 'reader_semaphore'`.

- [ ] **Step 3: Implement**

Create `backend/app/reader/pages.py`:

```python
"""PageRef to and from what the database stores."""

from typing import Any

from app.sources.base import PageRef


def dump(pages: list[PageRef]) -> list[dict[str, Any]]:
    return [{"url": page.url, "headers": dict(page.headers)} for page in pages]


def load(raw: list[dict[str, Any]]) -> list[PageRef]:
    return [PageRef(url=item["url"], headers=dict(item.get("headers") or {})) for item in raw]
```

Append to `backend/app/downloader/limits.py`:

```python
# One request at a time per site for the reader, apart from the downloads'
# slots. A download batch holds its slot for every chapter in it, so a reader
# waiting in the same queue would wait minutes for a page. The site sees at
# most per_source_concurrency + 1, which is a person reading on top of the
# backlog, not a second backlog.
READER_SLOTS = 1


async def reader_semaphore(site: str) -> asyncio.Semaphore:
    return await source_semaphore(f"reader:{site}", READER_SLOTS)
```

Create `backend/app/handlers/reader_cache.py`:

```python
"""The database side of the reader cache, shared by `api` and the download lane."""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.reader import pages as page_json
from app.sources.base import PageRef


async def stored_page_list(session: AsyncSession, chapter_id: int) -> list[PageRef] | None:
    result = await session.execute(
        text("select pages from chapter_page_list where chapter_id = :id"), {"id": chapter_id}
    )
    raw = result.scalar_one_or_none()
    return None if raw is None else page_json.load(raw)


async def store_page_list(session: AsyncSession, chapter_id: int, pages: list[PageRef]) -> None:
    await session.execute(
        text(
            """
            insert into chapter_page_list (chapter_id, pages, fetched_at)
            values (:id, cast(:pages as jsonb), now())
            on conflict (chapter_id) do update
               set pages = excluded.pages, fetched_at = excluded.fetched_at
            """
        ),
        {"id": chapter_id, "pages": json.dumps(page_json.dump(pages))},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_units.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reader/pages.py backend/app/downloader/limits.py \
  backend/app/handlers/reader_cache.py backend/tests/test_reader_units.py
git commit -m "feat(reader): store streamed page lists and give the reader its own slot per site"
```

---

### Task 4: Serving pages — archive and stream

**Files:**
- Create: `backend/app/api/reader_service.py`, `backend/app/api/routes_reader.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_reader_api.py`

**Interfaces:**
- Consumes:
  - From Tasks 2–3: `archive.*`, `cache.*`, `reader_cache.stored_page_list` and `store_page_list`, `reader_semaphore`.
  - From `app.handlers.download_chapter`: `load_catalogue_row`.
- Produces (`app.api.reader_service`):
  - Exceptions `ChapterMissing`, `NoMapping`, `Unavailable`, `PageFailed`.
  - `ChapterRow`, a dataclass with `id, series_id, number: Decimal, title, state, file_path, komga_book_id, chapter_url, series_title, source_site`.
  - `async chapter(session, chapter_id) -> ChapterRow`
  - `archive_of(row) -> Path | None`
  - `async page_count(session, row) -> tuple[Literal["archive", "stream"], int]`
  - `async serve_page(session, row, index) -> tuple[bytes, str]`
  - `cache_root() -> Path`
- Produces (routes):
  - `GET /api/reader/chapters/{id}` returns a minimal manifest for now (`chapter`, `series`, `origin`, `page_count`). Task 5 extends it.
  - `GET /api/reader/chapters/{id}/pages/{index}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reader_api.py`:

```python
"""The reader's HTTP surface against a real database and a stub source."""

import asyncio
import zipfile
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.sources.base import ChapterUnavailable, PageRef, RegisteredSource, install_registry
from tests.test_download_chapter_handler import FakeSource, Stub, _catalogue

pytestmark = pytest.mark.asyncio

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    (tmp_path / "manga").mkdir()
    (tmp_path / "cache").mkdir()
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "manga"))
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, series, list_entry, setting restart identity cascade")
        )
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from site_catalogue where key like 'stub-%'"))
        await session.execute(text("delete from source_pref where key like 'stub-%'"))
        await session.commit()
    get_settings.cache_clear()


async def _series(session, *, site: str | None = None, slug: str = "teto") -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values ('Teto X Egen', :slug, false, '{}'::jsonb) returning id"
            ),
            {"slug": slug},
        )
    ).scalar_one()
    if site is not None:
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:s, :site, 'https://stubsite.test/manga/1', true)"
            ),
            {"s": series_id, "site": site},
        )
    await session.commit()
    return int(series_id)


async def _chapter(
    session, series_id: int, number: str, *, url: str | None = None,
    file_path: str | None = None, state: str = "known", book: str | None = None,
) -> int:
    chapter_id = (
        await session.execute(
            text(
                "insert into chapter (series_id, number, title, source_url, state, file_path,"
                " komga_book_id) values (:s, :n, :t, :url, :state, :path, :book) returning id"
            ),
            {
                "s": series_id, "n": Decimal(number), "t": f"Chapter {number}", "url": url,
                "state": state, "path": file_path, "book": book,
            },
        )
    ).scalar_one()
    await session.commit()
    return int(chapter_id)


def _cbz(path, pages: list[bytes]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for index, data in enumerate(pages, start=1):
            zf.writestr(f"{index:03d}.jpg", data)
        zf.writestr("ComicInfo.xml", b"<ComicInfo/>")
    return str(path)


async def _state(chapter_id: int) -> str:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(text("select state from chapter where id = :id"), {"id": chapter_id})
        ).scalar_one()


async def _assembly_jobs(chapter_id: int) -> int:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text(
                    "select count(*) from job where type = 'download_chapter'"
                    " and (payload->>'chapter_id')::bigint = :id"
                    " and (payload->>'from_cache')::boolean"
                ),
                {"id": chapter_id},
            )
        ).scalar_one()


class Streamed:
    """A stub site and a fake source wired into the registry and catalogue."""

    def __init__(self, router, pages_for):
        self.hits: list[str] = []

        def counting(path):
            self.hits.append(path)
            return router(path)

        self.stub = Stub(counting)
        self.chapter_url = f"{self.stub.base_url}/manga/1/chapter/1"
        self.source = FakeSource(self.stub.key, pages={self.chapter_url: pages_for})
        install_registry({self.stub.key: RegisteredSource(source=self.source, base_url=self.stub.base_url)})

    async def seed(self, session) -> tuple[int, int]:
        await _catalogue(session, self.stub.key, self.stub.base_url)
        series_id = await _series(session, site=self.stub.key)
        chapter_id = await _chapter(session, series_id, "1", url=self.chapter_url)
        return series_id, chapter_id

    def close(self):
        self.stub.close()


async def test_an_archived_chapter_serves_its_pages(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG + b"1", JPEG + b"2"])
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", file_path=path, state="downloaded")

    manifest = (await client.get(f"/api/reader/chapters/{chapter_id}")).json()
    assert manifest["origin"] == "archive"
    assert manifest["page_count"] == 2

    response = await client.get(f"/api/reader/chapters/{chapter_id}/pages/1")
    assert response.status_code == 200
    assert response.content == JPEG + b"2"
    assert response.headers["content-type"] == "image/jpeg"
    assert "immutable" in response.headers["cache-control"]


async def test_a_page_past_the_end_is_404(client, tmp_path):
    path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG])
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", file_path=path, state="downloaded")
    assert (await client.get(f"/api/reader/chapters/{chapter_id}/pages/1")).status_code == 404
    assert (await client.get(f"/api/reader/chapters/{chapter_id}/pages/-1")).status_code == 404


async def test_an_unknown_chapter_is_404(client):
    assert (await client.get("/api/reader/chapters/999999")).status_code == 404


async def test_a_streamed_page_is_fetched_once_then_served_from_the_cache(client):
    streamed = Streamed(lambda path: (200, "image/jpeg", JPEG), [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)

        manifest = (await client.get(f"/api/reader/chapters/{chapter_id}")).json()
        assert manifest["origin"] == "stream"
        assert manifest["page_count"] == 2

        first = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        second = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert first.content == second.content == JPEG
        assert streamed.hits.count("/p1.jpg") == 1
        assert await _state(chapter_id) == "streaming"
    finally:
        streamed.close()


async def test_the_last_cached_page_queues_exactly_one_assembly(client):
    streamed = Streamed(lambda path: (200, "image/jpeg", JPEG), [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert await _assembly_jobs(chapter_id) == 0

        await asyncio.gather(
            client.get(f"/api/reader/chapters/{chapter_id}/pages/1"),
            client.get(f"/api/reader/chapters/{chapter_id}/pages/1"),
        )
        assert await _assembly_jobs(chapter_id) == 1
    finally:
        streamed.close()


async def test_a_stale_page_list_is_fetched_again_once(client):
    """A list stored an hour ago can name pages the CDN no longer serves."""

    def router(path):
        return (404, "text/plain", b"gone") if path == "/old.jpg" else (200, "image/jpeg", JPEG)

    streamed = Streamed(router, [PageRef(url="/old.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        await client.get(f"/api/reader/chapters/{chapter_id}")  # stores the old list

        streamed.source._pages[streamed.chapter_url] = [PageRef(url="/new.jpg")]
        response = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")

        assert response.status_code == 200
        assert "/new.jpg" in streamed.hits
    finally:
        streamed.close()


async def test_a_page_the_source_will_not_serve_is_502(client):
    streamed = Streamed(lambda path: (403, "text/plain", b"no"), [PageRef(url="/p1.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        response = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert response.status_code == 502
    finally:
        streamed.close()


async def test_a_chapter_the_source_refuses_is_410(client):
    streamed = Streamed(lambda path: (200, "image/jpeg", JPEG), [])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        streamed.source._unavailable = {streamed.chapter_url}
        assert (await client.get(f"/api/reader/chapters/{chapter_id}")).status_code == 410
    finally:
        streamed.close()


async def test_a_chapter_with_no_mapping_and_no_file_is_409(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", url="https://nowhere.test/c/1")
    assert (await client.get(f"/api/reader/chapters/{chapter_id}")).status_code == 409


async def test_a_chapter_that_reaches_the_library_is_served_from_the_archive(client, tmp_path):
    streamed = Streamed(lambda path: (200, "image/jpeg", JPEG), [PageRef(url="/p1.jpg")])
    try:
        async with get_sessionmaker()() as session:
            _, chapter_id = await streamed.seed(session)
        await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")

        path = _cbz(tmp_path / "manga" / "teto" / "c1.cbz", [JPEG + b"archived"])
        async with get_sessionmaker()() as session:
            await session.execute(
                text("update chapter set state = 'downloaded', file_path = :p where id = :id"),
                {"p": path, "id": chapter_id},
            )
            await session.commit()

        manifest = (await client.get(f"/api/reader/chapters/{chapter_id}")).json()
        assert manifest["origin"] == "archive"
        page = await client.get(f"/api/reader/chapters/{chapter_id}/pages/0")
        assert page.content == JPEG + b"archived"
    finally:
        streamed.close()


async def test_a_file_path_outside_the_library_is_not_served(client, tmp_path):
    path = _cbz(tmp_path / "elsewhere" / "c1.cbz", [JPEG])
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        chapter_id = await _chapter(session, series_id, "1", file_path=path, state="downloaded")
    # Not in the library and no source to stream from.
    assert (await client.get(f"/api/reader/chapters/{chapter_id}")).status_code == 409
```

`FakeSource` treats `_unavailable` as a set, and the test rebinds it. Check that `FakeSource.list_pages` reads `self._unavailable` at call time; it does, per `tests/test_download_chapter_handler.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_api.py -q`
Expected: FAIL. Every request answers 404, because there is no router.

- [ ] **Step 3: Implement `reader_service.py`**

Create `backend/app/api/reader_service.py`:

```python
"""Everything the reader routes do that is not HTTP.

Kept apart from the routes so the page logic reads as one piece: which copy of
a chapter answers, how a stream falls back when its list goes stale, and when a
cache becomes a download.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.downloader.cbz import page_extension
from app.downloader.fetcher import PageFetchError, fetch_pages
from app.downloader.limits import reader_semaphore
from app.enums import JobType
from app.handlers.base import PermanentError
from app.handlers.download_chapter import load_catalogue_row
from app.handlers.reader_cache import store_page_list, stored_page_list
from app.queue import repo
from app.reader import archive, cache
from app.sources import source_for_url
from app.sources.base import ChapterUnavailable, PageRef
from app.sources.net import get_client


class ChapterMissing(LookupError):
    pass


class NoMapping(RuntimeError):
    """Not in the library, and no confirmed source to stream it from."""


class Unavailable(RuntimeError):
    """The source says the chapter is gone."""


class PageFailed(RuntimeError):
    """One page could not be fetched. The chapter may still be fine."""


@dataclass(frozen=True)
class ChapterRow:
    id: int
    series_id: int
    number: Decimal
    title: str | None
    state: str
    file_path: str | None
    komga_book_id: str | None
    chapter_url: str | None
    series_title: str
    source_site: str | None


# One page-list request per chapter at a time. A manifest and the first page
# arrive together when a chapter opens, and both would otherwise ask the
# source for the same list. Keyed by the running loop too: a lock belongs to
# the loop it first waited on, and the test suite gives every test its own.
_list_locks: dict[tuple[int, int], asyncio.Lock] = {}


def cache_root() -> Path:
    return get_settings().reader_cache_path


async def chapter(session: AsyncSession, chapter_id: int) -> ChapterRow:
    result = await session.execute(
        text(
            """
            select c.id, c.series_id, c.number, c.title, c.state, c.file_path,
                   c.komga_book_id, c.source_url as chapter_url,
                   s.canonical_title as series_title, m.source_site
              from chapter c
              join series s on s.id = c.series_id
              left join source_mapping m on m.series_id = s.id and m.active
             where c.id = :id
             order by m.confirmed_at desc nulls last
             limit 1
            """
        ),
        {"id": chapter_id},
    )
    row = result.first()
    if row is None:
        raise ChapterMissing(f"chapter {chapter_id} not found")
    return ChapterRow(**row._mapping)


def archive_of(row: ChapterRow) -> Path | None:
    if row.file_path is None:
        return None
    path = Path(row.file_path)
    if not path.is_file() or not archive.inside(path, get_settings().library_path):
        return None
    return path


async def page_count(session: AsyncSession, row: ChapterRow) -> tuple[Literal["archive", "stream"], int]:
    found = archive_of(row)
    if found is not None:
        return "archive", len(archive.page_names(found))
    return "stream", len(await page_list(session, row))


async def serve_page(session: AsyncSession, row: ChapterRow, index: int) -> tuple[bytes, str]:
    if index < 0:
        raise IndexError(index)
    found = archive_of(row)
    if found is not None:
        return archive.read_page(found, index)

    root = cache_root()
    cached = cache.find_page(root, row.id, index)
    if cached is not None:
        cache.touch(root, row.id)
        data = cached.read_bytes()
        return data, page_extension(data)

    data = await _fetch_streamed(session, row, index)
    cache.write_page(root, row.id, index, data)
    await _mark_streaming(session, row.id)
    await _queue_assembly_when_complete(session, row)
    return data, page_extension(data)


async def page_list(session: AsyncSession, row: ChapterRow, *, refresh: bool = False) -> list[PageRef]:
    key = (id(asyncio.get_running_loop()), row.id)
    lock = _list_locks.setdefault(key, asyncio.Lock())
    async with lock:
        if not refresh:
            stored = await stored_page_list(session, row.id)
            if stored is not None:
                return stored
        source = _source_of(row)
        async with await reader_semaphore(row.source_site):
            try:
                pages = await source.list_pages(row.chapter_url)
            except ChapterUnavailable as exc:
                raise Unavailable(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise PageFailed(f"could not list pages: {exc}") from exc
        if not pages:
            raise Unavailable(f"no pages listed for {row.chapter_url}")
        await store_page_list(session, row.id, pages)
        # Committed here rather than by the route: two requests waiting on this
        # lock read through separate sessions, and the second must see the list.
        await session.commit()
        return pages


def _source_of(row: ChapterRow) -> Any:
    if row.source_site is None:
        raise NoMapping(f"series {row.series_id} has no confirmed source")
    if row.chapter_url is None:
        raise Unavailable(f"chapter {row.id} has no source url of its own")
    try:
        return source_for_url(row.chapter_url)
    except ValueError as exc:
        raise NoMapping(str(exc)) from exc


async def _client_of(session: AsyncSession, row: ChapterRow):
    try:
        return get_client(await load_catalogue_row(session, row.source_site))
    except PermanentError as exc:
        raise NoMapping(str(exc)) from exc


async def _fetch_streamed(session: AsyncSession, row: ChapterRow, index: int) -> bytes:
    source = _source_of(row)
    client = await _client_of(session, row)
    pages = await page_list(session, row)
    if index >= len(pages):
        raise IndexError(index)
    try:
        return await _fetch_one(source, client, row.source_site, pages[index])
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (404, 410):
            raise PageFailed(str(exc)) from exc

    # The same rule fetch_chapter applies: a 404 on a list that resolved a
    # while ago is the address going stale, so ask for the list once more and
    # no more than once.
    pages = await page_list(session, row, refresh=True)
    if index >= len(pages):
        raise IndexError(index)
    try:
        return await _fetch_one(source, client, row.source_site, pages[index])
    except httpx.HTTPStatusError as exc:
        raise PageFailed(str(exc)) from exc


async def _fetch_one(source: Any, client: Any, site: str, page: PageRef) -> bytes:
    async with await reader_semaphore(site):
        try:
            [data] = await fetch_pages(client, [page], transform=source.descramble)
        except (PageFetchError, httpx.TransportError) as exc:
            raise PageFailed(str(exc)) from exc
    return data


async def _mark_streaming(session: AsyncSession, chapter_id: int) -> None:
    # Only from a resting state. A chapter already queued or downloading keeps
    # its state: the download lane owns it now, and it will reach the library
    # on its own.
    await session.execute(
        text(
            "update chapter set state = 'streaming'"
            " where id = :id and state in ('known', 'failed')"
        ),
        {"id": chapter_id},
    )


async def _queue_assembly_when_complete(session: AsyncSession, row: ChapterRow) -> None:
    listed = await stored_page_list(session, row.id)
    if listed is None or cache.cached_count(cache_root(), row.id) < len(listed):
        return
    state = (
        await session.execute(text("select state from chapter where id = :id"), {"id": row.id})
    ).scalar_one()
    if state != "streaming":
        return
    # The dedupe key is what makes two requests for the last page queue one
    # job: the partial unique index refuses the second while the first waits.
    await repo.enqueue(
        session,
        JobType.DOWNLOAD_CHAPTER,
        {"chapter_id": row.id, "from_cache": True},
        priority=50,
        series_id=row.series_id,
        dedupe_key=f"download_chapter:{row.id}",
    )
```

- [ ] **Step 4: Implement `routes_reader.py` and register it**

Create `backend/app/api/routes_reader.py`:

```python
"""The reader: pages, where reading stands, and how a series is shown."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reader_service as service
from app.api.deps import db_session

router = APIRouter(prefix="/api/reader", tags=["reader"])

Session = Annotated[AsyncSession, Depends(db_session)]

# A page of a chapter never changes once fetched, and a reader flipping back
# and forth should not ask twice.
IMMUTABLE = "public, max-age=31536000, immutable"

MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
}


@contextmanager
def service_errors() -> Iterator[None]:
    try:
        yield
    except service.ChapterMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="no such page") from exc
    except service.NoMapping as exc:
        raise HTTPException(
            status_code=409, detail="this series has no confirmed source yet"
        ) from exc
    except service.Unavailable as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except service.PageFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _chapter_ref(row: service.ChapterRow) -> dict[str, Any]:
    return {"id": row.id, "number": float(row.number), "title": row.title, "state": row.state}


@router.get("/chapters/{chapter_id}")
async def manifest(chapter_id: int, session: Session) -> dict[str, Any]:
    with service_errors():
        row = await service.chapter(session, chapter_id)
        origin, count = await service.page_count(session, row)
    await session.commit()
    return {
        "chapter": _chapter_ref(row),
        "series": {"id": row.series_id, "title": row.series_title},
        "origin": origin,
        "page_count": count,
    }


@router.get("/chapters/{chapter_id}/pages/{index}")
async def page(chapter_id: int, index: int, session: Session) -> Response:
    with service_errors():
        row = await service.chapter(session, chapter_id)
        data, extension = await service.serve_page(session, row, index)
    await session.commit()
    return Response(
        content=data,
        media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers={"Cache-Control": IMMUTABLE},
    )
```

In `backend/app/api/main.py`:
- Add `routes_reader` to the `from app.api import (...)` list, in alphabetical order.
- Add `app.include_router(routes_reader.router)` after `routes_sources`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_api.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass. The stale-list test takes about a second, because the fetcher retries the 404 with backoff.

Two failures to check for:
- `ChapterRow(**row._mapping)` fails on an unexpected key: the column aliases must match the dataclass fields exactly.
- The concurrency test queues two jobs: confirm the partial unique index `ix_job_dedupe` exists (`\d job` in psql).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reader_service.py backend/app/api/routes_reader.py \
  backend/app/api/main.py backend/tests/test_reader_api.py
git commit -m "feat(reader): serve pages from the archive or stream them through a cache"
```

---

### Task 5: Manifest neighbours, position, preferences, resume

**Files:**
- Modify: `backend/app/api/reader_service.py`, `backend/app/api/routes_reader.py`, `backend/app/api/routes_series.py` (detail chapters carry `id`)
- Test: `backend/tests/test_reader_api.py`

**Interfaces:**
- Produces:
  - Manifest adds `previous: {id, number, title} | null`, `next: {...} | null`, `position: int | null` and `prefs: {mode, scale, background, custom}`.
  - `PUT /api/reader/series/{id}/position` with body `{chapter_id, page}` returns `{ok: true}`.
  - `GET /api/reader/series/{id}/prefs` and `PUT /api/reader/series/{id}/prefs` with body `{mode, scale, background}`; both return the effective prefs.
  - `PUT /api/reader/defaults` with body `{mode, scale, background}` returns `{ok: true}`.
  - `GET /api/reader/series/{id}/resume` returns `{chapter_id, page}`, or 404 when the series has no chapters.
  - `GET /api/series/{id}` adds `id` to each chapter.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_reader_api.py`:

```python
async def _three_archived_chapters(tmp_path) -> tuple[int, list[int]]:
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ids = []
        for number in ("1", "2", "3"):
            path = _cbz(tmp_path / "manga" / "teto" / f"c{number}.cbz", [JPEG, JPEG])
            ids.append(await _chapter(session, series_id, number, file_path=path, state="downloaded"))
    return series_id, ids


async def test_manifest_names_the_chapters_either_side(client, tmp_path):
    _, (first, middle, last) = await _three_archived_chapters(tmp_path)
    body = (await client.get(f"/api/reader/chapters/{middle}")).json()
    assert body["previous"]["id"] == first
    assert body["next"]["id"] == last
    edge = (await client.get(f"/api/reader/chapters/{first}")).json()
    assert edge["previous"] is None


async def test_position_round_trips_and_only_applies_to_its_chapter(client, tmp_path):
    series_id, (first, middle, _) = await _three_archived_chapters(tmp_path)
    saved = await client.put(
        f"/api/reader/series/{series_id}/position", json={"chapter_id": middle, "page": 1}
    )
    assert saved.status_code == 200
    assert (await client.get(f"/api/reader/chapters/{middle}")).json()["position"] == 1
    assert (await client.get(f"/api/reader/chapters/{first}")).json()["position"] is None


async def test_a_position_for_another_series_chapter_is_refused(client, tmp_path):
    series_id, (first, _, _) = await _three_archived_chapters(tmp_path)
    async with get_sessionmaker()() as session:
        other = await _series(session, slug="other")
    response = await client.put(
        f"/api/reader/series/{other}/position", json={"chapter_id": first, "page": 0}
    )
    assert response.status_code == 404


async def test_prefs_fall_back_to_the_defaults_then_stick_per_series(client, tmp_path):
    series_id, (first, _, _) = await _three_archived_chapters(tmp_path)
    prefs = (await client.get(f"/api/reader/series/{series_id}/prefs")).json()
    assert prefs == {"mode": "paged_rtl", "scale": "fit_screen", "background": "black", "custom": False}

    stored = await client.put(
        f"/api/reader/series/{series_id}/prefs",
        json={"mode": "long_strip", "scale": "fit_width", "background": "white"},
    )
    assert stored.json()["custom"] is True
    manifest = (await client.get(f"/api/reader/chapters/{first}")).json()
    assert manifest["prefs"]["mode"] == "long_strip"


async def test_an_unknown_mode_is_refused(client, tmp_path):
    series_id, _ = await _three_archived_chapters(tmp_path)
    response = await client.put(
        f"/api/reader/series/{series_id}/prefs",
        json={"mode": "sideways", "scale": "fit_width", "background": "white"},
    )
    assert response.status_code == 422


async def test_defaults_change_what_an_uncustomised_series_gets(client, tmp_path):
    series_id, _ = await _three_archived_chapters(tmp_path)
    await client.put(
        "/api/reader/defaults", json={"mode": "long_strip", "scale": "fit_width", "background": "gray"}
    )
    prefs = (await client.get(f"/api/reader/series/{series_id}/prefs")).json()
    assert prefs["mode"] == "long_strip"
    assert prefs["custom"] is False


async def test_resume_opens_the_saved_position(client, tmp_path):
    series_id, (_, middle, _) = await _three_archived_chapters(tmp_path)
    await client.put(f"/api/reader/series/{series_id}/position", json={"chapter_id": middle, "page": 1})
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).json() == {
        "chapter_id": middle, "page": 1,
    }


async def test_resume_without_a_position_opens_the_first_unread_chapter(client, tmp_path):
    series_id, (_, middle, _) = await _three_archived_chapters(tmp_path)
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into list_entry (provider, provider_media_id, series_id, title_romaji, synonyms, raw,"
                " status, user_progress_chapter) values ('local', :m, :s, 'Teto', '[]'::jsonb, '{}'::jsonb, 'reading', 1)"
            ),
            {"m": str(series_id), "s": series_id},
        )
        await session.commit()
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).json() == {
        "chapter_id": middle, "page": 0,
    }


async def test_resume_of_a_series_with_no_chapters_is_404(client):
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
    assert (await client.get(f"/api/reader/series/{series_id}/resume")).status_code == 404


async def test_series_detail_chapters_carry_their_id(client, tmp_path):
    series_id, ids = await _three_archived_chapters(tmp_path)
    detail = (await client.get(f"/api/series/{series_id}")).json()
    assert [chapter["id"] for chapter in detail["chapters"]] == ids
```

`list_entry` has no `title` column, and `synonyms` and `raw` have only Python-side defaults, so a raw insert states them. `tests/test_local_tracking.py` shows a working insert for the `local` provider if this one fails.

- [ ] **Step 2: Run tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_api.py -q`
Expected: the new tests FAIL with `KeyError: 'previous'`, 404/405 on the new routes, or a missing `id`.

- [ ] **Step 3: Extend `reader_service.py`**

Append:

```python
from app import settings_store  # place with the other imports
from app.handlers import progress_events  # place with the other imports

MODES = ("paged_ltr", "paged_rtl", "long_strip", "double")
SCALES = ("fit_width", "fit_height", "fit_screen")
BACKGROUNDS = ("black", "gray", "white")


async def neighbours(session: AsyncSession, row: ChapterRow) -> tuple[dict | None, dict | None]:
    async def one(comparison: str, order: str) -> dict | None:
        result = await session.execute(
            text(
                f"""
                select id, number, title from chapter
                 where series_id = :s and number {comparison} :n
                 order by number {order} limit 1
                """
            ),
            {"s": row.series_id, "n": row.number},
        )
        found = result.first()
        if found is None:
            return None
        return {"id": found.id, "number": float(found.number), "title": found.title}

    # The two literals are the only values interpolated, and they are ours.
    return await one("<", "desc"), await one(">", "asc")


async def position_in(session: AsyncSession, row: ChapterRow) -> int | None:
    result = await session.execute(
        text("select chapter_id, page from reading_position where series_id = :s"),
        {"s": row.series_id},
    )
    found = result.first()
    return found.page if found is not None and found.chapter_id == row.id else None


async def save_position(session: AsyncSession, series_id: int, chapter_id: int, page: int) -> None:
    owner = await session.execute(
        text("select 1 from chapter where id = :c and series_id = :s"),
        {"c": chapter_id, "s": series_id},
    )
    if owner.first() is None:
        raise ChapterMissing(f"chapter {chapter_id} is not part of series {series_id}")
    await session.execute(
        text(
            """
            insert into reading_position (series_id, chapter_id, page, updated_at)
            values (:s, :c, :p, now())
            on conflict (series_id) do update
               set chapter_id = excluded.chapter_id, page = excluded.page,
                   updated_at = excluded.updated_at
            """
        ),
        {"s": series_id, "c": chapter_id, "p": page},
    )


async def effective_prefs(session: AsyncSession, series_id: int) -> dict[str, Any]:
    result = await session.execute(
        text("select mode, scale, background from series_reader_pref where series_id = :s"),
        {"s": series_id},
    )
    found = result.first()
    if found is not None:
        return {"mode": found.mode, "scale": found.scale, "background": found.background, "custom": True}
    return {
        "mode": await settings_store.get(session, settings_store.READER_DEFAULT_MODE),
        "scale": await settings_store.get(session, settings_store.READER_DEFAULT_SCALE),
        "background": await settings_store.get(session, settings_store.READER_DEFAULT_BACKGROUND),
        "custom": False,
    }


async def save_prefs(session: AsyncSession, series_id: int, mode: str, scale: str, background: str) -> None:
    await session.execute(
        text(
            """
            insert into series_reader_pref (series_id, mode, scale, background)
            values (:s, :m, :sc, :b)
            on conflict (series_id) do update
               set mode = excluded.mode, scale = excluded.scale, background = excluded.background
            """
        ),
        {"s": series_id, "m": mode, "sc": scale, "b": background},
    )


async def save_defaults(session: AsyncSession, mode: str, scale: str, background: str) -> None:
    await settings_store.set_value(session, settings_store.READER_DEFAULT_MODE, mode)
    await settings_store.set_value(session, settings_store.READER_DEFAULT_SCALE, scale)
    await settings_store.set_value(session, settings_store.READER_DEFAULT_BACKGROUND, background)


async def resume(session: AsyncSession, series_id: int) -> dict[str, int]:
    saved = await session.execute(
        text(
            """
            select p.chapter_id, p.page from reading_position p
              join chapter c on c.id = p.chapter_id
             where p.series_id = :s
            """
        ),
        {"s": series_id},
    )
    found = saved.first()
    if found is not None:
        return {"chapter_id": found.chapter_id, "page": found.page}

    furthest = await progress_events.furthest_read(session, series_id)
    result = await session.execute(
        text(
            """
            select id from chapter where series_id = :s
             order by (number > :furthest) desc, number asc
             limit 1
            """
        ),
        {"s": series_id, "furthest": furthest},
    )
    chapter_id = result.scalar_one_or_none()
    if chapter_id is None:
        raise ChapterMissing(f"series {series_id} has no chapters")
    return {"chapter_id": chapter_id, "page": 0}
```

The ordering `(number > :furthest) desc, number asc` picks the first chapter past the furthest one read. When none is past it, it falls back to the first chapter, so a series read to the end still opens on something.

- [ ] **Step 4: Extend the routes**

In `backend/app/api/routes_reader.py`, add imports `from typing import Literal` and `from pydantic import BaseModel, Field`. Replace `manifest` and add the new routes:

```python
class PositionIn(BaseModel):
    chapter_id: int
    page: int = Field(ge=0)


class PrefsIn(BaseModel):
    mode: Literal["paged_ltr", "paged_rtl", "long_strip", "double"]
    scale: Literal["fit_width", "fit_height", "fit_screen"]
    background: Literal["black", "gray", "white"]


@router.get("/chapters/{chapter_id}")
async def manifest(chapter_id: int, session: Session) -> dict[str, Any]:
    with service_errors():
        row = await service.chapter(session, chapter_id)
        origin, count = await service.page_count(session, row)
    previous, following = await service.neighbours(session, row)
    body = {
        "chapter": _chapter_ref(row),
        "series": {"id": row.series_id, "title": row.series_title},
        "origin": origin,
        "page_count": count,
        "previous": previous,
        "next": following,
        "position": await service.position_in(session, row),
        "prefs": await service.effective_prefs(session, row.series_id),
    }
    await session.commit()
    return body


@router.put("/series/{series_id}/position")
async def save_position(series_id: int, body: PositionIn, session: Session) -> dict[str, bool]:
    with service_errors():
        await service.save_position(session, series_id, body.chapter_id, body.page)
    await session.commit()
    return {"ok": True}


@router.get("/series/{series_id}/prefs")
async def prefs(series_id: int, session: Session) -> dict[str, Any]:
    return await service.effective_prefs(session, series_id)


@router.put("/series/{series_id}/prefs")
async def save_prefs(series_id: int, body: PrefsIn, session: Session) -> dict[str, Any]:
    await service.save_prefs(session, series_id, body.mode, body.scale, body.background)
    await session.commit()
    return await service.effective_prefs(session, series_id)


@router.put("/defaults")
async def save_defaults(body: PrefsIn, session: Session) -> dict[str, bool]:
    await service.save_defaults(session, body.mode, body.scale, body.background)
    await session.commit()
    return {"ok": True}


@router.get("/series/{series_id}/resume")
async def resume(series_id: int, session: Session) -> dict[str, int]:
    with service_errors():
        return await service.resume(session, series_id)
```

The `PUT .../prefs` route for an unknown series id fails with a foreign-key error, which surfaces as a 500. Guard it: `select 1 from series where id = :id`, and raise 404 if absent, before calling `save_prefs`.

In `backend/app/api/routes_series.py`, in the detail endpoint:
- Change the chapters query to `select id, number, title, state, file_path, komga_book_id`.
- Add `"id": c.id,` as the first key of each chapter dict.

- [ ] **Step 5: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_api.py tests/test_api.py tests/test_series_detail_links.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reader_service.py backend/app/api/routes_reader.py \
  backend/app/api/routes_series.py backend/tests/test_reader_api.py
git commit -m "feat(reader): remember the page, the display per series, and where to resume"
```

---

### Task 6: Finishing a chapter — lists and Komga

**Files:**
- Create: `backend/app/api/progress_queue.py`, `backend/app/handlers/komga_read_progress.py`, `backend/tests/test_reader_progress.py`
- Modify: `backend/app/api/routes_series.py`, `backend/app/api/routes_reader.py`, `backend/app/handlers/progress_write.py`, `backend/app/worker/main.py`

**Interfaces:**
- Produces:
  - `progress_queue.chapter_ceiling(total, known) -> int | None`, moved from `routes_series`, which re-imports it.
  - `progress_queue.progress_bounds(session, series_id) -> Bounds(current: int, ceiling: int | None, has_entries: bool)`.
  - `progress_queue.queue_progress_write(session, series_id, chapter: int, *, source: ProgressSource) -> None`.
  - `POST /api/reader/chapters/{id}/complete` returns `{progress_queued: bool, komga_queued: bool}`.
  - Job `komga_read_progress` with payload `{book_id}`.
  - `progress_write` reads `payload.get("source", "manual")`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reader_progress.py`:

```python
"""Finishing a chapter in the reader moves the lists and Komga forward."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import komga_read_progress, progress_write
from app.handlers.base import JobContext
from app.queue import repo

pytestmark = pytest.mark.asyncio

EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, series, list_entry restart identity cascade")
        )
        await session.commit()


async def _series_at(progress: int | None, *, total: int | None = None) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', 's-progress', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        if progress is not None:
            await session.execute(
                text(
                    "insert into list_entry (provider, provider_media_id, series_id, title_romaji, synonyms, raw,"
                    " status, user_progress_chapter, total_chapters)"
                    " values ('local', :m, :s, 'S', '[]'::jsonb, '{}'::jsonb, 'reading', :p, :t)"
                ),
                {"m": str(series_id), "s": series_id, "p": progress, "t": total},
            )
        await session.commit()
    return int(series_id)


async def _chapter(series_id: int, number: str, book: str | None = None) -> int:
    async with get_sessionmaker()() as session:
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, komga_book_id)"
                    " values (:s, :n, :b) returning id"
                ),
                {"s": series_id, "n": Decimal(number), "b": book},
            )
        ).scalar_one()
        await session.commit()
    return int(chapter_id)


async def _jobs(job_type: JobType) -> list[dict]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text("select payload from job where type = :t order by id"), {"t": str(job_type)}
        )
        return [row[0] for row in rows.all()]


async def test_completing_a_chapter_queues_a_reader_progress_write(client):
    series_id = await _series_at(3)
    chapter_id = await _chapter(series_id, "5")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body == {"progress_queued": True, "komga_queued": False}
    assert await _jobs(JobType.PROGRESS_WRITE) == [
        {"series_id": series_id, "chapter": 5, "source": "reader"}
    ]


async def test_completing_a_chapter_behind_the_lists_queues_nothing(client):
    """Read in Mihon up to 15, then reread 10 here: the lists must stay at 15."""
    series_id = await _series_at(15)
    chapter_id = await _chapter(series_id, "10")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body["progress_queued"] is False
    assert await _jobs(JobType.PROGRESS_WRITE) == []


async def test_a_fractional_chapter_completes_its_whole_number(client):
    series_id = await _series_at(22)
    chapter_id = await _chapter(series_id, "23.5")
    await client.post(f"/api/reader/chapters/{chapter_id}/complete")
    assert (await _jobs(JobType.PROGRESS_WRITE))[0]["chapter"] == 23


async def test_a_chapter_past_the_ceiling_is_not_written(client):
    series_id = await _series_at(3, total=4)
    chapter_id = await _chapter(series_id, "9")
    # Only one chapter row exists, so the ceiling is max(total=4, known=1) = 4.
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body["progress_queued"] is False


async def test_a_series_on_no_list_queues_no_progress(client):
    series_id = await _series_at(None)
    chapter_id = await _chapter(series_id, "1")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body["progress_queued"] is False


async def test_completing_queues_komga_only_with_a_book_id(client):
    series_id = await _series_at(0)
    indexed = await _chapter(series_id, "1", book="book-1")
    unindexed = await _chapter(series_id, "2")
    assert (await client.post(f"/api/reader/chapters/{indexed}/complete")).json()["komga_queued"]
    assert not (await client.post(f"/api/reader/chapters/{unindexed}/complete")).json()["komga_queued"]
    assert await _jobs(JobType.KOMGA_READ_PROGRESS) == [{"book_id": "book-1"}]


async def test_progress_write_records_the_reader_as_the_source():
    series_id = await _series_at(1)
    async with get_sessionmaker()() as session:
        await repo.enqueue(
            session, JobType.PROGRESS_WRITE,
            {"series_id": series_id, "chapter": 2, "source": "reader"}, series_id=series_id,
        )
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await progress_write.handle(JobContext(session=session, job=job))
        await session.commit()
        source = (
            await session.execute(
                text("select source from progress_event where series_id = :s"), {"s": series_id}
            )
        ).scalar_one()
    assert source == "reader"


class FakeKomga:
    has_credentials = True

    def __init__(self):
        self.marked: list[tuple[str, bool]] = []

    async def set_read_progress(self, book_id: str, *, page: int, completed: bool) -> None:
        self.marked.append((book_id, completed))


async def test_the_komga_job_marks_the_book_read(monkeypatch):
    fake = FakeKomga()
    monkeypatch.setattr(komga_read_progress, "from_settings", lambda: fake)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.KOMGA_READ_PROGRESS, {"book_id": "book-9"})
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await komga_read_progress.handle(JobContext(session=session, job=job))
    assert fake.marked == [("book-9", True)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_progress.py -q`
Expected: FAIL with `ImportError: cannot import name 'komga_read_progress'`.

- [ ] **Step 3: Extract `progress_queue.py`**

Create `backend/app/api/progress_queue.py`:
- Move `chapter_ceiling` here verbatim from `routes_series.py`, docstring included.
- Add:

```python
"""Queueing a progress write, shared by the progress button and the reader."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, ProgressSource
from app.queue import repo


@dataclass(frozen=True)
class Bounds:
    current: int
    ceiling: int | None
    has_entries: bool


# chapter_ceiling(...) moved here unchanged.


async def progress_bounds(session: AsyncSession, series_id: int) -> Bounds:
    # min(), not max(): see the comment on set_progress in routes_series.
    result = await session.execute(
        text(
            """
            select coalesce(min(e.user_progress_chapter), 0) as current,
                   max(e.total_chapters) as total_chapters,
                   count(e.id) as entries,
                   (select count(*) from chapter where series_id = :id) as known
              from list_entry e
             where e.series_id = :id
            """
        ),
        {"id": series_id},
    )
    row = result.one()
    return Bounds(
        current=row.current,
        ceiling=chapter_ceiling(row.total_chapters, row.known),
        has_entries=row.entries > 0,
    )


async def queue_progress_write(
    session: AsyncSession, series_id: int, chapter: int, *, source: ProgressSource
) -> None:
    queued = await repo.enqueue(
        session,
        JobType.PROGRESS_WRITE,
        {"series_id": series_id, "chapter": chapter, "source": str(source)},
        priority=0,
        series_id=series_id,
        dedupe_key=f"progress_write:{series_id}",
    )
    if queued is None:
        ...  # the existing jsonb_set update from routes_series.set_progress, moved here
```

Replace `...` with the `update job set payload = jsonb_set(...)` statement exactly as it stands in `routes_series.set_progress`, comment included, with `body.chapter` replaced by `chapter`.

In `routes_series.py`:
- Delete `chapter_ceiling`.
- Import `chapter_ceiling`, `progress_bounds` and `queue_progress_write` from `app.api.progress_queue`.
- In `set_progress`, replace the bounds query with `bounds = await progress_bounds(session, series_id)`, and use `bounds.current` and `bounds.ceiling`.
- Replace the enqueue-and-merge block with `await queue_progress_write(session, series_id, body.chapter, source=ProgressSource.MANUAL)`.
- Import `ProgressSource` from `app.enums`.

The existing progress tests in `test_api.py` must still pass unchanged.

- [ ] **Step 4: `progress_write` source and the Komga handler**

In `backend/app/handlers/progress_write.py`, replace `source=ProgressSource.MANUAL,` in the `record` call with:

```python
            # Payloads queued before the reader existed carry no source, and
            # every one of them came from the progress button.
            source=ProgressSource(ctx.payload.get("source", ProgressSource.MANUAL)),
```

Create `backend/app/handlers/komga_read_progress.py`:

```python
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
```

In `backend/app/worker/main.py`, add `komga_read_progress` to the handler import list, alphabetically.

- [ ] **Step 5: The completion route**

Add to `backend/app/api/routes_reader.py`:

```python
import math  # with the other imports

from app.api.progress_queue import progress_bounds, queue_progress_write
from app.enums import JobType, ProgressSource
from app.handlers.progress_write import forward_only
from app.queue import repo


@router.post("/chapters/{chapter_id}/complete")
async def complete(chapter_id: int, session: Session) -> dict[str, bool]:
    """Finishing a chapter here says the same thing finishing it in Komga does.

    A refusal is not an error. Rereading an old chapter, or reading a series on
    no list, must not interrupt the reader; it only moves nothing.
    """
    with service_errors():
        row = await service.chapter(session, chapter_id)

    # Lists count whole chapters. 23.5 finished means 23 is, and 24 is not.
    chapter = math.floor(row.number)
    bounds = await progress_bounds(session, row.series_id)
    progress_queued = (
        bounds.has_entries
        and chapter >= 1
        and forward_only(bounds.current, chapter) is not None
        and (bounds.ceiling is None or chapter <= bounds.ceiling)
    )
    if progress_queued:
        await queue_progress_write(session, row.series_id, chapter, source=ProgressSource.READER)

    komga_queued = False
    if row.komga_book_id is not None:
        await repo.enqueue(
            session,
            JobType.KOMGA_READ_PROGRESS,
            {"book_id": row.komga_book_id},
            series_id=row.series_id,
            dedupe_key=f"komga_read_progress:{row.komga_book_id}",
        )
        komga_queued = True

    await session.commit()
    return {"progress_queued": progress_queued, "komga_queued": komga_queued}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_progress.py tests/test_api.py tests/test_local_tracking.py tests/test_lanes.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/progress_queue.py backend/app/api/routes_series.py \
  backend/app/api/routes_reader.py backend/app/handlers/progress_write.py \
  backend/app/handlers/komga_read_progress.py backend/app/worker/main.py \
  backend/tests/test_reader_progress.py
git commit -m "feat(reader): finishing a chapter moves the lists and Komga forward"
```

---

### Task 7: Building the archive from the cache

**Files:**
- Modify: `backend/app/handlers/download_chapter.py`, `backend/app/handlers/download_batch.py`
- Test: `backend/tests/test_download_chapter_handler.py`, `backend/tests/test_download_batch_handler.py`

**Interfaces:**
- Consumes: `cache.read_all` and `cache.remove`, `reader_cache.stored_page_list`, `Settings.reader_cache_path`.
- Produces: `download_chapter` honours `payload["from_cache"]`. `download_batch` leaves `streaming` chapters alone.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_download_chapter_handler.py`:

```python
from app.handlers.reader_cache import store_page_list
from app.reader import cache as reader_cache_files


async def _context_from_cache(session, chapter_id: int) -> JobContext:
    await repo.enqueue(
        session, JobType.DOWNLOAD_CHAPTER, {"chapter_id": chapter_id, "from_cache": True}
    )
    await session.commit()
    job = await repo.lease(session, types=EVERY_TYPE)
    await session.commit()
    return JobContext(session=session, job=job)


async def test_a_chapter_read_in_the_reader_is_assembled_from_the_cache_without_the_network(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    from app.config import get_settings

    get_settings.cache_clear()

    def router(path):
        raise AssertionError(f"the network was asked for {path}")

    stub = Stub(router)
    try:
        chapter_url = f"{stub.base_url}/manga/1/chapter/1"
        listed = [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")]
        source = FakeSource(stub.key, pages={chapter_url: listed})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", chapter_url)
            await session.execute(
                text("update chapter set state = 'streaming' where id = :id"), {"id": chapter_id}
            )
            await store_page_list(session, chapter_id, listed)
            await session.commit()
            for index in range(2):
                reader_cache_files.write_page(tmp_path / "cache", chapter_id, index, JPEG)

            ctx = await _context_from_cache(session, chapter_id)
            await download_chapter.handle(ctx)
            await session.commit()
            row = (
                await session.execute(
                    text("select state, file_path from chapter where id = :id"), {"id": chapter_id}
                )
            ).first()

        assert row.state == "downloaded"
        with zipfile.ZipFile(row.file_path) as archive:
            assert sorted(n for n in archive.namelist() if n.endswith(".jpg")) == ["001.jpg", "002.jpg"]
            assert "ComicInfo.xml" in archive.namelist()
        assert not (tmp_path / "cache" / str(chapter_id)).exists()
    finally:
        stub.close()


async def test_a_page_missing_from_the_cache_is_fetched_and_the_rest_are_not(tmp_path, monkeypatch):
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    from app.config import get_settings

    get_settings.cache_clear()
    hits: list[str] = []

    def router(path):
        hits.append(path)
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        chapter_url = f"{stub.base_url}/manga/1/chapter/1"
        listed = [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")]
        source = FakeSource(stub.key, pages={chapter_url: listed})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", chapter_url)
            await store_page_list(session, chapter_id, listed)
            await session.commit()
            reader_cache_files.write_page(tmp_path / "cache", chapter_id, 0, JPEG)

            ctx = await _context_from_cache(session, chapter_id)
            await download_chapter.handle(ctx)
            await session.commit()

        assert hits == ["/p2.jpg"]
    finally:
        stub.close()


async def test_assembly_of_a_chapter_already_in_the_library_only_clears_the_cache(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    from app.config import get_settings
    from app.downloader.paths import chapter_path

    get_settings.cache_clear()
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        chapter_url = f"{stub.base_url}/manga/1/chapter/1"
        install_registry({stub.key: RegisteredSource(source=FakeSource(stub.key, pages={}), base_url=stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", chapter_url)
            destination = chapter_path(tmp_path, "rebirth-monarch-of-the-dead", Decimal("1"), "Chapter 1")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"already here")
            reader_cache_files.write_page(tmp_path / "cache", chapter_id, 0, JPEG)

            ctx = await _context_from_cache(session, chapter_id)
            await download_chapter.handle(ctx)
            await session.commit()

        assert destination.read_bytes() == b"already here"
        assert not (tmp_path / "cache" / str(chapter_id)).exists()
    finally:
        stub.close()
```

The `clean` fixture sets `LIBRARY_PATH` to `tmp_path`, so the library and `tmp_path / "cache"` share a parent and do not collide.

Append to `backend/tests/test_download_batch_handler.py` (its helpers mirror the chapter tests):

```python
async def test_a_chapter_being_streamed_is_left_to_the_reader():
    hits: list[str] = []

    def router(path):
        hits.append(path)
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        url_1 = f"{stub.base_url}/manga/1/chapter/1"
        url_2 = f"{stub.base_url}/manga/1/chapter/2"
        source = FakeSource(stub.key, pages={url_1: [PageRef(url="/a.jpg")], url_2: [PageRef(url="/b.jpg")]})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            first = await _chapter(session, series_id, "1", url_1)
            second = await _chapter(session, series_id, "2", url_2)
            await session.execute(
                text("update chapter set state = 'streaming' where id = :id"), {"id": second}
            )
            await session.commit()
            ctx = await _context(session, [first, second])
            await download_batch.handle(ctx)
            await session.commit()

        assert hits == ["/a.jpg"]
        assert (await _states([first, second]))[second] == "streaming"
    finally:
        stub.close()
```

Check the helper names in `test_download_batch_handler.py` (`_series`, `_catalogue`, `_chapter`, `_context`, `_states`, `Stub`, `FakeSource`, `JPEG`) and adapt their signatures if they differ.

- [ ] **Step 2: Run tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_download_chapter_handler.py tests/test_download_batch_handler.py -q`
Expected: the new tests FAIL. The network test raises `AssertionError` from the router, and the batch test fetches `/b.jpg`.

- [ ] **Step 3: Implement the `from_cache` path**

In `backend/app/handlers/download_chapter.py`:
- Add imports: `from app.downloader.fetcher import fetch_pages`, `from app.handlers.reader_cache import stored_page_list`, `from app.reader import cache as reader_cache_files`.
- Replace `handle` with:

```python
@register(JobType.DOWNLOAD_CHAPTER)
async def handle(ctx: JobContext) -> None:
    chapter_id = int(ctx.payload["chapter_id"])
    from_cache = bool(ctx.payload.get("from_cache"))
    row = await load_context(ctx.session, chapter_id)
    number = Decimal(str(row["number"]))
    settings = get_settings()

    destination = chapter_path(Path(settings.library_path), row["slug"], number, row["title"])
    if destination.exists():
        await ctx.log(f"chapter {number} already in the library", pct=100)
        await mark_downloaded(ctx.session, chapter_id, destination)
        if from_cache:
            reader_cache_files.remove(settings.reader_cache_path, chapter_id)
        return

    if row["chapter_url"] is None:
        raise PermanentError(f"chapter {chapter_id} has no source url of its own")

    await ctx.session.execute(
        text("update chapter set state = 'downloading' where id = :id"), {"id": chapter_id}
    )
    await ctx.session.commit()

    if from_cache:
        page_bytes = await pages_from_cache(ctx, row, chapter_id, number)
    else:
        page_bytes = await pages_from_source(ctx, row, chapter_id, number)

    info = await build_comicinfo(ctx.session, row)
    await write_cbz(page_bytes, destination, info)

    await mark_downloaded(ctx.session, chapter_id, destination)
    if from_cache:
        reader_cache_files.remove(settings.reader_cache_path, chapter_id)
    await ctx.log(f"saved {destination.name}", pct=100)

    # One scan per series, not one per chapter: the dedupe key collapses a burst
    # of finished downloads into a single indexing pass.
    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": row["series_id"]},
        series_id=row["series_id"],
        dedupe_key=f"komga_scan:{row['series_id']}",
    )


async def _site(ctx: JobContext, row: dict[str, Any]):
    source = source_for_url(row["chapter_url"])
    catalogue_row = await load_catalogue_row(ctx.session, row["source_site"])
    # Images are frequently served from a different host than the site itself
    # (MangaDex hands out *.mangadex.network URLs) - the rate limit bucket that
    # governs them is still the site's, keyed off the catalogue row above,
    # rather than one per image CDN. Deliberate simplification, not an
    # oversight: the CDN is fronting the same site's own capacity.
    client = get_client(catalogue_row)
    limit = await settings_store.get_int(ctx.session, settings_store.PER_SOURCE_CONCURRENCY)
    semaphore = await source_semaphore(row["source_site"], limit)
    return source, client, semaphore


async def pages_from_cache(
    ctx: JobContext, row: dict[str, Any], chapter_id: int, number: Decimal
) -> list[bytes]:
    """The pages a reader already fetched, plus whatever it skipped.

    A reader can jump from page 3 to page 30, and the slider makes that easy,
    so a chapter that reached "every page cached" by count can still be asked
    to assemble after the cache lost a page to cleanup. Only the gaps go to the
    network.
    """
    listed = await stored_page_list(ctx.session, chapter_id)
    if listed is None:
        return await pages_from_source(ctx, row, chapter_id, number)

    pages = reader_cache_files.read_all(get_settings().reader_cache_path, chapter_id, len(listed))
    missing = [index for index, data in enumerate(pages) if data is None]
    if missing:
        source, client, semaphore = await _site(ctx, row)
        async with semaphore:
            fetched = await fetch_pages(
                client, [listed[index] for index in missing], transform=source.descramble
            )
        for index, data in zip(missing, fetched, strict=True):
            pages[index] = data
    await ctx.log(
        f"chapter {number}: {len(listed) - len(missing)}/{len(listed)} pages from the reader",
        pct=80,
    )
    return [data for data in pages if data is not None]


async def pages_from_source(
    ctx: JobContext, row: dict[str, Any], chapter_id: int, number: Decimal
) -> list[bytes]:
    ...
```

The body of `pages_from_source` is the existing fetch block, moved verbatim with all its comments:
- It starts from `await ctx.log(f"chapter {number}: listing pages from …", pct=0)`.
- It runs through the `report` closure and `async with semaphore:` with its `ChapterUnavailable` handling.
- It ends with the `pages fetched` log line.
- Obtain `source, client, semaphore` from `await _site(ctx, row)` at its top.
- It returns `page_bytes`.

Remove the now-duplicated `source_for_url`, `get_client` and semaphore lines from the old `handle`.

- [ ] **Step 4: Skip streaming chapters in a batch**

In `backend/app/handlers/download_batch.py`, inside `handle`, change the loop that builds `wanted`:

```python
    for row in rows:
        number = Decimal(str(row["number"]))
        # Someone is reading it, and the reader's cache becomes this chapter's
        # archive. Fetching it here as well would ask the source twice.
        if row["state"] == "streaming":
            continue
        destination = chapter_path(library_root, slug, number, row["title"])
```

`load_batch` already selects `c.state`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_download_chapter_handler.py tests/test_download_batch_handler.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, old tests included.

- [ ] **Step 6: Commit**

Two commits, one per handler:

```bash
git add backend/app/handlers/download_chapter.py backend/tests/test_download_chapter_handler.py
git commit -m "feat(downloader): build a chapter's archive from the pages the reader fetched"
git add backend/app/handlers/download_batch.py backend/tests/test_download_batch_handler.py
git commit -m "fix(downloader): leave a chapter being streamed to the reader"
```

---

### Task 8: Cleaning up abandoned caches

**Files:**
- Modify: `backend/app/handlers/reader_cache.py`, `backend/app/worker/runner.py`
- Test: `backend/tests/test_reader_cache_prune.py`

**Interfaces:**
- Produces:
  - `reader_cache.prune(session, root: Path, *, max_age_seconds: float = READER_CACHE_MAX_AGE) -> int`, which returns how many caches it removed.
  - `READER_CACHE_MAX_AGE = 7 * 86400`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_reader_cache_prune.py`:

```python
"""A chapter opened and left half read must not hold its cache forever."""

import os
import time

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers import reader_cache
from app.reader import cache

pytestmark = pytest.mark.asyncio

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


async def _chapter(state: str) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', :slug, false, '{}'::jsonb) returning id"
                ),
                {"slug": f"s-prune-{state}-{time.time_ns()}"},
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text("insert into chapter (series_id, number, state) values (:s, 1, :st) returning id"),
                {"s": series_id, "st": state},
            )
        ).scalar_one()
        await session.commit()
    return int(chapter_id)


def _age(root, chapter_id, days):
    old = time.time() - days * 86400
    directory = root / str(chapter_id)
    for path in [*directory.iterdir(), directory]:
        os.utime(path, (old, old))


async def _state(chapter_id: int) -> str:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(text("select state from chapter where id = :id"), {"id": chapter_id})
        ).scalar_one()


async def test_an_old_cache_is_removed_and_its_chapter_is_known_again(tmp_path):
    stale = await _chapter("streaming")
    fresh = await _chapter("streaming")
    cache.write_page(tmp_path, stale, 0, JPEG)
    cache.write_page(tmp_path, fresh, 0, JPEG)
    _age(tmp_path, stale, 8)

    async with get_sessionmaker()() as session:
        removed = await reader_cache.prune(session, tmp_path)
        await session.commit()

    assert removed == 1
    assert not (tmp_path / str(stale)).exists()
    assert (tmp_path / str(fresh)).exists()
    assert await _state(stale) == "known"
    assert await _state(fresh) == "streaming"


async def test_pruning_leaves_a_chapter_that_moved_on_alone(tmp_path):
    downloaded = await _chapter("downloaded")
    cache.write_page(tmp_path, downloaded, 0, JPEG)
    _age(tmp_path, downloaded, 8)
    async with get_sessionmaker()() as session:
        await reader_cache.prune(session, tmp_path)
        await session.commit()
    assert await _state(downloaded) == "downloaded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_cache_prune.py -q`
Expected: FAIL with `AttributeError: module 'app.handlers.reader_cache' has no attribute 'prune'`.

- [ ] **Step 3: Implement**

Append to `backend/app/handlers/reader_cache.py`:

```python
from pathlib import Path  # with the other imports

from app.reader import cache  # with the other imports

# A week: long enough that a chapter put down on Friday is still cached on
# Monday, short enough that a series abandoned mid-chapter does not hold its
# pages for good.
READER_CACHE_MAX_AGE = 7 * 86400


async def prune(
    session: AsyncSession, root: Path, *, max_age_seconds: float = READER_CACHE_MAX_AGE
) -> int:
    stale = cache.stale_chapters(root, max_age_seconds)
    for chapter_id in stale:
        cache.remove(root, chapter_id)
    if stale:
        # Back to known only from streaming: a chapter downloaded meanwhile
        # keeps the state that says so.
        await session.execute(
            text(
                "update chapter set state = 'known'"
                " where id = any(cast(:ids as bigint[])) and state = 'streaming'"
            ),
            {"ids": stale},
        )
    return len(stale)
```

In `backend/app/worker/runner.py`, inside `reclaim_loop`, after `chapters = await repo.reclaim_orphaned_chapters(session)`:

```python
                # Only worker-download mounts the cache; on the fetch lane the
                # directory does not exist and this finds nothing.
                pruned = await reader_cache.prune(session, get_settings().reader_cache_path)
```

After the existing `if chapters:` log, add:

```python
            if pruned:
                log.info("removed %d reader caches nobody came back to", pruned)
```

Add the imports `from app.config import get_settings` and `from app.handlers import reader_cache`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_reader_cache_prune.py tests/test_worker_startup.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/reader_cache.py backend/app/worker/runner.py \
  backend/tests/test_reader_cache_prune.py
git commit -m "feat(reader): drop caches of chapters left half read for a week"
```

---

### Task 9: Komga follows list progress

**Files:**
- Modify: `backend/app/handlers/komga_scan.py`
- Test: `backend/tests/test_komga_list_progress.py`

**Interfaces:**
- Produces: `komga_scan.mark_read_up_to_lists(ctx, client, series_id, books) -> int`, which is called in `handle` right after the book ids are committed.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_komga_list_progress.py`:

```python
"""Komga learns what was read anywhere else: in Soshuhen's reader before it
had indexed the chapter, or in Mihon through the lists."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import komga_scan
from app.handlers.base import JobContext
from app.queue import repo

pytestmark = pytest.mark.asyncio

EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


class Book:
    def __init__(self, book_id: str, path: str, completed: bool = False):
        self.id = book_id
        self.path = path
        self.completed = completed

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]


class FakeKomga:
    has_credentials = True

    def __init__(self, books):
        self.books = books
        self.marked: list[str] = []

    async def ensure_library(self, name, path):
        return "lib-1"

    async def scan_library(self, library_id):
        return None

    async def find_series(self, root, slug, library_id):
        return "komga-series-1"

    async def books_of_series(self, series_id):
        return self.books

    async def set_read_progress(self, book_id, *, page, completed):
        self.marked.append(book_id)


async def _series(progress: int | None) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, chapter, series, list_entry restart identity cascade")
        )
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('K', 'k-progress', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        if progress is not None:
            await session.execute(
                text(
                    "insert into list_entry (provider, provider_media_id, series_id, title_romaji, synonyms, raw,"
                    " status, user_progress_chapter) values ('local', :m, :s, 'K', '[]'::jsonb, '{}'::jsonb, 'reading', :p)"
                ),
                {"m": str(series_id), "s": series_id, "p": progress},
            )
        for number in (1, 2, 3):
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, file_path)"
                    " values (:s, :n, 'downloaded', :p)"
                ),
                {"s": series_id, "n": number, "p": f"/manga/k/c{number}.cbz"},
            )
        await session.commit()
    return int(series_id)


async def _scan(monkeypatch, series_id, client):
    monkeypatch.setattr(komga_scan, "SCAN_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(komga_scan, "from_settings", lambda: client)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await komga_scan.handle(JobContext(session=session, job=job))
        await session.commit()


def _books(read: set[str] = frozenset()):
    return [Book(f"b{n}", f"/manga/k/c{n}.cbz", completed=f"b{n}" in read) for n in (1, 2, 3)]


async def test_books_up_to_list_progress_are_marked_read(monkeypatch):
    series_id = await _series(2)
    client = FakeKomga(_books())
    await _scan(monkeypatch, series_id, client)
    assert client.marked == ["b1", "b2"]


async def test_a_book_komga_already_has_as_read_is_not_marked_again(monkeypatch):
    series_id = await _series(2)
    client = FakeKomga(_books(read={"b1"}))
    await _scan(monkeypatch, series_id, client)
    assert client.marked == ["b2"]


async def test_a_series_with_no_progress_marks_nothing(monkeypatch):
    series_id = await _series(None)
    client = FakeKomga(_books())
    await _scan(monkeypatch, series_id, client)
    assert client.marked == []
```

`komga_scan.handle` also calls `ensure_series_cover` and `ensure_book_covers` on the client. If they reach methods `FakeKomga` lacks, copy the minimal stubs from `FakeKomga` in `tests/test_komga_completed.py`; that module's tests already drive `handle` end to end.

- [ ] **Step 2: Run test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_komga_list_progress.py -q`
Expected: FAIL, with `client.marked == []` where `["b1", "b2"]` was expected.

- [ ] **Step 3: Implement**

In `backend/app/handlers/komga_scan.py`, add `from app.handlers import progress_events` and:

```python
async def mark_read_up_to_lists(ctx: JobContext, client, series_id: int, books) -> int:
    """Mark read in Komga every indexed book the lists already count as read.

    The reader marks a book itself when Komga already knows it. A chapter read
    while it was still streaming had no book to mark, and one read in Mihon
    never reached Komga at all. Both are behind the lists' progress, which only
    moves forward, so the lists are what Komga is brought up to.
    """
    furthest = await progress_events.furthest_read(ctx.session, series_id)
    if furthest <= 0:
        return 0
    result = await ctx.session.execute(
        text(
            """
            select komga_book_id from chapter
             where series_id = :s and komga_book_id is not null and number <= :furthest
            """
        ),
        {"s": series_id, "furthest": furthest},
    )
    behind = {row[0] for row in result.all()}
    marked = 0
    for book in books:
        if book.id not in behind or book.completed:
            continue
        try:
            await client.set_read_progress(book.id, page=1, completed=True)
        except Exception as exc:  # noqa: BLE001 - one book is not the whole series
            await ctx.log(f"could not mark {book.filename} read: {exc}", level="warning")
            continue
        marked += 1
    return marked
```

In `handle`, after the `await ctx.session.commit()` that follows `adopt_book_ids`, add:

```python
    caught_up = await mark_read_up_to_lists(ctx, client, series_id, books)
    if caught_up:
        await ctx.log(f"marked {caught_up} books read to match the lists")
```

`furthest <= 0` returns before `book.completed` is ever read. That keeps the older tests, whose fake books have no `completed` attribute, passing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_komga_list_progress.py tests/test_komga_completed.py tests/test_komga_cover.py tests/test_komga_book_cover.py -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/komga_scan.py backend/tests/test_komga_list_progress.py
git commit -m "feat(komga): mark books read up to the progress the lists record"
```

---

### Task 10: Containers

**Files:**
- Modify: `backend/Dockerfile`, `docker-compose.yml`

- [ ] **Step 1: Dockerfile**

In `backend/Dockerfile`, before `EXPOSE 8000`:

```dockerfile
# A fresh named volume copies this directory's mode, which is the only way to
# get a cache two services running as PUID can both write without a root
# init step.
RUN mkdir -p /reader-cache && chmod 1777 /reader-cache
```

- [ ] **Step 2: Compose**

In `docker-compose.yml`, change the `api` service as follows.
- Add, right under `image:` or `build:`:

```yaml
    # Same uid as worker-download, which deletes the pages this writes once
    # they have become an archive.
    user: "${PUID:-1000}:${PGID:-1000}"
```

- Replace its `volumes:` with:

```yaml
    volumes:
      - ${LIBRARY_PATH_HOST:-./data/manga}:/manga:ro
      - reader-cache:/reader-cache
```

- Add `READER_CACHE_PATH: /reader-cache` to its `environment`.
- Update the existing comment above `FLARESOLVERR_URL`. It says the API "never fetches", which is no longer true: say that the API now fetches pages for the reader.

In `worker-download`'s `volumes:`, add `- reader-cache:/reader-cache`. `READER_CACHE_PATH` defaults to `/reader-cache` in `config.py`, so the shared env needs no entry.

Under the top-level `volumes:`, add `reader-cache:`.

- [ ] **Step 3: Verify**

Run: `docker compose config --quiet && docker compose build api && docker compose up -d --force-recreate api worker worker-download`
Then: `docker compose exec api sh -c 'touch /reader-cache/x && rm /reader-cache/x && echo ok'`
Expected: `ok`. Then `docker compose logs api --tail 20` shows uvicorn started and no permission error from `alembic upgrade head`.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml
git commit -m "build: share a reader cache between the api and the download lane"
```

---

### Task 11: Frontend groundwork — tokens, icons, API client, routes, entry points

**Files:**
- Modify: `frontend/tailwind.config.ts`, `frontend/src/ui/Icon.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/routes.tsx`, `frontend/src/features/series/ChapterTable.tsx`, `frontend/src/features/home/ContinueReading.tsx`
- Create: `frontend/src/features/reader/ResumePage.tsx`, `frontend/src/features/reader/ReaderMessage.tsx`, `frontend/src/features/reader/ReaderPage.tsx` (placeholder, replaced in Task 12)

**Interfaces:**
- Produces, in `lib/api.ts`:
  - Types `ReaderMode`, `ReaderScale`, `ReaderBackground`, `ReaderPrefs`, `ReaderChapterRef`, `ReaderChapter` and `ReaderManifest`.
  - `readerPageUrl(chapterId, index): string`.
  - `api.readerManifest`, `readerResume`, `readerChapters`, `saveReaderPosition`, `completeChapter`, `saveReaderPrefs` and `saveReaderDefaults`.
  - `SeriesChapter.id`.
- Produces: tokens `reader-black`, `reader-gray`, `reader-white`; icons `arrow_back`, `chevron_left`, `chevron_right`, `fullscreen`, `close`, `home`.

- [ ] **Step 1: Tokens and icons**

In `frontend/tailwind.config.ts`, inside `colors`, after the `warning` group:

```ts
        // The reader's page backgrounds. Not surface roles: a page is a
        // scanned image, and pure black or white around it is what the
        // reading apps use so the page edge does not read as a frame.
        'reader-black': '#000000',
        'reader-gray': '#2b2b2b',
        'reader-white': '#ffffff',
```

In `frontend/src/ui/Icon.tsx`, add to `ICONS` (Material icon paths):

```ts
  arrow_back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20z',
  chevron_left: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  chevron_right: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  fullscreen: 'M7 14H5v5h5v-2H7zm-2-4h2V7h3V5H5zm12 7h-3v2h5v-5h-2zM14 5v2h3v3h2V5z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
```

- [ ] **Step 2: API client**

In `frontend/src/lib/api.ts`, add `id: number` as the first field of `SeriesChapter`, with the comment `/** The reader opens a chapter by this. */`. Add after `SeriesChapter`:

```ts
export type ReaderMode = 'paged_ltr' | 'paged_rtl' | 'long_strip' | 'double'
export type ReaderScale = 'fit_width' | 'fit_height' | 'fit_screen'
export type ReaderBackground = 'black' | 'gray' | 'white'

export interface ReaderPrefs {
  mode: ReaderMode
  scale: ReaderScale
  background: ReaderBackground
  /** False while the series follows the default for every series. */
  custom: boolean
}

export interface ReaderChapterRef {
  id: number
  number: number
  title: string | null
}

export interface ReaderChapter extends ReaderChapterRef {
  state: string
}

export interface ReaderManifest {
  chapter: ReaderChapter
  series: { id: number; title: string }
  /** `stream` means the pages come from the source and are saved to the
      library once every one of them has loaded. */
  origin: 'archive' | 'stream'
  page_count: number
  previous: ReaderChapterRef | null
  next: ReaderChapterRef | null
  /** The saved page, only when the saved position is in this chapter. */
  position: number | null
  prefs: ReaderPrefs
}

/** An address, not a request: the browser loads it as an image. */
export function readerPageUrl(chapterId: number, index: number): string {
  return `/api/reader/chapters/${chapterId}/pages/${index}`
}
```

Inside `export const api = {`, after `seriesDetail`:

```ts
  readerManifest: (chapterId: number) =>
    request<ReaderManifest>(`/api/reader/chapters/${chapterId}`),
  readerResume: (seriesId: number) =>
    request<{ chapter_id: number; page: number }>(`/api/reader/series/${seriesId}/resume`),
  readerChapters: (seriesId: number) =>
    request<ReaderChapter[]>(`/api/series/${seriesId}/chapters`),
  saveReaderPosition: (seriesId: number, chapterId: number, page: number) =>
    request<{ ok: boolean }>(`/api/reader/series/${seriesId}/position`, {
      method: 'PUT',
      body: JSON.stringify({ chapter_id: chapterId, page }),
    }),
  completeChapter: (chapterId: number) =>
    request<{ progress_queued: boolean; komga_queued: boolean }>(
      `/api/reader/chapters/${chapterId}/complete`,
      { method: 'POST' },
    ),
  saveReaderPrefs: (seriesId: number, prefs: Omit<ReaderPrefs, 'custom'>) =>
    request<ReaderPrefs>(`/api/reader/series/${seriesId}/prefs`, {
      method: 'PUT',
      body: JSON.stringify(prefs),
    }),
  saveReaderDefaults: (prefs: Omit<ReaderPrefs, 'custom'>) =>
    request<{ ok: boolean }>('/api/reader/defaults', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    }),
```

- [ ] **Step 3: Message, resume page and a placeholder reader**

Create `frontend/src/features/reader/ReaderMessage.tsx`:

```tsx
import { Link } from 'react-router-dom'

import { buttonClass } from '../../ui'

/** Every state the reader shows before it has a page to show. */
export function ReaderMessage({
  title,
  detail,
  backTo,
}: {
  title: string
  detail?: string
  backTo: string
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-space-md bg-reader-black px-space-lg text-center">
      <h1 className="text-headline-sm text-on-surface">{title}</h1>
      {detail && <p className="max-w-md text-body-md text-on-surface-variant">{detail}</p>}
      <Link to={backTo} className={buttonClass({ variant: 'surface' })}>
        Back to the series
      </Link>
    </main>
  )
}
```

Create `frontend/src/features/reader/ResumePage.tsx`:

```tsx
import { useCallback, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ReaderMessage } from './ReaderMessage'

/** Continue reading: the server knows where, this only goes there. */
export function ResumePage() {
  const seriesId = Number(useParams().seriesId)
  const navigate = useNavigate()
  const load = useCallback(() => api.readerResume(seriesId), [seriesId])
  const { data, error, notFound } = useAsyncData(load)

  useEffect(() => {
    if (data) navigate(`/read/${data.chapter_id}?page=${data.page}`, { replace: true })
  }, [data, navigate])

  if (notFound) {
    return (
      <ReaderMessage
        title="Nothing to read yet"
        detail="No chapters of this series have been found at its source."
        backTo={`/series/${seriesId}`}
      />
    )
  }
  if (error) return <ReaderMessage title="Could not open the reader" detail={error} backTo={`/series/${seriesId}`} />
  return <ReaderMessage title="Opening…" backTo={`/series/${seriesId}`} />
}
```

Create a placeholder `frontend/src/features/reader/ReaderPage.tsx`, which Task 12 replaces:

```tsx
export function ReaderPage() {
  return null
}
```

- [ ] **Step 4: Routes and entry points**

In `frontend/src/app/routes.tsx`, import `ReaderPage` and `ResumePage`, and add before `<Route element={<AppShell />}>`:

```tsx
      {/* Outside the shell: the reader is the whole screen, and the header and
          bottom navigation would sit on top of the page being read. */}
      <Route path="read/series/:seriesId" element={<ResumePage />} />
      <Route path="read/:chapterId" element={<ReaderPage />} />
```

In `frontend/src/features/series/ChapterTable.tsx`, add `import { Link } from 'react-router-dom'`, and replace the whole Read `<td>` content (the `komgaHref && chapter.komga_book_id ? … : …` expression) with:

```tsx
                <div className="inline-flex items-center gap-space-xs">
                  {/* Every chapter can be read now: one not downloaded yet is
                      streamed from its source and saved as it is read. */}
                  <Link
                    to={`/read/${chapter.id}`}
                    className="inline-flex items-center gap-1.5 rounded-lg px-space-sm py-1 font-mono text-label-sm text-primary transition-colors hover:bg-primary/[0.12]"
                  >
                    <Icon name="book" className="h-3.5 w-3.5" />
                    Read
                  </Link>
                  {komgaHref && chapter.komga_book_id && (
                    <a
                      href={`${komgaHref}/book/${chapter.komga_book_id}/read?page=1&incognito=false`}
                      target="_blank"
                      rel="noreferrer"
                      title="Open in Komga"
                      aria-label="Open in Komga"
                      className="inline-flex items-center rounded-lg px-space-xs py-1 text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
                    >
                      <Icon name="link" className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
```

Change the row key from `chapter.number` to `chapter.id`.

In `frontend/src/features/home/ContinueReading.tsx`, after the `<p>` carrying "Chapter {formatChapter(row.progress)}", add:

```tsx
        <Link
          to={`/read/series/${row.series_id}`}
          className="mt-space-xs inline-flex w-fit items-center gap-1.5 rounded-lg px-space-sm py-1 font-mono text-label-sm text-primary transition-colors hover:bg-primary/[0.12]"
        >
          <Icon name="book" className="h-3.5 w-3.5" />
          Continue
        </Link>
```

Import `Icon` from `'../../ui'` if the file does not already.

- [ ] **Step 5: Build and verify the classes exist**

Run (from `frontend/`): `npm run build && grep -o 'bg-reader-black' dist/assets/*.css | head -1`
Expected: the build passes, and grep prints `bg-reader-black`. Every other class used here already exists elsewhere in the app.

- [ ] **Step 6: Commit**

```bash
git add frontend/tailwind.config.ts frontend/src/ui/Icon.tsx frontend/src/lib/api.ts \
  frontend/src/app/routes.tsx frontend/src/features/reader \
  frontend/src/features/series/ChapterTable.tsx frontend/src/features/home/ContinueReading.tsx
git commit -m "feat(web): reader routes, API client and the links that open it"
```

---

### Task 12: Reader core — pages, modes, navigation, position, completion

**Files:**
- Create in `frontend/src/features/reader/`: `lib/spreads.ts`, `lib/useReaderKeys.ts`, `lib/usePreload.ts`, `lib/usePositionSaver.ts`, `lib/styles.ts`, `PageImage.tsx`, `PagedView.tsx`, `StripView.tsx`, `EndOfChapter.tsx`
- Replace: `frontend/src/features/reader/ReaderPage.tsx`

**Interfaces:**
- Consumes: from Task 11, the `lib/api.ts` reader exports, `ReaderMessage` and the tokens.
- Produces: `ReaderPage` with internal state that Task 13's chrome reads through props:
  - `manifest`, `prefs`, `page`, `pageCount`
  - `goTo(page)`, `openChapter(id)`, `setPrefs`, `chromeVisible`, `setChromeVisible`, `panel`, `setPanel`

- [ ] **Step 1: Pure helpers and hooks**

Create `frontend/src/features/reader/lib/spreads.ts`:

```ts
import type { ReaderMode } from '../../../lib/api'

/** The pages shown together at each step of a paged mode. */
export function spreads(pageCount: number, mode: ReaderMode): number[][] {
  if (mode !== 'double') return Array.from({ length: pageCount }, (_, index) => [index])
  // The first page stands alone, the way a printed volume opens on its
  // cover; pairing it shifts every later spread by one and splits two-page
  // art down the middle.
  const groups: number[][] = pageCount > 0 ? [[0]] : []
  for (let index = 1; index < pageCount; index += 2) {
    groups.push(index + 1 < pageCount ? [index, index + 1] : [index])
  }
  return groups
}

export function spreadOf(groups: number[][], page: number): number {
  const found = groups.findIndex((group) => group.includes(page))
  return found === -1 ? 0 : found
}

export function clampPage(page: number, pageCount: number): number {
  if (!Number.isFinite(page) || pageCount === 0) return 0
  return Math.min(Math.max(Math.trunc(page), 0), pageCount - 1)
}
```

Create `frontend/src/features/reader/lib/styles.ts`:

```ts
import type { ReaderBackground, ReaderScale } from '../../../lib/api'

// Static maps rather than `bg-reader-${name}`: the Tailwind scanner never
// sees an interpolated class, and the build silently drops it.
export const BACKGROUND: Record<ReaderBackground, string> = {
  black: 'bg-reader-black',
  gray: 'bg-reader-gray',
  white: 'bg-reader-white',
}

export const PAGED_FIT: Record<ReaderScale, string> = {
  fit_width: 'h-auto w-full',
  fit_height: 'h-screen w-auto max-w-none',
  fit_screen: 'max-h-screen max-w-full object-contain',
}

// Fit height has no meaning down a strip, so it reads as a comfortable column
// the same as fit screen.
export const STRIP_FIT: Record<ReaderScale, string> = {
  fit_width: 'w-full',
  fit_height: 'w-full max-w-3xl',
  fit_screen: 'w-full max-w-3xl',
}
```

Create `frontend/src/features/reader/lib/useReaderKeys.ts`:

```ts
import { useEffect, useRef } from 'react'

export interface ReaderKeyActions {
  left: () => void
  right: () => void
  forward: () => void
  back: () => void
  previousChapter: () => void
  nextChapter: () => void
  fullscreen: () => void
  escape: () => void
}

export function useReaderKeys(actions: ReaderKeyActions): void {
  // A ref, so the listener is bound once and still calls the latest closures.
  const latest = useRef(actions)
  latest.current = actions

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (target instanceof HTMLInputElement && target.type !== 'range') return
      if (target instanceof HTMLTextAreaElement) return
      const run = latest.current
      switch (event.key) {
        case 'ArrowLeft':
          run.left()
          break
        case 'ArrowRight':
          run.right()
          break
        case ' ':
          if (event.shiftKey) run.back()
          else run.forward()
          break
        case '[':
          run.previousChapter()
          break
        case ']':
          run.nextChapter()
          break
        case 'f':
          run.fullscreen()
          break
        case 'Escape':
          run.escape()
          break
        default:
          return
      }
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
```

Create `frontend/src/features/reader/lib/usePreload.ts`:

```ts
import { useEffect } from 'react'

/**
 * Ask the browser for these images before they are on screen.
 *
 * The images are never cancelled on cleanup. A page turn would cancel the
 * request for the page after next, which the next turn asks for again, and
 * for a streamed chapter the server is fetching it from the source either way.
 */
export function usePreload(urls: string[]): void {
  const key = urls.join('|')
  useEffect(() => {
    for (const url of key ? key.split('|') : []) {
      const image = new Image()
      image.decoding = 'async'
      image.src = url
    }
  }, [key])
}
```

Create `frontend/src/features/reader/lib/usePositionSaver.ts`:

```ts
import { useCallback, useEffect, useRef } from 'react'

import { api } from '../../../lib/api'

const DELAY_MS = 800

/**
 * Save where reading stands, once the page has stopped changing.
 *
 * An explicit call per page turn rather than an effect on the page number:
 * an effect would also run for the page restored on open, and with a
 * debounce it would save the placeholder page zero over the real position
 * before the restore landed.
 *
 * A failed save is not shown. The next page turn saves again, and an error
 * banner over the page being read costs more than one lost position.
 */
export function usePositionSaver(seriesId: number | null, chapterId: number | null) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current)
    },
    [chapterId],
  )

  return useCallback(
    (page: number, { immediately = false } = {}) => {
      if (seriesId === null || chapterId === null) return
      if (timer.current !== null) clearTimeout(timer.current)
      const save = () => void api.saveReaderPosition(seriesId, chapterId, page).catch(() => undefined)
      if (immediately) save()
      else timer.current = setTimeout(save, DELAY_MS)
    },
    [seriesId, chapterId],
  )
}
```

- [ ] **Step 2: Page, views and end of chapter**

Create `frontend/src/features/reader/PageImage.tsx`:

```tsx
import { useState } from 'react'

import { readerPageUrl } from '../../lib/api'
import { Button } from '../../ui'

/**
 * One page, or a page-sized placeholder that says it could not load.
 *
 * A failed page must not take the chapter down with it: the source may have
 * dropped one request, and the page after it is very likely fine.
 */
export function PageImage({
  chapterId,
  index,
  className,
  eager = false,
}: {
  chapterId: number
  index: number
  className: string
  eager?: boolean
}) {
  const [attempt, setAttempt] = useState(0)
  const [failed, setFailed] = useState(false)

  if (failed) {
    return (
      <div className="flex aspect-[2/3] w-full max-w-xl flex-col items-center justify-center gap-space-md bg-surface-container text-on-surface-variant">
        <p className="text-body-md">Page {index + 1} could not be loaded.</p>
        <Button
          onClick={(event) => {
            event.stopPropagation()
            setFailed(false)
            setAttempt((value) => value + 1)
          }}
        >
          Try again
        </Button>
      </div>
    )
  }

  // The attempt in the query string is what makes a retry a new request: the
  // browser would otherwise answer from its memory of the failure.
  const src = attempt === 0 ? readerPageUrl(chapterId, index) : `${readerPageUrl(chapterId, index)}?attempt=${attempt}`
  return (
    <img
      src={src}
      alt={`Page ${index + 1}`}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      draggable={false}
      onError={() => setFailed(true)}
      className={`select-none ${className}`}
    />
  )
}
```

Create `frontend/src/features/reader/PagedView.tsx`:

```tsx
import type { MouseEvent } from 'react'

import type { ReaderScale } from '../../lib/api'
import { PAGED_FIT } from './lib/styles'
import { PageImage } from './PageImage'

export type Zone = 'left' | 'center' | 'right'

export function PagedView({
  chapterId,
  group,
  scale,
  rtl,
  onZone,
}: {
  chapterId: number
  group: number[]
  scale: ReaderScale
  rtl: boolean
  onZone: (zone: Zone) => void
}) {
  // A right-to-left spread puts the earlier page on the right.
  const ordered = rtl ? [...group].reverse() : group

  function click(event: MouseEvent<HTMLDivElement>) {
    const { left, width } = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - left) / width
    onZone(x < 1 / 3 ? 'left' : x > 2 / 3 ? 'right' : 'center')
  }

  return (
    <div onClick={click} className="flex min-h-screen w-full cursor-pointer items-center justify-center">
      {ordered.map((index) => (
        <PageImage
          key={index}
          chapterId={chapterId}
          index={index}
          eager
          className={group.length > 1 ? 'max-h-screen w-1/2 object-contain' : PAGED_FIT[scale]}
        />
      ))}
    </div>
  )
}
```

Create `frontend/src/features/reader/StripView.tsx`:

```tsx
import { useEffect, useRef, type ReactNode } from 'react'

import type { ReaderScale } from '../../lib/api'
import { STRIP_FIT } from './lib/styles'
import { PageImage } from './PageImage'

export function StripView({
  chapterId,
  pageCount,
  scale,
  initialPage,
  onPage,
  onEnd,
  onTap,
  end,
}: {
  chapterId: number
  pageCount: number
  scale: ReaderScale
  initialPage: number
  onPage: (page: number) => void
  onEnd: () => void
  onTap: () => void
  end: ReactNode
}) {
  const pages = useRef<(HTMLDivElement | null)[]>([])
  const endRef = useRef<HTMLDivElement | null>(null)
  const callbacks = useRef({ onPage, onEnd })
  callbacks.current = { onPage, onEnd }

  // Once per chapter. Rerunning on every page change would yank the strip back
  // to wherever the last saved page was.
  useEffect(() => {
    pages.current[initialPage]?.scrollIntoView()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId])

  useEffect(() => {
    const ratios = new Map<number, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          ratios.set(Number((entry.target as HTMLElement).dataset.index), entry.intersectionRatio)
        }
        let best = -1
        let highest = 0
        for (const [index, ratio] of ratios) {
          if (ratio > highest) {
            best = index
            highest = ratio
          }
        }
        if (best >= 0) callbacks.current.onPage(best)
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] },
    )
    for (const element of pages.current) if (element) observer.observe(element)

    const ending = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) callbacks.current.onEnd()
    })
    if (endRef.current) ending.observe(endRef.current)

    return () => {
      observer.disconnect()
      ending.disconnect()
    }
  }, [chapterId, pageCount])

  return (
    <div onClick={onTap} className="mx-auto flex w-full flex-col items-center">
      {Array.from({ length: pageCount }, (_, index) => (
        <div
          key={index}
          data-index={index}
          ref={(element) => {
            pages.current[index] = element
          }}
          // A height before the image loads, so the observer and the restore
          // scroll have something to measure.
          className="flex min-h-[50vh] w-full justify-center"
        >
          <PageImage chapterId={chapterId} index={index} eager={Math.abs(index - initialPage) < 3} className={STRIP_FIT[scale]} />
        </div>
      ))}
      <div ref={endRef} className="w-full">
        {end}
      </div>
    </div>
  )
}
```

The repo has no ESLint config (check with `ls frontend/.eslintrc* frontend/eslint.config.*`). If there is none, drop the `eslint-disable` comment and keep the explanatory comment above it.

Create `frontend/src/features/reader/EndOfChapter.tsx`:

```tsx
import { Link } from 'react-router-dom'

import type { ReaderChapterRef } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Button, buttonClass } from '../../ui'

export function EndOfChapter({
  current,
  next,
  seriesId,
  onNext,
}: {
  current: ReaderChapterRef
  next: ReaderChapterRef | null
  seriesId: number
  onNext: () => void
}) {
  return (
    <section className="flex min-h-[60vh] w-full flex-col items-center justify-center gap-space-md px-space-lg text-center">
      <p className="font-mono text-label-md text-on-surface-variant">End of Ch. {formatChapter(current.number)}</p>
      {next ? (
        <Button
          variant="primary"
          icon="chevron_right"
          onClick={(event) => {
            event.stopPropagation()
            onNext()
          }}
        >
          Ch. {formatChapter(next.number)}
          {next.title ? ` · ${next.title}` : ''}
        </Button>
      ) : (
        <>
          <p className="text-body-md text-on-surface">You are caught up.</p>
          <Link to={`/series/${seriesId}`} className={buttonClass({ variant: 'surface' })}>
            Back to the series
          </Link>
        </>
      )}
    </section>
  )
}
```

- [ ] **Step 3: ReaderPage**

Replace `frontend/src/features/reader/ReaderPage.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api, readerPageUrl, type ReaderPrefs } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { EndOfChapter } from './EndOfChapter'
import { BACKGROUND } from './lib/styles'
import { clampPage, spreadOf, spreads } from './lib/spreads'
import { usePositionSaver } from './lib/usePositionSaver'
import { usePreload } from './lib/usePreload'
import { useReaderKeys } from './lib/useReaderKeys'
import { PagedView, type Zone } from './PagedView'
import { ReaderMessage } from './ReaderMessage'
import { StripView } from './StripView'

const PRELOAD_AHEAD = 3

export type Panel = 'settings' | 'chapters' | null

export function ReaderPage() {
  const chapterId = Number(useParams().chapterId)
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const load = useCallback(() => api.readerManifest(chapterId), [chapterId])
  const { data: manifest, error, notFound } = useAsyncData(load)

  const [prefs, setPrefs] = useState<ReaderPrefs | null>(null)
  const [page, setPage] = useState(0)
  const [atEnd, setAtEnd] = useState(false)
  const [chromeVisible, setChromeVisible] = useState(true)
  const [panel, setPanel] = useState<Panel>(null)
  const completed = useRef(new Set<number>())

  const save = usePositionSaver(manifest?.series.id ?? null, manifest?.chapter.id ?? null)

  // Once per manifest: the address wins over the saved position, so a link to
  // a page opens that page.
  useEffect(() => {
    if (!manifest) return
    setPrefs(manifest.prefs)
    const requested = params.get('page')
    const start = clampPage(requested !== null ? Number(requested) : (manifest.position ?? 0), manifest.page_count)
    setPage(start)
    setAtEnd(false)
    save(start, { immediately: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest])

  const mode = prefs?.mode ?? 'paged_rtl'
  const rtl = mode === 'paged_rtl'
  const strip = mode === 'long_strip'
  const groups = useMemo(() => spreads(manifest?.page_count ?? 0, mode), [manifest, mode])
  const step = spreadOf(groups, page)

  const goTo = useCallback(
    (next: number) => {
      if (!manifest) return
      const target = clampPage(next, manifest.page_count)
      setPage(target)
      setAtEnd(false)
      save(target)
      setParams({ page: String(target) }, { replace: true })
    },
    [manifest, save, setParams],
  )

  const openChapter = useCallback((id: number) => navigate(`/read/${id}?page=0`), [navigate])

  const finish = useCallback(() => {
    if (!manifest || completed.current.has(manifest.chapter.id)) return
    completed.current.add(manifest.chapter.id)
    // Failing here moves nothing and is retried by finishing the chapter
    // again; it does not deserve an interruption.
    void api.completeChapter(manifest.chapter.id).catch(() => completed.current.delete(manifest.chapter.id))
  }, [manifest])

  const forward = useCallback(() => {
    if (!manifest) return
    if (strip) {
      window.scrollBy({ top: window.innerHeight * 0.9, behavior: 'smooth' })
      return
    }
    if (atEnd) {
      if (manifest.next) openChapter(manifest.next.id)
      return
    }
    if (step + 1 < groups.length) goTo(groups[step + 1][0])
    else {
      setAtEnd(true)
      finish()
    }
  }, [manifest, strip, atEnd, step, groups, goTo, openChapter, finish])

  const back = useCallback(() => {
    if (!manifest) return
    if (strip) {
      window.scrollBy({ top: -window.innerHeight * 0.9, behavior: 'smooth' })
      return
    }
    if (atEnd) setAtEnd(false)
    else if (step > 0) goTo(groups[step - 1][0])
    else if (manifest.previous) openChapter(manifest.previous.id)
  }, [manifest, strip, atEnd, step, groups, goTo, openChapter])

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
    else void document.documentElement.requestFullscreen().catch(() => undefined)
  }, [])

  useReaderKeys({
    left: rtl ? forward : back,
    right: rtl ? back : forward,
    forward,
    back,
    previousChapter: () => manifest?.previous && openChapter(manifest.previous.id),
    nextChapter: () => manifest?.next && openChapter(manifest.next.id),
    fullscreen: toggleFullscreen,
    escape: () => setPanel(null),
  })

  // A paged mode shows each page from its top; the browser would otherwise
  // keep the scroll offset of a tall page on the next one.
  useEffect(() => {
    if (!strip) window.scrollTo({ top: 0 })
  }, [page, atEnd, strip])

  const visibleLast = groups[step]?.at(-1) ?? page
  const preload = useMemo(() => {
    if (!manifest) return []
    const urls: string[] = []
    for (let index = visibleLast + 1; index <= visibleLast + PRELOAD_AHEAD && index < manifest.page_count; index++) {
      urls.push(readerPageUrl(manifest.chapter.id, index))
    }
    if (manifest.next && manifest.page_count - visibleLast <= PRELOAD_AHEAD) {
      for (let index = 0; index < PRELOAD_AHEAD; index++) urls.push(readerPageUrl(manifest.next.id, index))
    }
    return urls
  }, [manifest, visibleLast])
  usePreload(preload)

  if (notFound) return <ReaderMessage title="This chapter no longer exists" backTo="/library" />
  if (error && !manifest) return <ReaderMessage title="This chapter cannot be read" detail={error} backTo="/library" />
  if (!manifest || !prefs) return <ReaderMessage title="Opening…" backTo="/library" />

  function onZone(zone: Zone) {
    if (zone === 'center') setChromeVisible((visible) => !visible)
    else if (zone === 'left') (rtl ? forward : back)()
    else (rtl ? back : forward)()
  }

  const end = (
    <EndOfChapter
      current={manifest.chapter}
      next={manifest.next}
      seriesId={manifest.series.id}
      onNext={() => manifest.next && openChapter(manifest.next.id)}
    />
  )

  return (
    <main className={`min-h-screen w-full ${BACKGROUND[prefs.background]}`}>
      {strip ? (
        <StripView
          chapterId={manifest.chapter.id}
          pageCount={manifest.page_count}
          scale={prefs.scale}
          initialPage={page}
          onPage={(index) => {
            setPage(index)
            save(index)
          }}
          onEnd={finish}
          onTap={() => setChromeVisible((visible) => !visible)}
          end={end}
        />
      ) : atEnd ? (
        <div onClick={() => setChromeVisible((visible) => !visible)}>{end}</div>
      ) : (
        <PagedView chapterId={manifest.chapter.id} group={groups[step] ?? [page]} scale={prefs.scale} rtl={rtl} onZone={onZone} />
      )}
      {/* Task 13 mounts the tablet and desktop chrome and the panels here. */}
    </main>
  )
}
```

The `eslint-disable` comment follows the same rule as in `StripView`: keep it only if the repo lints.

- [ ] **Step 4: Build and verify**

Run (from `frontend/`): `npm run build && for c in 'aspect-\[2\/3\]' 'min-h-\[50vh\]' 'min-h-\[60vh\]' 'bg-reader-gray' 'bg-reader-white' 'w-1\/2' 'max-w-3xl' 'max-h-screen'; do grep -q "$c" dist/assets/*.css && echo "ok $c" || echo "MISSING $c"; done`
Expected: build passes and every line prints `ok`.

Then do a manual check with the stack running (`npm run dev`, API on `:8000`):
- Open `/read/<id>` of a downloaded chapter.
- Arrow keys and clicks on the outer thirds turn pages.
- The last page leads to "End of Ch. N".
- Reloading keeps the page.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/reader
git commit -m "feat(web): read a chapter paged, double or as a long strip"
```

---

### Task 13: Reader chrome — tablet, desktop, slider, settings and chapters panels

**Files:**
- Create in `frontend/src/features/reader/`: `PageSlider.tsx`, `ReaderSheet.tsx`, `SettingsPanel.tsx`, `ChapterPanel.tsx`, `TabletChrome.tsx`, `DesktopChrome.tsx`
- Modify: `frontend/src/features/reader/ReaderPage.tsx`

**Interfaces:**
- Consumes: `ReaderPage` state from Task 12; `Tabs` and `Button` from `ui`; `useScrollLock` from `ui/useScrollLock`.

- [ ] **Step 1: Slider and sheet**

Create `frontend/src/features/reader/PageSlider.tsx`:

```tsx
export function PageSlider({
  page,
  pageCount,
  rtl,
  onSeek,
}: {
  page: number
  pageCount: number
  rtl: boolean
  onSeek: (page: number) => void
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-space-sm rounded-full bg-surface-container-highest px-space-md py-space-xs">
      <span className="w-8 text-right font-mono text-label-sm text-on-surface">{page + 1}</span>
      <input
        type="range"
        min={0}
        max={Math.max(pageCount - 1, 0)}
        value={page}
        // The slider runs the way the pages do, so dragging toward the end of
        // a right-to-left chapter means dragging left.
        dir={rtl ? 'rtl' : 'ltr'}
        aria-label="Page"
        onChange={(event) => onSeek(Number(event.target.value))}
        className="min-w-0 flex-1 accent-primary"
      />
      <span className="w-8 font-mono text-label-sm text-on-surface-variant">{pageCount}</span>
    </div>
  )
}
```

Create `frontend/src/features/reader/ReaderSheet.tsx`:

```tsx
import type { ReactNode } from 'react'

import { Icon } from '../../ui'
import { useScrollLock } from '../../ui/useScrollLock'

/** A bottom sheet below xl, where a thumb reaches it; a centred panel above. */
export function ReaderSheet({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useScrollLock(true)
  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-surface-container-lowest/70 xl:items-center"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-[85vh] w-full flex-col overflow-hidden rounded-t-xl bg-surface-container shadow-overlay xl:max-w-lg xl:rounded-xl"
      >
        <div className="flex items-center justify-between px-space-lg py-space-md">
          <h2 className="text-headline-sm text-on-surface">{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-lg p-space-xs text-outline hover:bg-surface-container-high hover:text-on-surface">
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-space-lg pb-space-lg">{children}</div>
      </div>
    </div>
  )
}
```

Check that `useScrollLock`'s export takes `(active: boolean)`; per `ui/useScrollLock.ts:47` it does.

- [ ] **Step 2: Settings and chapters panels**

Create `frontend/src/features/reader/SettingsPanel.tsx`:

```tsx
import { useState } from 'react'

import type { ReaderBackground, ReaderMode, ReaderPrefs, ReaderScale } from '../../lib/api'
import { Button, Tabs } from '../../ui'
import { ReaderSheet } from './ReaderSheet'

const MODES: { value: ReaderMode; label: string }[] = [
  { value: 'paged_rtl', label: 'Paged (right to left)' },
  { value: 'paged_ltr', label: 'Paged (left to right)' },
  { value: 'double', label: 'Double page' },
  { value: 'long_strip', label: 'Long strip' },
]

const SCALES: { value: ReaderScale; label: string }[] = [
  { value: 'fit_screen', label: 'Fit screen' },
  { value: 'fit_width', label: 'Fit width' },
  { value: 'fit_height', label: 'Fit height' },
]

const BACKGROUNDS: { value: ReaderBackground; label: string }[] = [
  { value: 'black', label: 'Black' },
  { value: 'gray', label: 'Gray' },
  { value: 'white', label: 'White' },
]

function OptionGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <fieldset className="flex flex-col pt-space-md">
      <legend className="pb-space-sm text-label-md text-on-surface-variant">{label}</legend>
      <div className="flex flex-wrap gap-space-sm">
        {options.map((option) => {
          const selected = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
              className={`rounded-lg border px-space-md py-space-sm text-body-md transition-colors ${
                selected
                  ? 'border-primary bg-primary/[0.12] text-primary'
                  : 'border-outline-variant text-on-surface hover:bg-surface-container-high'
              }`}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

export function SettingsPanel({
  prefs,
  error,
  onChange,
  onMakeDefault,
  onClose,
}: {
  prefs: ReaderPrefs
  error: string | null
  onChange: (next: Omit<ReaderPrefs, 'custom'>) => void
  onMakeDefault: () => void
  onClose: () => void
}) {
  const [tab, setTab] = useState<'layout' | 'image'>('layout')
  const { mode, scale, background } = prefs

  return (
    <ReaderSheet title="Reader settings" onClose={onClose}>
      <Tabs
        options={[
          { value: 'layout', label: 'Layout' },
          { value: 'image', label: 'Image' },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'layout' ? (
        <OptionGroup label="Reading mode" options={MODES} value={mode} onChange={(next) => onChange({ mode: next, scale, background })} />
      ) : (
        <>
          <OptionGroup label="Scale" options={SCALES} value={scale} onChange={(next) => onChange({ mode, scale: next, background })} />
          <OptionGroup
            label="Background"
            options={BACKGROUNDS}
            value={background}
            onChange={(next) => onChange({ mode, scale, background: next })}
          />
        </>
      )}
      <div className="mt-space-lg flex flex-wrap items-center justify-between gap-space-sm border-t border-outline-variant pt-space-md">
        <p className="text-body-sm text-on-surface-variant">
          {prefs.custom ? 'Saved for this series.' : 'Following the default for every series.'}
        </p>
        <Button size="sm" onClick={onMakeDefault}>
          Use for every series
        </Button>
      </div>
      {error && <p className="mt-space-sm text-body-sm text-error">{error}</p>}
    </ReaderSheet>
  )
}
```

Create `frontend/src/features/reader/ChapterPanel.tsx`:

```tsx
import { useCallback } from 'react'

import { api } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { Button } from '../../ui'
import { ReaderSheet } from './ReaderSheet'

export function ChapterPanel({
  seriesId,
  currentId,
  onOpen,
  onClose,
}: {
  seriesId: number
  currentId: number
  onOpen: (chapterId: number) => void
  onClose: () => void
}) {
  const load = useCallback(() => api.readerChapters(seriesId), [seriesId])
  const { data, error, reload } = useAsyncData(load)

  return (
    <ReaderSheet title="Chapters" onClose={onClose}>
      {!data && !error && <p className="text-body-md text-on-surface-variant">Loading…</p>}
      {!data && error && (
        <div className="flex flex-col items-start gap-space-sm">
          <p className="text-body-md text-error">{error}</p>
          <Button size="sm" onClick={reload}>
            Try again
          </Button>
        </div>
      )}
      {data && (
        <ul className="flex flex-col">
          {[...data].reverse().map((chapter) => {
            const current = chapter.id === currentId
            return (
              <li key={chapter.id}>
                <button
                  type="button"
                  aria-current={current ? 'true' : undefined}
                  onClick={() => onOpen(chapter.id)}
                  className={`flex w-full items-center gap-space-sm rounded-lg px-space-sm py-space-sm text-left transition-colors ${
                    current ? 'bg-primary/[0.12] text-primary' : 'text-on-surface hover:bg-surface-container-high'
                  }`}
                >
                  <span className="font-mono text-label-md">Ch. {formatChapter(chapter.number)}</span>
                  {chapter.title && <span className="min-w-0 flex-1 truncate text-body-sm text-on-surface-variant">{chapter.title}</span>}
                  {chapter.state !== 'downloaded' && (
                    <span className="ml-auto shrink-0 font-mono text-label-sm text-outline">streams</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </ReaderSheet>
  )
}
```

- [ ] **Step 3: Tablet and desktop chrome**

Create `frontend/src/features/reader/TabletChrome.tsx`:

```tsx
import { Link } from 'react-router-dom'

import type { ReaderManifest } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Icon } from '../../ui'
import type { Panel } from './ReaderPage'
import { PageSlider } from './PageSlider'

const ROUND =
  'inline-flex h-11 w-11 items-center justify-center rounded-full bg-surface-container-highest text-on-surface disabled:opacity-40'

export function TabletChrome({
  manifest,
  page,
  rtl,
  visible,
  onSeek,
  onOpenChapter,
  onPanel,
}: {
  manifest: ReaderManifest
  page: number
  rtl: boolean
  visible: boolean
  onSeek: (page: number) => void
  onOpenChapter: (chapterId: number) => void
  onPanel: (panel: Panel) => void
}) {
  if (!visible) return null
  const { chapter, previous, next } = manifest
  return (
    <div className="xl:hidden">
      <header className="fixed inset-x-0 top-0 z-30 flex items-center gap-space-md bg-surface-container/95 px-space-md py-space-sm">
        <Link to={`/series/${manifest.series.id}`} aria-label="Back to the series" className="rounded-lg p-space-xs text-on-surface">
          <Icon name="arrow_back" className="h-6 w-6" />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="truncate text-title-md text-on-surface">{manifest.series.title}</p>
          <p className="truncate text-body-sm text-on-surface-variant">
            Ch. {formatChapter(chapter.number)}
            {chapter.title ? ` - ${chapter.title}` : ''}
          </p>
        </div>
      </header>
      <footer className="fixed inset-x-0 bottom-0 z-30 flex flex-col gap-space-sm bg-surface-container/95 px-space-md pb-space-md pt-space-sm">
        {manifest.origin === 'stream' && (
          <p className="text-center text-body-sm text-on-surface-variant">
            Streaming from the source. Saved to the library once every page has loaded.
          </p>
        )}
        <div className="flex items-center gap-space-sm">
          <button type="button" aria-label="Previous chapter" disabled={!previous} onClick={() => previous && onOpenChapter(previous.id)} className={ROUND}>
            <Icon name="chevron_left" className="h-5 w-5" />
          </button>
          <PageSlider page={page} pageCount={manifest.page_count} rtl={rtl} onSeek={onSeek} />
          <button type="button" aria-label="Next chapter" disabled={!next} onClick={() => next && onOpenChapter(next.id)} className={ROUND}>
            <Icon name="chevron_right" className="h-5 w-5" />
          </button>
        </div>
        <div className="flex justify-around">
          <button type="button" aria-label="Chapters" onClick={() => onPanel('chapters')} className="rounded-lg p-space-sm text-on-surface">
            <Icon name="list" className="h-6 w-6" />
          </button>
          <button type="button" aria-label="Reader settings" onClick={() => onPanel('settings')} className="rounded-lg p-space-sm text-on-surface">
            <Icon name="settings" className="h-6 w-6" />
          </button>
        </div>
      </footer>
    </div>
  )
}
```

Create `frontend/src/features/reader/DesktopChrome.tsx`:

```tsx
import { Link } from 'react-router-dom'

import type { ReaderManifest } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Icon, type IconName } from '../../ui'
import type { Panel } from './ReaderPage'
import { PageSlider } from './PageSlider'

const TOOL =
  'inline-flex h-10 w-10 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface'

function ToolButton({ icon, label, onClick }: { icon: IconName; label: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className={TOOL}>
      <Icon name={icon} className="h-5 w-5" />
    </button>
  )
}

export function DesktopChrome({
  manifest,
  page,
  rtl,
  strip,
  onSeek,
  onOpenChapter,
  onPanel,
  onFullscreen,
}: {
  manifest: ReaderManifest
  page: number
  rtl: boolean
  strip: boolean
  onSeek: (page: number) => void
  onOpenChapter: (chapterId: number) => void
  onPanel: (panel: Panel) => void
  onFullscreen: () => void
}) {
  const { chapter, previous, next } = manifest
  return (
    <div className="hidden xl:block">
      <div className="fixed left-1/2 top-space-md z-30 flex -translate-x-1/2 items-center gap-space-sm rounded-full bg-surface-container/90 px-space-sm py-space-xs shadow-card">
        <ToolButton icon="chevron_left" label="Previous chapter ([)" onClick={() => previous && onOpenChapter(previous.id)} />
        <span className="font-mono text-label-md text-on-surface">Ch. {formatChapter(chapter.number)}</span>
        <ToolButton icon="chevron_right" label="Next chapter (])" onClick={() => next && onOpenChapter(next.id)} />
      </div>

      <nav className="fixed right-space-md top-1/2 z-30 flex -translate-y-1/2 flex-col gap-space-xs rounded-lg bg-surface-container/90 p-space-xs shadow-card">
        <Link to="/" aria-label="Home" title="Home" className={TOOL}>
          <Icon name="home" className="h-5 w-5" />
        </Link>
        <Link to={`/series/${manifest.series.id}`} aria-label="Series" title="Series" className={TOOL}>
          <Icon name="book" className="h-5 w-5" />
        </Link>
        <ToolButton icon="list" label="Chapters" onClick={() => onPanel('chapters')} />
        <ToolButton icon="settings" label="Reader settings" onClick={() => onPanel('settings')} />
        <ToolButton icon="fullscreen" label="Fullscreen (f)" onClick={onFullscreen} />
      </nav>

      {manifest.origin === 'stream' && (
        <p className="fixed left-space-md top-space-md z-30 max-w-xs rounded-lg bg-surface-container/90 px-space-sm py-space-xs text-body-sm text-on-surface-variant">
          Streaming from the source. Saved to the library once every page has loaded.
        </p>
      )}

      {!strip && (
        <div className="fixed bottom-space-md left-1/2 z-30 w-full max-w-xl -translate-x-1/2">
          <PageSlider page={page} pageCount={manifest.page_count} rtl={rtl} onSeek={onSeek} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Mount chrome and panels in `ReaderPage`**

In `ReaderPage.tsx`, add the imports: `ChapterPanel`, `DesktopChrome`, `SettingsPanel`, `TabletChrome`. Then add the preference handlers inside the component, before the early returns:

```tsx
  const [prefsError, setPrefsError] = useState<string | null>(null)

  const changePrefs = useCallback(
    (next: Omit<ReaderPrefs, 'custom'>) => {
      if (!manifest || !prefs) return
      const before = prefs
      setPrefs({ ...next, custom: true })
      setPrefsError(null)
      api
        .saveReaderPrefs(manifest.series.id, next)
        .then(setPrefs)
        .catch((failure: unknown) => {
          setPrefs(before)
          setPrefsError(failure instanceof Error ? failure.message : 'Could not save.')
        })
    },
    [manifest, prefs],
  )

  const makeDefault = useCallback(() => {
    if (!prefs) return
    const { mode: m, scale, background } = prefs
    setPrefsError(null)
    api.saveReaderDefaults({ mode: m, scale, background }).catch((failure: unknown) => {
      setPrefsError(failure instanceof Error ? failure.message : 'Could not save.')
    })
  }, [prefs])
```

Replace the placeholder comment in the returned JSX with:

```tsx
      <TabletChrome
        manifest={manifest}
        page={page}
        rtl={rtl}
        visible={chromeVisible}
        onSeek={goTo}
        onOpenChapter={openChapter}
        onPanel={setPanel}
      />
      <DesktopChrome
        manifest={manifest}
        page={page}
        rtl={rtl}
        strip={strip}
        onSeek={goTo}
        onOpenChapter={openChapter}
        onPanel={setPanel}
        onFullscreen={toggleFullscreen}
      />
      {panel === 'settings' && (
        <SettingsPanel prefs={prefs} error={prefsError} onChange={changePrefs} onMakeDefault={makeDefault} onClose={() => setPanel(null)} />
      )}
      {panel === 'chapters' && (
        <ChapterPanel
          seriesId={manifest.series.id}
          currentId={manifest.chapter.id}
          onOpen={(id) => {
            setPanel(null)
            openChapter(id)
          }}
          onClose={() => setPanel(null)}
        />
      )}
```

In the strip view, a seek from the slider has to scroll to the page rather than only set state. `DesktopChrome` hides the slider in strip mode, but the tablet slider still shows. Give the tablet slider an `onSeek` that scrolls in strip mode:

```tsx
        onSeek={(index) =>
          strip
            ? document.querySelector(`[data-index="${index}"]`)?.scrollIntoView()
            : goTo(index)
        }
```

- [ ] **Step 5: Build and verify**

Run (from `frontend/`): `npm run build && for c in 'bg-surface-container\/95' 'bg-surface-container\/90' 'max-h-\[85vh\]' 'xl\\:max-w-lg' 'xl\\:rounded-xl' 'xl\\:items-center' 'rounded-t-xl' 'h-11' 'accent-primary' 'top-space-md' 'right-space-md' 'bottom-space-md' 'left-space-md' 'bg-surface-container-lowest\/70'; do grep -q "$c" dist/assets/*.css && echo "ok $c" || echo "MISSING $c"; done`
Expected: build passes and every line prints `ok`. If one is missing:
- An opacity off the scale needs brackets, e.g. `/[0.7]`.
- An inset token that does not generate means spacing tokens do not extend `inset` in this config. Switch to `top-4`-style standard steps, which still come from Tailwind's scale and are not literals.

- [ ] **Step 6: Manual verification**

Run with the stack up (`docker compose up -d` plus `npm run dev`), using the in-app browser:
1. At width 375 (phone):
   - The top bar and footer appear.
   - Tapping the centre hides and shows them.
   - The slider seeks.
   - The settings sheet rises from the bottom.
2. At width 768 (tablet): the same layout as on the phone. At 1440 (desktop):
   - The pill and the icon bar appear, and the top bar does not.
   - `f` toggles fullscreen.
   - `[` and `]` change chapter.
3. For each of the four modes:
   - Switching applies immediately and survives a reload, and the series shows "Saved for this series".
   - In RTL, ← goes forward.
   - Double opens with the cover alone.
   - Long strip scrolls and saves the page.
4. On an undownloaded chapter:
   - The streaming note shows.
   - After reading every page, `download_chapter` with `from_cache` appears on Downloads, and the chapter becomes Downloaded.
5. Reaching the end calls `/complete` once, visible in the network panel, and the list moves forward.
6. A failing page (block one image URL in devtools) shows the retry placeholder, and the rest of the chapter reads.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/reader
git commit -m "feat(web): tablet and desktop reader chrome with settings and chapter panels"
```

---

### Task 14: Documentation

**Files:**
- Modify: `docs/features.md`, `docs/configuration.md`, `docs/data-model.md`, `docs/architecture.md`, `docs/jobs.md`, `CLAUDE.md`

- [ ] **Step 1: Write the changes**

| File | Change |
|---|---|
| `docs/features.md`, "Reading" (around line 222) | Replace the paragraph saying no reader ships. Describe the reader: any chapter, streamed when not downloaded and saved as it is read; four modes; per-series settings; resume. State that Komga and Mihon remain valid readers and that progress converges through the lists. Update the diagram at line 10 if it says Komga is the only reader. |
| `docs/configuration.md`, "Reading on your phone" (around line 192) | Remove "syncs both ways". State the flows: the reader moves the lists, and Komga when indexed; Komga moves the lists through `progress_push`; `komga_scan` brings Komga up to the lists. Mention `READER_CACHE_PATH` and that `api` now runs as `PUID:PGID`. |
| `docs/data-model.md` | Add `reading_position`, `series_reader_pref`, `chapter_page_list`; `chapter.state = streaming`; `progress_event.source = reader`. |
| `docs/architecture.md` | `api` now reaches source sites for the reader, with one slot per site of its own. Describe the `reader-cache` volume and why `worker-download` stays the only writer of `/manga`. Update the services table line for komga ("the library server and reader"): Komga is one reader of several. |
| `docs/jobs.md` | `download_chapter` with `from_cache`; `komga_read_progress`; cache pruning in the download lane's reclaim pass; `komga_scan` marking books read up to list progress. |
| `CLAUDE.md` | In "Rebuilding after a code change" and the lane notes, say `api` and `worker-download` share the `reader-cache` volume. Add to the module boundaries that `app/reader/` is pure, like `downloader/`. |

Write in the existing voice of each file: say why, not what.

- [ ] **Step 2: Verify**

Run: `grep -n "ships no reader\|no reader\|syncs both ways" docs/*.md`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs: describe the reader, the cache and how progress converges"
```

---

## Final verification

- [ ] `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q` (from `backend/`): every test passes.
- [ ] `.venv/bin/python -m ruff check app/ tests/`: clean.
- [ ] `npm run build` (from `frontend/`): passes.
- [ ] Rebuild the stack and repeat the Task 13 manual pass once:

```bash
docker compose build api && docker compose up -d --force-recreate api worker worker-download web
```
