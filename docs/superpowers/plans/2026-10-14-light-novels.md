# Light Novels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A light novel on a MyAnimeList or AniList list is matched against a prose source, its chapters are downloaded as one EPUB per chapter, and Komga serves them for reading. Reading progress flows back to the lists.

**Architecture:** `series.kind` (`comic` / `prose` / null) routes each series. A `ProseSource` contract sits beside the image `Source`; both share `search` and `list_chapters`, and only the content call differs (`fetch_chapter` returns sanitised XHTML plus image refs). The download handlers branch once at the archive write: CBZ for comics, a hand-rolled EPUB 3 writer for prose. Komga's library gets `scanEpub: true`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Alembic, httpx, selectolax 0.4, pytest + pytest-asyncio; React + TypeScript + Tailwind 4 frontend.

**Spec:** `docs/superpowers/specs/2026-10-14-light-novels-design.md`. Read it before starting any task.

## Global Constraints

- Commits: English, one focused change per commit, **no assistant attribution of any kind** (no `Co-Authored-By`, no "Generated with" line). The user's global `CLAUDE.md` overrides any harness reminder that says otherwise.
- Work happens on branch `feat/light-novels`, which already holds the spec commit.
- Tests run against a throwaway Postgres. Start one per worktree:
  `docker run -d --name manga-pg-ln -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5434:5432 postgres:17-alpine`
  and run every pytest command below as `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest ...` from `backend/`.
- Lint after every task: `.venv/bin/python -m ruff check app/ tests/` from `backend/`.
- `sources/`, `downloader/` and `komga/` never touch the database. `sources/` never imports from `downloader/`.
- asyncpg cannot infer the type of a null parameter: write `cast(:x as text)` wherever a bound value may be null.
- Comments explain why a line exists, never what it does. Match the surrounding comment density.
- Content language: English only. No new third-party dependency (selectolax, httpx, stdlib `zipfile` and `xml.etree` cover everything).
- Kind values are exactly the strings `"comic"` and `"prose"`. Null means unknown and behaves as `"comic"` everywhere.
- Frontend: no hex, px or rem literal in a component; every new Tailwind class must be found by `grep` in `frontend/dist/` after `npm run build`. Feature folders never import from each other.

## Review Focus

1. **A chapter locked behind a paywall or app.** lolobun locks most chapters (569 of 589 on the recorded book), and a locked page returns a short teaser, not a 404. Expected: the chapter is marked `skipped` with "locked" in the job log, and the batch carries on. Never ship a teaser as a chapter. Pinned in Task 12 (`test_a_locked_chapter_is_unavailable_not_a_teaser`).
2. **A series whose kind is corrected after files exist.** Expected: switching a series between comic and prose does not redownload chapters whose file exists with the other extension. Pinned in Task 5 (`test_existing_chapter_file_finds_either_extension`) and Task 11 (`test_a_prose_batch_skips_a_chapter_already_on_disk_as_cbz`).
3. **Opening a prose chapter in the image reader** (a bookmark, or an old link). Expected: a clear 409 telling the user to read it in Komga, not a 500 or a zip of EPUB internals rendered as pages. Pinned in Task 10.
4. **Hostile or messy chapter HTML**: scripts, inline handlers, `&nbsp;`-only paragraphs, control characters, nested `div`s, unknown tags. Expected: the output is valid XML that Komga's reader opens, and the text survives. Pinned in Task 4 (`test_control_characters_are_removed_so_the_xml_parses`, `test_unknown_tags_are_unwrapped_and_their_text_kept`).
5. **The source search returning comics alongside novels** (lolobun's search endpoint mixes them). Expected: a prose source offers only prose candidates, so a novel is never mapped to a comic URL. Pinned in Task 12 (`test_search_offers_novels_only`).

---

## File Structure

**Create:**
- `backend/alembic/versions/0019_series_kind.py`: the `series.kind` column and its backfill.
- `backend/alembic/versions/0020_seed_prose_sources.py`: catalogue rows for the three native prose sources.
- `backend/app/sources/prose.py`: `clean_chapter_html`, the shared sanitiser.
- `backend/app/sources/lolobun.py`, `backend/app/sources/novelight.py`, `backend/app/sources/empirenovel.py`: the three sources.
- `backend/app/downloader/epub.py`: `EpubChapter`, `write_epub`.
- `backend/app/downloader/prose_fetch.py`: `fetch_prose_chapter` (text plus image bytes).
- `backend/app/handlers/prose_download.py`: `write_prose_chapter`, shared by both download handlers.
- `frontend/src/features/series/KindControl.tsx`: the comic/prose selector.
- Tests: `tests/test_series_kind_migration.py`, `tests/test_series_kind_sync.py`, `tests/test_prose_contract.py`, `tests/test_prose_clean.py`, `tests/test_epub.py`, `tests/test_prose_fetch.py`, `tests/test_prose_download.py`, `tests/test_series_kind_api.py`, `tests/test_source_lolobun.py`, `tests/test_source_novelight.py`, `tests/test_source_empirenovel.py`, plus fixtures under `tests/fixtures/sources/`.

**Modify:**
- `backend/app/models.py`: `Series.kind`.
- `backend/app/handlers/list_sync.py`: `series_kind_column`, `refresh_series_kind`, called from `handle`.
- `backend/app/sources/base.py`, `backend/app/sources/__init__.py`: the contract split and narrowed getters.
- `backend/app/sources/registry.py`: register the prose natives.
- `backend/app/downloader/paths.py`: kind-aware filenames, `existing_chapter_file`.
- `backend/app/komga/client.py`: `scanEpub: True`, reconcile in `ensure_library`.
- `backend/app/handlers/match_search.py`: search same-kind sources only.
- `backend/app/handlers/download_batch.py`, `backend/app/handlers/download_chapter.py`: the prose branch.
- `backend/app/handlers/chapter_discover.py`: disk reconcile finds either extension.
- `backend/app/worker/main.py`: the library mount guard counts `.epub` too.
- `backend/app/api/routes_series.py`: `kind` in payloads, `POST /{id}/kind`, mapping guard.
- `backend/app/api/reader_service.py`, `backend/app/api/routes_reader.py`: refuse prose chapters.
- `frontend/src/lib/api.ts`, `frontend/src/features/series/SeriesHeader.tsx`, `frontend/src/features/series/SeriesDetailPage.tsx`, `frontend/src/features/series/useSeriesDetail.ts`, `frontend/src/features/series/ChapterTable.tsx`.
- Docs: `docs/architecture.md`, `docs/data-model.md`, `docs/features.md`, `CLAUDE.md`.

---

### Task 1: `series.kind` column and backfill

**Files:**
- Create: `backend/alembic/versions/0019_series_kind.py`
- Modify: `backend/app/models.py` (class `Series`, after `review_ignored_at`)
- Test: `backend/tests/test_series_kind_migration.py`

**Interfaces:**
- Produces: column `series.kind text null`, check constraint `kind in ('comic','prose')`; ORM attribute `Series.kind: Mapped[str | None]`.

- [ ] **Step 1: Write the failing test**

The test drives the migration's own logic by downgrading to `0018_reader` and upgrading again, the way `test_split_prose_from_comic_migration.py` does.

```python
"""0019 backfills series.kind from what each entry's provider said.

Run against a real database through alembic itself, so the test exercises the
migration's own SQL rather than a copy of it.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
BEFORE = "0018_reader"


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], check=True, capture_output=True, cwd=BACKEND
    )


@pytest.fixture
async def at_head():
    """Leave the database at head however the test ends, for the modules after it."""
    yield
    alembic("upgrade", "head")


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate list_entry, series, chapter restart identity cascade")
        )
        await session.commit()
    yield


async def _series(session, slug: str, entries: list[tuple[str, dict]]) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:t, :slug, false, '{}'::jsonb) returning id"
            ),
            {"t": slug, "slug": slug},
        )
    ).scalar_one()
    for index, (provider, raw) in enumerate(entries):
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, status, raw,
                                        updated_at)
                values (:p, :m, :s, 'reading', cast(:raw as jsonb), now())
                """
            ),
            {"p": provider, "m": f"{slug}-{index}", "s": series_id, "raw": json.dumps(raw)},
        )
    return int(series_id)


async def test_backfill_reads_each_providers_own_kind(at_head):
    alembic("downgrade", BEFORE)
    async with get_sessionmaker()() as session:
        ids = {
            "mal_ln": await _series(
                session, "mal-ln", [("mal", {"node": {"media_type": "light_novel"}})]
            ),
            "anilist_novel": await _series(
                session, "anilist-novel", [("anilist", {"media": {"format": "NOVEL"}})]
            ),
            "baka_novel": await _series(
                session, "baka-novel", [("mangabaka", {"Series": {"type": "Novel"}})]
            ),
            "mixed": await _series(
                session,
                "mixed",
                [
                    ("mal", {"node": {"media_type": "novel"}}),
                    ("anilist", {"media": {"format": "MANGA"}}),
                ],
            ),
            "manhwa": await _series(
                session, "manhwa", [("mal", {"node": {"media_type": "manhwa"}})]
            ),
            "silent": await _series(session, "silent", [("local", {})]),
            "one_shot": await _series(
                session, "one-shot", [("anilist", {"media": {"format": "ONE_SHOT"}})]
            ),
        }
        await session.commit()

    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select id, kind from series"))).all()
    kinds = {row.id: row.kind for row in rows}
    assert kinds[ids["mal_ln"]] == "prose"
    assert kinds[ids["anilist_novel"]] == "prose"
    assert kinds[ids["baka_novel"]] == "prose"
    # Mixed resolves to comic, the safe direction from issue #88.
    assert kinds[ids["mixed"]] == "comic"
    assert kinds[ids["manhwa"]] == "comic"
    assert kinds[ids["silent"]] is None
    # ONE_SHOT is in neither vocabulary, so the series stays unknown.
    assert kinds[ids["one_shot"]] is None


async def test_kind_rejects_values_outside_the_vocabulary():
    async with get_sessionmaker()() as session:
        with pytest.raises(Exception, match="series_kind_check"):
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('x', 'x', false, '{}'::jsonb, 'audio')"
                )
            )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_series_kind_migration.py -q`
Expected: FAIL. `column "kind" does not exist`.

- [ ] **Step 3: Write the migration**

`backend/alembic/versions/0019_series_kind.py`:

```python
"""series.kind: comic or prose, so a light novel stops being searched as a manga

Revision ID: 0019_series_kind
Revises: 0018_reader
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_series_kind"
down_revision: str | None = "0018_reader"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The provider vocabularies are copied here rather than imported from
# app.providers: a migration has to keep meaning what it meant on the day it
# shipped, and the maps in the app are free to grow after that. The rules are
# series_kind_from_entries' rules - any comic entry makes the series a comic,
# because a mixed series is exactly the shape issue #88 found already merged,
# and resolving it to prose would let the corruption compound.
BACKFILL = """
with entry_kind as (
    select series_id,
           case
               when provider = 'mal' then
                   case when raw -> 'node' ->> 'media_type' in ('novel', 'light_novel')
                            then 'prose'
                        when raw -> 'node' ->> 'media_type' in ('manga', 'manhwa', 'manhua', 'oel')
                            then 'comic'
                   end
               when provider = 'anilist' then
                   case when raw -> 'media' ->> 'format' = 'NOVEL' then 'prose'
                        when raw -> 'media' ->> 'format' in ('MANGA', 'MANHWA', 'MANHUA', 'OEL')
                            then 'comic'
                   end
               when provider = 'mangabaka' then
                   case when lower(raw -> 'Series' ->> 'type') = 'novel' then 'prose'
                        when lower(raw -> 'Series' ->> 'type') in ('manga', 'manhwa', 'manhua', 'oel')
                            then 'comic'
                   end
           end as kind
      from list_entry
     where series_id is not null
)
update series s
   set kind = resolved.kind
  from (
      select series_id,
             case when bool_or(kind = 'comic') then 'comic'
                  when bool_or(kind = 'prose') then 'prose'
             end as kind
        from entry_kind
       group by series_id
  ) resolved
 where resolved.series_id = s.id
   and resolved.kind is not null
"""


def upgrade() -> None:
    op.add_column("series", sa.Column("kind", sa.Text(), nullable=True))
    op.create_check_constraint("series_kind_check", "series", "kind in ('comic', 'prose')")
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_constraint("series_kind_check", "series", type_="check")
    op.drop_column("series", "kind")
```

- [ ] **Step 4: Add the ORM attribute**

In `backend/app/models.py`, class `Series`, directly after the `review_ignored_at` column:

```python
    # comic or prose. Null is unknown and behaves as comic, which is what every
    # series did before this column existed. meta.kind_locked marks a value the
    # user chose by hand, which a list sync must not overwrite.
    kind: Mapped[str | None] = mapped_column(String(10))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_series_kind_migration.py tests/test_migration_chain.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0019_series_kind.py backend/app/models.py backend/tests/test_series_kind_migration.py
git commit -m "feat(db): record whether a series is a comic or prose"
```

---

### Task 2: List sync keeps `series.kind` current

**Files:**
- Modify: `backend/app/handlers/list_sync.py` (after `series_kind_from_entries`, and in `handle`)
- Test: `backend/tests/test_series_kind_sync.py`

**Interfaces:**
- Consumes: `series.kind` (Task 1); existing `entry_kind_from_raw(provider, raw)`, `series_kind_from_entries(kinds)`.
- Produces: `series_kind_column(kinds: set[str | None]) -> str | None` (returns `"comic"`, `"prose"` or `None`); `async refresh_series_kind(session: AsyncSession, series_id: int) -> None`.

- [ ] **Step 1: Write the failing test**

```python
"""list_sync keeps series.kind in step with the entries a series holds."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.list_sync import refresh_series_kind, series_kind_column


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate list_entry, series restart identity cascade"))
        await session.commit()
    yield


async def _series(session, *, meta: dict | None = None, kind: str | None = None) -> int:
    return int(
        (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('t', 't', false, cast(:meta as jsonb), cast(:kind as text))"
                    " returning id"
                ),
                {"meta": json.dumps(meta or {}), "kind": kind},
            )
        ).scalar_one()
    )


async def _entry(session, series_id: int, provider: str, media_id: str, raw: dict) -> None:
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, status, raw,
                                    updated_at)
            values (:p, :m, :s, 'reading', cast(:raw as jsonb), now())
            """
        ),
        {"p": provider, "m": media_id, "s": series_id, "raw": json.dumps(raw)},
    )


async def _kind(session, series_id: int) -> str | None:
    return (
        await session.execute(text("select kind from series where id = :id"), {"id": series_id})
    ).scalar_one()


def test_series_kind_column_speaks_the_column_vocabulary():
    assert series_kind_column({"NOVEL"}) == "prose"
    assert series_kind_column({"MANGA", "NOVEL"}) == "comic"
    assert series_kind_column({None}) is None
    assert series_kind_column(set()) is None


async def test_a_novel_entry_makes_its_series_prose():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _entry(session, series_id, "anilist", "1", {"media": {"format": "NOVEL"}})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) == "prose"


async def test_a_comic_entry_joining_turns_the_series_comic():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, kind="prose")
        await _entry(session, series_id, "anilist", "1", {"media": {"format": "NOVEL"}})
        await _entry(session, series_id, "mal", "2", {"node": {"media_type": "manga"}})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) == "comic"


async def test_a_kind_the_user_locked_is_left_alone():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, meta={"kind_locked": True}, kind="prose")
        await _entry(session, series_id, "mal", "1", {"node": {"media_type": "manga"}})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) == "prose"


async def test_entries_that_say_nothing_leave_the_kind_unknown():
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await _entry(session, series_id, "local", "1", {})
        await refresh_series_kind(session, series_id)
        assert await _kind(session, series_id) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_series_kind_sync.py -q`
Expected: FAIL. `ImportError: cannot import name 'refresh_series_kind'`.

- [ ] **Step 3: Implement**

In `backend/app/handlers/list_sync.py`, directly after `series_kind_from_entries`:

```python
# series_kind_from_entries speaks provider vocabulary, which the merge guard
# needs; the column speaks the pipeline's own, which is all a handler routing a
# download needs to know.
_KIND_COLUMN = {"MANGA": "comic", "NOVEL": "prose"}


def series_kind_column(kinds: set[str | None]) -> str | None:
    """The series.kind value for a series holding entries of these kinds."""
    return _KIND_COLUMN.get(series_kind_from_entries(kinds) or "")


async def refresh_series_kind(session: AsyncSession, series_id: int) -> None:
    """Recompute series.kind from every entry the series holds.

    From all of them rather than from the entry that just arrived, so a comic
    entry joining a prose series turns it comic, the safe direction from #88.
    A kind the user set by hand is theirs: a provider that cannot tell a light
    novel from a manga does not get to overrule them on every sync.
    """
    rows = (
        await session.execute(
            text("select provider, raw from list_entry where series_id = :id"),
            {"id": series_id},
        )
    ).all()
    kind = series_kind_column({entry_kind_from_raw(provider, raw) for provider, raw in rows})
    await session.execute(
        text(
            """
            update series
               set kind = cast(:kind as text)
             where id = :id
               and kind is distinct from cast(:kind as text)
               and not coalesce((meta ->> 'kind_locked')::boolean, false)
            """
        ),
        {"id": series_id, "kind": kind},
    )
```

In `handle`, directly after `await upsert_entry(ctx.session, dto, series_id)`:

```python
        await refresh_series_kind(ctx.session, series_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_series_kind_sync.py tests/test_cross_reference_dedupe.py tests/test_local_tracking.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/list_sync.py backend/tests/test_series_kind_sync.py
git commit -m "feat(sync): keep a series' kind in step with its list entries"
```

---

### Task 3: The prose source contract

**Files:**
- Modify: `backend/app/sources/base.py`, `backend/app/sources/__init__.py`
- Test: `backend/tests/test_prose_contract.py`

**Interfaces:**
- Produces (all in `app.sources.base`, re-exported from `app.sources`):
  - `class SiteSource(ABC)`: `site: str`, `domains: tuple[str, ...]`, `kind: ClassVar[str]`, abstract `search`, abstract `list_chapters` (signatures unchanged from today's `Source`).
  - `class Source(SiteSource)`: `kind = "comic"`, abstract `list_pages`, concrete `descramble`. **Name and behaviour unchanged.**
  - `class ProseSource(SiteSource)`: `kind = "prose"`, abstract `async fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText`.
  - `@dataclass(frozen=True) class ChapterText`: `title: str | None`, `body: str`, `images: list[PageRef]`.
  - `def kind_of(source: object) -> str`: `getattr(source, "kind", "comic")`.
  - `def all_sources(kind: str | None = None) -> list[SiteSource]`.
  - `def get_comic_source(site: str) -> Source` and `def get_prose_source(site: str) -> ProseSource`: both raise `TypeError` for the other kind and `ValueError` for an unknown site.
  - `RegisteredSource.source` is typed `SiteSource`.

- [ ] **Step 1: Write the failing test**

```python
"""The prose contract sits beside the image one, and the registry tells them apart."""

import pytest

from app.sources import base


class Comic(base.Source):
    site = "comic-site"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def list_pages(self, chapter_url, *, language="en"):
        return []


class Prose(base.ProseSource):
    site = "prose-site"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        return base.ChapterText(title=None, body="<p>x</p>", images=[])


class DuckTyped:
    """The shape the download tests' fakes take: no base class, no kind."""

    site = "duck"
    domains = ()


@pytest.fixture
def registry():
    base.install_registry(
        {
            "comic-site": base.RegisteredSource(Comic(), "https://comic.test"),
            "prose-site": base.RegisteredSource(Prose(), "https://prose.test"),
            "duck": base.RegisteredSource(DuckTyped(), "https://duck.test"),
        }
    )
    yield
    base.install_registry({})


def test_each_contract_declares_its_kind():
    assert Comic.kind == "comic"
    assert Prose.kind == "prose"
    assert base.kind_of(DuckTyped()) == "comic"


def test_all_sources_filters_by_kind(registry):
    assert {s.site for s in base.all_sources(kind="prose")} == {"prose-site"}
    assert {s.site for s in base.all_sources(kind="comic")} == {"comic-site", "duck"}
    assert len(base.all_sources()) == 3


def test_the_narrowed_getters_refuse_the_other_kind(registry):
    assert isinstance(base.get_prose_source("prose-site"), Prose)
    assert isinstance(base.get_comic_source("comic-site"), Comic)
    with pytest.raises(TypeError, match="prose-site is a prose source"):
        base.get_comic_source("prose-site")
    with pytest.raises(TypeError, match="comic-site is a comic source"):
        base.get_prose_source("comic-site")
    with pytest.raises(ValueError, match="unknown source site"):
        base.get_prose_source("nowhere")


async def test_a_prose_source_returns_chapter_text():
    text = await Prose().fetch_chapter("https://prose.test/c/1")
    assert text == base.ChapterText(title=None, body="<p>x</p>", images=[])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_contract.py -q`
Expected: FAIL. `AttributeError: module 'app.sources.base' has no attribute 'ProseSource'`.

- [ ] **Step 3: Implement**

In `backend/app/sources/base.py`:

1. Change the module docstring's first paragraph to:

```python
"""Contract for a source site, plus the registry that picks one for a URL.

Every source answers which works match a title and which chapters exist at a
URL. What a chapter *is* depends on the kind: a comic source lists page images,
which the downloader fetches; a prose source returns the chapter's text.
"""
```

2. Add `from typing import ClassVar` to the imports.

3. Replace the `class Source(ABC):` block (through the end of `descramble`) with:

```python
@dataclass(frozen=True)
class ChapterText:
    """One prose chapter, already reduced to the XHTML an EPUB can carry.

    Images stay references rather than bytes, so the downloader fetches them
    through the same rate-limited path as comic pages, referer and all. The
    body names them as {{img:N}}, an index into `images`.
    """

    title: str | None
    body: str
    images: list[PageRef] = field(default_factory=list)


class SiteSource(ABC):
    """What every site answers, whatever it publishes."""

    site: str
    domains: tuple[str, ...]
    kind: ClassVar[str]

    @abstractmethod
    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        """Candidates for the review screen, best score first."""

    @abstractmethod
    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        """Every chapter the source publishes for this work."""


class Source(SiteSource):
    """A comic source. The name predates prose sources and stays, so the
    templates and every native comic source keep compiling untouched."""

    kind: ClassVar[str] = "comic"

    @abstractmethod
    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        """Every page image for one chapter, in reading order."""

    def descramble(self, data: bytes, page: PageRef) -> bytes:
        """The bytes a reader should see. Identity for every source but one.

        Concrete rather than abstract: adding it here must not force every
        other source to grow a no-op override. comiciviewer is the only site
        that needs it today.
        """
        return data


class ProseSource(SiteSource):
    """A source that publishes text."""

    kind: ClassVar[str] = "prose"

    @abstractmethod
    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        """The chapter's text. Raises ChapterUnavailable for a chapter the site
        removed or keeps behind a paywall."""


def kind_of(source: object) -> str:
    """A source's kind, with comic as the answer for anything that never said.

    The download tests register duck-typed fakes with no base class at all, and
    every source written before prose existed is a comic one.
    """
    return getattr(source, "kind", "comic")
```

4. In `RegisteredSource`, change `source: Source` to `source: SiteSource`.

5. Replace `get_source` and `all_sources` with:

```python
def get_source(site: str) -> SiteSource:
    if site not in _REGISTRY:
        raise ValueError(f"unknown source site: {site}")
    return _REGISTRY[site].source


def get_comic_source(site: str) -> Source:
    """The source for a site that must publish images.

    Raises rather than returning something that lacks list_pages, so a mapping
    that crossed kinds fails here by name instead of as an AttributeError deep
    in a download.
    """
    source = get_source(site)
    if kind_of(source) != "comic":
        raise TypeError(f"{site} is a {kind_of(source)} source, not a comic one")
    return source  # type: ignore[return-value]


def get_prose_source(site: str) -> ProseSource:
    """The source for a site that must publish text. See get_comic_source."""
    source = get_source(site)
    if not isinstance(source, ProseSource):
        raise TypeError(f"{site} is a {kind_of(source)} source, not a prose one")
    return source


def all_sources(kind: str | None = None) -> list[SiteSource]:
    sources = [entry.source for entry in _REGISTRY.values()]
    if kind is None:
        return sources
    return [source for source in sources if kind_of(source) == kind]
```

6. Change `source_for_url`'s return annotation to `SiteSource`.

In `backend/app/sources/__init__.py`, export the new names:

```python
"""Source sites. The registry is loaded at boot - see registry.reload."""

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    NotConfigured,
    PageRef,
    ProseSource,
    SiteSource,
    Source,
    all_sources,
    get_comic_source,
    get_prose_source,
    get_source,
    kind_of,
    source_for_url,
)
from app.sources.registry import reload

__all__ = [
    "Candidate",
    "ChapterRef",
    "ChapterText",
    "NotConfigured",
    "PageRef",
    "ProseSource",
    "SiteSource",
    "Source",
    "all_sources",
    "get_comic_source",
    "get_prose_source",
    "get_source",
    "kind_of",
    "reload",
    "source_for_url",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_contract.py tests/test_sources_base.py tests/test_source_registry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources/base.py backend/app/sources/__init__.py backend/tests/test_prose_contract.py
git commit -m "feat(sources): add a prose source contract beside the comic one"
```

---

### Task 4: Chapter HTML sanitiser

**Files:**
- Create: `backend/app/sources/prose.py`
- Test: `backend/tests/test_prose_clean.py`

**Interfaces:**
- Consumes: `ChapterUnavailable` (`app.sources.base`).
- Produces: `clean_chapter_html(fragment: str, base_url: str) -> tuple[str, list[str]]`. Returns the XHTML body (a fragment of block elements) and the absolute image URLs in body order. The body references image N as the literal text `{{img:N}}`. Raises `ChapterUnavailable` when no text and no image survive.

- [ ] **Step 1: Write the failing test**

```python
"""clean_chapter_html: whatever a site serves, the output is XHTML an EPUB can carry."""

from xml.etree import ElementTree as ET

import pytest

from app.sources.base import ChapterUnavailable
from app.sources.prose import clean_chapter_html

BASE = "https://site.test/n/1/2"


def _parses(body: str) -> ET.Element:
    return ET.fromstring(f'<body xmlns="http://www.w3.org/1999/xhtml">{body}</body>')


def test_allowlisted_formatting_survives():
    body, _ = clean_chapter_html(
        "<p>One <em>two</em> <strong>three</strong></p><hr><blockquote>q</blockquote>", BASE
    )
    assert body == "<p>One <em>two</em> <strong>three</strong></p><hr/><blockquote>q</blockquote>"
    _parses(body)


def test_scripts_styles_and_attributes_are_dropped():
    body, _ = clean_chapter_html(
        '<p onclick="steal()" style="color:red" class="x">Hi</p>'
        "<script>alert(1)</script><style>p{}</style><iframe src='ad'></iframe>",
        BASE,
    )
    assert body == "<p>Hi</p>"


def test_unknown_tags_are_unwrapped_and_their_text_kept():
    body, _ = clean_chapter_html("<p>a <span><font>b</font></span> <a href='/x'>c</a></p>", BASE)
    assert body == "<p>a b c</p>"


def test_a_div_holding_only_text_becomes_a_paragraph():
    body, _ = clean_chapter_html("<div><div>First</div><div>Second</div></div>", BASE)
    assert body == "<p>First</p><p>Second</p>"


def test_empty_and_nbsp_paragraphs_are_removed():
    body, _ = clean_chapter_html("<p>&nbsp;</p><p> </p><p>Kept</p>", BASE)
    assert body == "<p>Kept</p>"


def test_entities_come_out_as_xml():
    body, _ = clean_chapter_html("<p>Tom &amp; Jerry &lt;3 &hellip;</p>", BASE)
    assert body == "<p>Tom &amp; Jerry &lt;3 …</p>"
    _parses(body)


def test_control_characters_are_removed_so_the_xml_parses():
    body, _ = clean_chapter_html("<p>bad\x0bchar\x00s</p>", BASE)
    assert body == "<p>badchars</p>"
    _parses(body)


def test_images_become_ordered_placeholders_with_absolute_urls():
    body, images = clean_chapter_html(
        '<p>Look <img src="/img/a.png"></p><img data-src="https://cdn.test/b.jpg">', BASE
    )
    assert body == "<p>Look {{img:0}}</p>{{img:1}}"
    assert images == ["https://site.test/img/a.png", "https://cdn.test/b.jpg"]


def test_a_body_with_nothing_left_is_unavailable():
    with pytest.raises(ChapterUnavailable):
        clean_chapter_html("<script>x</script><p>&nbsp;</p>", BASE)


def test_bare_top_level_text_is_wrapped_in_a_paragraph():
    body, _ = clean_chapter_html("Loose text<br>more<p>Para</p>", BASE)
    assert body == "<p>Loose text<br/>more</p><p>Para</p>"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_clean.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.sources.prose'`.

- [ ] **Step 3: Implement**

`backend/app/sources/prose.py`:

```python
"""Reduce a site's chapter HTML to the XHTML an EPUB can carry.

Each source cuts away its own chrome first - ads, navigation, translator
banners - because only it knows what those look like. What is left still comes
from a site nobody here controls, so this keeps an allowlist rather than a
blocklist: a tag nobody thought of is unwrapped, never passed through.
"""

import html
import re
from urllib.parse import urljoin

from selectolax.parser import HTMLParser, Node

from app.sources.base import ChapterUnavailable

INLINE = {"em", "strong", "i", "b"}
BLOCK = {"p", "blockquote", "h1", "h2", "h3", "h4", "ul", "ol", "li"}
VOID = {"br", "hr"}
# Dropped with everything inside them. Unwrapping a script would print its
# source into the chapter.
DROPPED = {"script", "style", "iframe", "noscript", "form", "button", "svg", "nav", "aside",
           "template", "select", "textarea", "input"}
# Containers a site uses for layout. Unwrapped, or turned into a paragraph
# when they hold no block of their own - several sites put each paragraph in
# a bare div, and unwrapping those would run the whole chapter together.
CONTAINERS = {"div", "section", "article", "main", "center"}
# XML 1.0 refuses these outright, and a single one makes the EPUB unreadable.
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_BLOCK_OPEN = re.compile(r"^<(p|blockquote|h[1-4]|ul|ol|li|hr)\b")


def clean_chapter_html(fragment: str, base_url: str) -> tuple[str, list[str]]:
    """The chapter as XHTML, and the image URLs it references, in order."""
    # NUL goes before parsing, not after: selectolax repeats the text that
    # follows one ("a\x00b" parses to "abb"), which no later pass can undo.
    tree = HTMLParser(fragment.replace("\x00", ""))
    root = tree.body or tree.root
    images: list[str] = []
    pieces = _children(root, images, base_url)
    body = "".join(_wrap_loose(pieces)).strip()

    if not _has_content(body):
        raise ChapterUnavailable("the chapter has no text once the page around it is removed")
    return body, images


def _children(node: Node, images: list[str], base_url: str) -> list[str]:
    out: list[str] = []
    for child in node.iter(include_text=True):
        out.extend(_render(child, images, base_url))
    return out


def _render(node: Node, images: list[str], base_url: str) -> list[str]:
    tag = node.tag
    if tag == "-text":
        return [_text(node.text(deep=False))]
    if tag in DROPPED or tag == "_comment":
        return []
    if tag in VOID:
        return [f"<{tag}/>"]
    if tag == "img":
        src = node.attributes.get("data-src") or node.attributes.get("src")
        if not src:
            return []
        images.append(urljoin(base_url, src))
        return [f"{{{{img:{len(images) - 1}}}}}"]

    inner = _children(node, images, base_url)
    if tag in INLINE:
        content = "".join(inner)
        return [f"<{tag}>{content}</{tag}>"] if content.strip() else inner
    if tag in BLOCK:
        content = "".join(inner).strip()
        if tag == "p" and not _has_content(content):
            return []
        return [f"<{tag}>{content}</{tag}>"]
    if tag in CONTAINERS and not any(_BLOCK_OPEN.match(piece) for piece in inner):
        content = "".join(inner).strip()
        return [f"<p>{content}</p>"] if _has_content(content) else []
    return inner


def _text(value: str | None) -> str:
    cleaned = _INVALID_XML.sub("", (value or "").replace("\xa0", " "))
    return html.escape(cleaned, quote=False)


def _wrap_loose(pieces: list[str]) -> list[str]:
    """Wrap runs of top-level inline content in a paragraph.

    Text sitting directly in the chapter container, separated by <br>, is how
    a good half of these sites lay a chapter out.
    """
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        content = "".join(run).strip()
        while content.endswith("<br/>"):
            content = content.removesuffix("<br/>").rstrip()
        if content and (re.sub(r"<[^>]+>", "", content).strip() or "{{img:" in content):
            # A run that is nothing but one image stays bare: an <img> may sit
            # directly in <body>, and wrapping it adds a blank line around it.
            if re.fullmatch(r"\{\{img:\d+\}\}", content):
                out.append(content)
            else:
                out.append(f"<p>{content}</p>")
        run.clear()

    for piece in pieces:
        if _BLOCK_OPEN.match(piece):
            flush()
            out.append(piece)
        else:
            run.append(piece)
    flush()
    return out


def _has_content(markup: str) -> bool:
    if "{{img:" in markup:
        return True
    text_only = re.sub(r"<[^>]+>", "", markup)
    return bool(text_only.strip())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_clean.py -q`
Expected: PASS. If one expectation fails on whitespace only, adjust the implementation, not the test: the test fixes the output format the EPUB writer relies on.

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources/prose.py backend/tests/test_prose_clean.py
git commit -m "feat(sources): reduce chapter HTML to EPUB-safe XHTML"
```

---

### Task 5: Kind-aware chapter paths

**Files:**
- Modify: `backend/app/downloader/paths.py`, `backend/app/worker/main.py:203`
- Test: `backend/tests/test_paths.py` (append)

**Interfaces:**
- Produces:
  - `chapter_filename(series_slug: str, number: Decimal, title: str | None = None, *, kind: str = "comic") -> str`
  - `chapter_path(library_root: Path, series_slug: str, number: Decimal, title: str | None = None, *, kind: str = "comic") -> Path`
  - `existing_chapter_file(library_root: Path, series_slug: str, number: Decimal, title: str | None) -> Path | None`: the first of these that exists: with title / without title, each as `.cbz` and `.epub`.
  - `ARCHIVE_SUFFIXES = (".cbz", ".epub")`
- `number_from_filename` already ignores the extension; a test pins that.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_paths.py`:

```python
from app.downloader.paths import existing_chapter_file


def test_a_prose_chapter_is_an_epub_with_the_same_stem():
    comic = chapter_filename("slug", Decimal("3"), "Title")
    prose = chapter_filename("slug", Decimal("3"), "Title", kind="prose")
    assert comic == "slug - Ch.0003 - Title.cbz"
    assert prose == "slug - Ch.0003 - Title.epub"


def test_the_number_reads_back_from_either_extension():
    assert number_from_filename("slug - Ch.0012.5 - x.epub") == Decimal("12.5")
    assert number_from_filename("slug - Ch.0012.cbz") == Decimal("12")


def test_existing_chapter_file_finds_either_extension(tmp_path):
    cbz = chapter_path(tmp_path, "slug", Decimal("1"), "One")
    cbz.parent.mkdir(parents=True)
    cbz.write_bytes(b"x")
    assert existing_chapter_file(tmp_path, "slug", Decimal("1"), "One") == cbz

    epub = chapter_path(tmp_path, "slug", Decimal("2"), kind="prose")
    epub.write_bytes(b"x")
    # Asked with a title the file was written without: still found.
    assert existing_chapter_file(tmp_path, "slug", Decimal("2"), "Two") == epub

    assert existing_chapter_file(tmp_path, "slug", Decimal("3"), None) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_paths.py -q`
Expected: FAIL. `ImportError: cannot import name 'existing_chapter_file'`.

- [ ] **Step 3: Implement**

In `backend/app/downloader/paths.py`, replace `chapter_filename` and `chapter_path`, and add the new helper after `chapter_path`:

```python
# The stem is the same for both kinds, so ordering, the number parsed back out
# of a Komga filename and the reconcile-by-path logic never learn that two
# formats exist.
_EXTENSIONS = {"comic": "cbz", "prose": "epub"}
ARCHIVE_SUFFIXES = (".cbz", ".epub")


def chapter_filename(
    series_slug: str, number: Decimal, title: str | None = None, *, kind: str = "comic"
) -> str:
    stem = f"{series_slug} - Ch.{format_number(number)}"
    if title:
        safe = safe_component(title)
        if safe:
            stem = f"{stem} - {safe}"
    return f"{stem}.{_EXTENSIONS.get(kind, 'cbz')}"


def chapter_path(
    library_root: Path,
    series_slug: str,
    number: Decimal,
    title: str | None = None,
    *,
    kind: str = "comic",
) -> Path:
    return series_dir(library_root, series_slug) / chapter_filename(
        series_slug, number, title, kind=kind
    )


def existing_chapter_file(
    library_root: Path, series_slug: str, number: Decimal, title: str | None
) -> Path | None:
    """A chapter already in the library, in whichever format it was written.

    Both formats count. A series whose kind is corrected after files exist
    must not redownload a backlog the library already holds, and a file
    written before a title was known carries no title suffix.
    """
    for kind in _EXTENSIONS:
        for candidate_title in (title, None):
            path = chapter_path(library_root, series_slug, number, candidate_title, kind=kind)
            if path.exists():
                return path
    return None
```

In `backend/app/worker/main.py`, replace the line counting archives (currently line 203):

```python
    found = (
        sum(1 for path in library.glob("**/*") if path.suffix in ARCHIVE_SUFFIXES)
        if library.is_dir()
        else 0
    )
```

and add `from app.downloader.paths import ARCHIVE_SUFFIXES` to that module's imports. Update the error message's "holds no archives" wording only if it mentions CBZ; it currently does not.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_paths.py tests/test_library_mount_guard.py tests/test_cbz.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/downloader/paths.py backend/app/worker/main.py backend/tests/test_paths.py
git commit -m "feat(downloader): name prose chapters .epub and find either format on disk"
```

---

### Task 6: EPUB writer

**Files:**
- Create: `backend/app/downloader/epub.py`
- Test: `backend/tests/test_epub.py`

**Interfaces:**
- Consumes: `page_extension` and `place_file` from `app.downloader.cbz`.
- Produces:

```python
@dataclass
class EpubChapter:
    series: str
    number: Decimal
    identifier: str            # f"soshuhen:{series_id}:{number}"
    title: str | None
    body: str                  # ChapterText.body, with {{img:N}} placeholders
    images: list[bytes]        # index-aligned with ChapterText.images
    cover: bytes | None
    language: str = "en"
    authors: list[str] = field(default_factory=list)
    summary: str | None = None

async def write_epub(chapter: EpubChapter, destination: Path) -> None
```

`write_epub` raises `ValueError` when the body references an image index it was not given.

- [ ] **Step 1: Write the failing test**

```python
"""write_epub produces the EPUB 3 package Komga's metadata provider reads."""

import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from app.downloader.epub import EpubChapter, write_epub

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "x": "http://www.w3.org/1999/xhtml",
}


def _chapter(**overrides) -> EpubChapter:
    values = {
        "series": "The Weakest of the Four",
        "number": Decimal("12.5"),
        "identifier": "soshuhen:7:12.5",
        "title": "A Bad Day",
        "body": "<p>Hello {{img:0}}</p><p>Bye &amp; done</p>",
        "images": [PNG],
        "cover": JPEG,
        "authors": ["Mirriad"],
        "summary": "A summary.",
    }
    values.update(overrides)
    return EpubChapter(**values)


async def test_mimetype_comes_first_and_uncompressed(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"


async def test_every_manifest_item_exists_and_the_container_points_at_the_opf(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = container.find(".//c:rootfile", NS).get("full-path")
        assert opf_path == "OEBPS/content.opf"
        opf = ET.fromstring(archive.read(opf_path))
        names = set(archive.namelist())
        for item in opf.findall(".//opf:manifest/opf:item", NS):
            assert f"OEBPS/{item.get('href')}" in names


async def test_the_metadata_is_what_komga_reads(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
    meta = opf.find("opf:metadata", NS)
    assert meta.find("dc:title", NS).text == "The Weakest of the Four - Chapter 12.5: A Bad Day"
    assert meta.find("dc:language", NS).text == "en"
    assert meta.find("dc:creator", NS).text == "Mirriad"
    assert meta.find("dc:description", NS).text == "A summary."
    assert meta.find("dc:identifier", NS).text == "soshuhen:7:12.5"
    collection = meta.find("opf:meta[@property='belongs-to-collection']", NS)
    assert collection.text == "The Weakest of the Four"
    refines = f"#{collection.get('id')}"
    position = meta.find(f"opf:meta[@refines='{refines}'][@property='group-position']", NS)
    assert position.text == "12.5"
    kind = meta.find(f"opf:meta[@refines='{refines}'][@property='collection-type']", NS)
    assert kind.text == "series"
    assert meta.find("opf:meta[@property='dcterms:modified']", NS) is not None


async def test_the_cover_is_marked_cover_image(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
        cover = [
            item for item in opf.findall(".//opf:item", NS)
            if "cover-image" in (item.get("properties") or "")
        ]
        assert len(cover) == 1
        assert cover[0].get("href") == "images/cover.jpg"
        assert archive.read("OEBPS/images/cover.jpg") == JPEG


async def test_placeholders_become_images_and_the_chapter_parses(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        chapter = archive.read("OEBPS/chapter.xhtml").decode()
        assert "{{img:" not in chapter
        assert 'src="images/001.png"' in chapter
        assert archive.read("OEBPS/images/001.png") == PNG
        ET.fromstring(chapter)


async def test_no_cover_means_no_cover_item(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(cover=None), out)
    with zipfile.ZipFile(out) as archive:
        assert "OEBPS/images/cover.jpg" not in archive.namelist()
        assert b"cover-image" not in archive.read("OEBPS/content.opf")


async def test_a_missing_image_fails_the_chapter_and_leaves_nothing(tmp_path):
    out = tmp_path / "a.epub"
    with pytest.raises(ValueError, match="image 0"):
        await write_epub(_chapter(images=[]), out)
    assert list(tmp_path.iterdir()) == []


async def test_a_chapter_without_a_title_is_named_by_number(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(title=None, number=Decimal("3")), out)
    with zipfile.ZipFile(out) as archive:
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
    assert opf.find(".//dc:title", NS).text == "The Weakest of the Four - Chapter 3"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_epub.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.downloader.epub'`.

- [ ] **Step 3: Implement**

`backend/app/downloader/epub.py`:

```python
"""Turn one prose chapter into the EPUB 3 file Komga reads.

Hand-rolled, like the CBZ writer: the package is five small files, and every
field written here was chosen from what Komga's own EpubMetadataProvider and
EpubExtractor read (gotson/komga, verified 2026-10-14) - title, creator,
description, language, belongs-to-collection with group-position for the
series and number, and the manifest item marked cover-image for the
thumbnail.
"""

import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from app.downloader.cbz import page_extension, place_file

_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
}
_PLACEHOLDER = re.compile(r"\{\{img:(\d+)\}\}")

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass
class EpubChapter:
    series: str
    number: Decimal
    identifier: str
    title: str | None
    body: str
    images: list[bytes]
    cover: bytes | None
    language: str = "en"
    authors: list[str] = field(default_factory=list)
    summary: str | None = None

    @property
    def full_title(self) -> str:
        name = f"{self.series} - Chapter {_number(self.number)}"
        return f"{name}: {self.title}" if self.title else name


async def write_epub(chapter: EpubChapter, destination: Path) -> None:
    """Build the package in a scratch file and rename it into place.

    Komga scans on a schedule and on demand, and a half-written zip it indexes
    becomes a broken book in the library - so the destination only ever holds
    a complete file, exactly as with write_cbz.
    """
    files = _package(chapter)

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, scratch_name = tempfile.mkstemp(dir=destination.parent, suffix=".epub.part")
    os.close(handle)
    scratch = Path(scratch_name)
    try:
        with zipfile.ZipFile(scratch, "w") as archive:
            # First and stored: the OCF spec requires it, and readers find the
            # format by reading those bytes at a fixed offset.
            archive.writestr(
                zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED
            )
            for name, data, compress in files:
                archive.writestr(name, data, compress)
        await place_file(scratch, destination)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise


def _package(chapter: EpubChapter) -> list[tuple[str, bytes, int]]:
    image_names: list[str] = []
    files: list[tuple[str, bytes, int]] = []
    for index, data in enumerate(chapter.images, start=1):
        name = f"images/{index:03d}.{page_extension(data)}"
        image_names.append(name)
        # Already compressed formats; deflating them spends CPU for nothing.
        files.append((f"OEBPS/{name}", data, zipfile.ZIP_STORED))

    cover_name = None
    if chapter.cover is not None:
        cover_name = f"images/cover.{page_extension(chapter.cover)}"
        files.append((f"OEBPS/{cover_name}", chapter.cover, zipfile.ZIP_STORED))

    body = _resolve_images(chapter.body, image_names)
    files.append(("META-INF/container.xml", CONTAINER.encode(), zipfile.ZIP_DEFLATED))
    files.append(
        ("OEBPS/chapter.xhtml", _chapter_xhtml(chapter, body).encode(), zipfile.ZIP_DEFLATED)
    )
    files.append(("OEBPS/nav.xhtml", _nav(chapter).encode(), zipfile.ZIP_DEFLATED))
    files.append(
        ("OEBPS/content.opf", _opf(chapter, image_names, cover_name).encode(),
         zipfile.ZIP_DEFLATED)
    )
    return files


def _resolve_images(body: str, image_names: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index >= len(image_names):
            # Shipping the chapter without the image would look like a working
            # download with a hole in it, the same failure write_cbz refuses.
            raise ValueError(f"chapter body references image {index}, which was not fetched")
        return f'<img src="{image_names[index]}" alt=""/>'

    return _PLACEHOLDER.sub(replace, body)


def _chapter_xhtml(chapter: EpubChapter, body: str) -> str:
    heading = escape(chapter.title or f"Chapter {_number(chapter.number)}")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang={quoteattr(chapter.language)}>\n'
        f"<head><meta charset=\"utf-8\"/><title>{escape(chapter.full_title)}</title></head>\n"
        f"<body><section><h2>{heading}</h2>{body}</section></body>\n"
        "</html>\n"
    )


def _nav(chapter: EpubChapter) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f"<head><meta charset=\"utf-8\"/><title>{escape(chapter.full_title)}</title></head>\n"
        '<body><nav epub:type="toc"><ol>'
        f'<li><a href="chapter.xhtml">{escape(chapter.full_title)}</a></li>'
        "</ol></nav></body>\n"
        "</html>\n"
    )


def _opf(chapter: EpubChapter, image_names: list[str], cover_name: str | None) -> str:
    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = [
        f'<dc:identifier id="book-id">{escape(chapter.identifier)}</dc:identifier>',
        f"<dc:title>{escape(chapter.full_title)}</dc:title>",
        f"<dc:language>{escape(chapter.language)}</dc:language>",
        *(f"<dc:creator>{escape(author)}</dc:creator>" for author in chapter.authors),
        *(
            [f"<dc:description>{escape(chapter.summary)}</dc:description>"]
            if chapter.summary
            else []
        ),
        f'<meta property="dcterms:modified">{modified}</meta>',
        f'<meta property="belongs-to-collection" id="series">{escape(chapter.series)}</meta>',
        '<meta refines="#series" property="collection-type">series</meta>',
        f'<meta refines="#series" property="group-position">{_number(chapter.number)}</meta>',
    ]
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
    ]
    for index, name in enumerate(image_names, start=1):
        media_type = _MEDIA_TYPES[name.rsplit(".", 1)[1]]
        manifest.append(f'<item id="img{index:03d}" href="{name}" media-type="{media_type}"/>')
    if cover_name is not None:
        media_type = _MEDIA_TYPES[cover_name.rsplit(".", 1)[1]]
        manifest.append(
            f'<item id="cover" href="{cover_name}" media-type="{media_type}" '
            'properties="cover-image"/>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="book-id">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        + "\n".join(metadata)
        + "\n</metadata>\n<manifest>\n"
        + "\n".join(manifest)
        + '\n</manifest>\n<spine><itemref idref="chapter"/></spine>\n</package>\n'
    )


def _number(number: Decimal) -> str:
    integral = int(number)
    return str(integral) if number == integral else format(number.normalize(), "f")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_epub.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/downloader/epub.py backend/tests/test_epub.py
git commit -m "feat(downloader): write one prose chapter as an EPUB 3 package"
```

---

### Task 7: Komga scans EPUB, including on existing installs

**Files:**
- Modify: `backend/app/komga/client.py` (`library_payload`, `ensure_library`)
- Test: `backend/tests/test_komga_client.py` (edit one test, add two)

**Interfaces:**
- Produces: `library_payload(...)["scanEpub"] is True`; `KomgaClient.ensure_library` sends `PATCH /api/v1/libraries/{id}` with exactly `{"scanEpub": true}` when the existing library reports `"scanEpub": false`. A library response with no `scanEpub` key is left alone.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_komga_client.py`, inside `test_library_payload_leaves_the_archives_alone`, change any assertion on `scanEpub` to `True` if present. Then append:

```python
def test_library_payload_scans_epub_for_prose():
    assert library_payload("Manga", "/manga")["scanEpub"] is True


async def test_an_existing_library_with_epub_off_is_switched_on_alone():
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        if request.method == "GET":
            return httpx.Response(
                200, json=[{"id": "lib-1", "name": "Manga", "root": "/manga", "scanEpub": False}]
            )
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", api_key="k", client=http_client)
        assert await client.ensure_library("Manga", "/manga") == "lib-1"
    patches = [call for call in calls if call[0] == "PATCH"]
    assert len(patches) == 1
    assert patches[0][1] == "/api/v1/libraries/lib-1"
    # Partial body: Komga's PATCH leaves every field it is not sent alone.
    assert json.loads(patches[0][2]) == {"scanEpub": True}


async def test_an_existing_library_already_scanning_epub_is_not_patched():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(
            200, json=[{"id": "lib-1", "name": "Manga", "root": "/manga", "scanEpub": True}]
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", api_key="k", client=http_client)
        await client.ensure_library("Manga", "/manga")
    assert calls == ["GET"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_komga_client.py -q`
Expected: FAIL on the three new tests.

- [ ] **Step 3: Implement**

In `library_payload`, change `"scanEpub": False,` to `"scanEpub": True,` and extend the docstring:

```python
    """Komga requires every switch to be stated, so state them deliberately.

    ComicInfo import is on because the pipeline writes that file into each
    archive; conversion and repair are off because the files arrive as CBZ
    already and rewriting them would fight the downloader. EPUB is scanned
    because prose chapters arrive as EPUB, and its metadata import is on for
    the same reason ComicInfo's is.
    """
```

Replace `ensure_library`:

```python
    async def ensure_library(self, name: str, root: str) -> str:
        """Create the library if it is absent. Matching is by root path.

        A library created before prose existed has EPUB scanning off, and
        Komga would then never index a single light novel. Only that switch
        is changed - PATCH takes a partial body (since Komga 1.3.0), so every
        setting the user may have tuned in Komga's own screens stays theirs.
        """
        for library in await self.libraries():
            if (library.get("root") or "").rstrip("/") == root.rstrip("/"):
                if library.get("scanEpub") is False:
                    response = await self._request(
                        "PATCH", f"{API}/libraries/{library['id']}", json={"scanEpub": True}
                    )
                    if response.status_code >= 400:
                        raise KomgaError(
                            f"enabling EPUB scanning failed: {response.status_code} "
                            f"{response.text[:300]}"
                        )
                return library["id"]
        response = await self._request("POST", f"{API}/libraries", json=library_payload(name, root))
        if response.status_code >= 400:
            raise KomgaError(
                f"library creation failed: {response.status_code} {response.text[:300]}"
            )
        return response.json()["id"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_komga_client.py tests/test_komga_list_progress.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/komga/client.py backend/tests/test_komga_client.py
git commit -m "feat(komga): scan EPUB files, switching it on for existing libraries"
```

---

### Task 8: Search and mapping respect the series kind

**Files:**
- Modify: `backend/app/handlers/match_search.py`, `backend/app/api/routes_series.py` (`confirm_mapping`)
- Test: `backend/tests/test_series_kind_api.py` (created here, extended in Task 9), `backend/tests/test_match_search_fanout.py` (append)

**Interfaces:**
- Consumes: `all_sources(kind=...)`, `kind_of` (Task 3); `series.kind` (Task 1).
- Produces: `async def series_kind(session: AsyncSession, series_id: int) -> str` in `app/handlers/match_search.py`. It returns `"comic"` for null. `POST /api/series/{id}/mapping` answers 422 when the URL's source kind differs from the series kind.

- [ ] **Step 1: Write the failing tests**

First read `backend/tests/test_match_search_fanout.py` to reuse its fake sources and context helpers. Append a test in the same style:

```python
async def test_a_prose_series_only_asks_prose_sources():
    asked: list[str] = []

    class ComicFake(base.Source):
        site = "comic-fake"
        domains = ()

        async def search(self, titles, *, limit=8):
            asked.append(self.site)
            return []

        async def list_chapters(self, url, *, language="en"):
            return []

        async def list_pages(self, chapter_url, *, language="en"):
            return []

    class ProseFake(base.ProseSource):
        site = "prose-fake"
        domains = ()

        async def search(self, titles, *, limit=8):
            asked.append(self.site)
            return []

        async def list_chapters(self, url, *, language="en"):
            return []

        async def fetch_chapter(self, chapter_url, *, language="en"):
            raise NotImplementedError

    base.install_registry(
        {
            "comic-fake": base.RegisteredSource(ComicFake(), "https://c.test"),
            "prose-fake": base.RegisteredSource(ProseFake(), "https://p.test"),
        }
    )
    async with get_sessionmaker()() as session:
        series_id = await _series_titled(session, "Some Novel")
        await session.execute(
            text("update series set kind = 'prose' where id = :id"), {"id": series_id}
        )
        await session.commit()
        ctx = await _match_context(session, series_id)
        await match_search.handle(ctx)

    assert asked == ["prose-fake"]
```

Use the helper names that file already defines for creating a series and leasing a `MATCH_SEARCH` job. If they are named differently, use those names; if the file has no helper for one of them, add a small local one in the style of `_series` and `_context` from `tests/test_download_batch_handler.py`. Import `from app.sources import base` if it isn't already imported.

Create `backend/tests/test_series_kind_api.py`:

```python
"""The API keeps a series and its source on the same side of comic/prose."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import get_sessionmaker
from app.main import app
from app.sources import base


class ProseFake(base.ProseSource):
    site = "prose-fake"
    domains = ("prose.test",)

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotImplementedError


class ComicFake(base.Source):
    site = "comic-fake"
    domains = ("comic.test",)

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def list_pages(self, chapter_url, *, language="en"):
        return []


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    base.install_registry(
        {
            "prose-fake": base.RegisteredSource(ProseFake(), "https://prose.test"),
            "comic-fake": base.RegisteredSource(ComicFake(), "https://comic.test"),
        }
    )
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        yield http


async def _series(kind: str | None) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('t', 't', true, '{}'::jsonb, cast(:kind as text)) returning id"
                ),
                {"kind": kind},
            )
        ).scalar_one()
        await session.commit()
        return int(series_id)


async def test_a_prose_series_refuses_a_comic_source(client):
    series_id = await _series("prose")
    response = await client.post(
        f"/api/series/{series_id}/mapping", json={"source_url": "https://comic.test/m/1"}
    )
    assert response.status_code == 422
    assert "prose" in response.json()["detail"]


async def test_an_unknown_kind_series_refuses_a_prose_source(client):
    series_id = await _series(None)
    response = await client.post(
        f"/api/series/{series_id}/mapping", json={"source_url": "https://prose.test/n/1"}
    )
    assert response.status_code == 422


async def test_a_prose_series_accepts_a_prose_source(client):
    series_id = await _series("prose")
    response = await client.post(
        f"/api/series/{series_id}/mapping", json={"source_url": "https://prose.test/n/1"}
    )
    assert response.status_code == 200
```

Check how `tests/test_api.py` builds its client (`app.main:app` with `ASGITransport`, or a fixture in conftest) and match it exactly. The fixture above is the default shape.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_match_search_fanout.py tests/test_series_kind_api.py -q`
Expected: FAIL. The search asks both sources; the comic mapping on a prose series returns 200.

- [ ] **Step 3: Implement**

In `backend/app/handlers/match_search.py` add:

```python
async def series_kind(session: AsyncSession, series_id: int) -> str:
    """The kind to search as. Unknown searches as comic, which is what every
    series did before the column existed."""
    kind = (
        await session.execute(text("select kind from series where id = :id"), {"id": series_id})
    ).scalar_one_or_none()
    return kind or "comic"
```

In `handle`, before the `gather`:

```python
    kind = await series_kind(ctx.session, series_id)
```

and replace `for source in all_sources()` with `for source in all_sources(kind=kind)`. Change `_search_one`'s `source: Source` annotation to `source: SiteSource` and import `SiteSource` from `app.sources.base` instead of `Source`.

In `backend/app/api/routes_series.py`, import `kind_of` from `app.sources` and `series_kind` from `app.handlers.match_search`. In `confirm_mapping`, directly after the `source_for_url` try/except:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_match_search_fanout.py tests/test_series_kind_api.py tests/test_review_queue.py tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/match_search.py backend/app/api/routes_series.py backend/tests/test_match_search_fanout.py backend/tests/test_series_kind_api.py
git commit -m "feat(search): match a series only against sources of its own kind"
```

---

### Task 9: Series kind in the API, and setting it by hand

**Files:**
- Modify: `backend/app/api/routes_series.py` (`LIST_SQL`, `LIST_SQL_ONE`, `_row_to_series`, new route)
- Test: `backend/tests/test_series_kind_api.py` (append)

**Interfaces:**
- Produces: `"kind": "comic" | "prose" | null` in every series object from `GET /api/series` and `GET /api/series/{id}`. `POST /api/series/{id}/kind` with body `{"kind": "comic" | "prose"}` returns `{"ok": true, "kind": ...}`, sets `meta.kind_locked = true`, and returns 404 for an unknown series.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_series_kind_api.py`:

```python
async def test_series_payloads_carry_the_kind(client):
    series_id = await _series("prose")
    listed = (await client.get("/api/series")).json()
    rows = listed if isinstance(listed, list) else listed["series"]
    assert next(row for row in rows if row["id"] == series_id)["kind"] == "prose"
    detail = (await client.get(f"/api/series/{series_id}")).json()
    assert detail["series"]["kind"] == "prose"


async def test_setting_the_kind_by_hand_locks_it(client):
    series_id = await _series(None)
    response = await client.post(f"/api/series/{series_id}/kind", json={"kind": "prose"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "kind": "prose"}
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text("select kind, meta from series where id = :id"), {"id": series_id}
            )
        ).one()
    assert row.kind == "prose"
    assert row.meta["kind_locked"] is True


async def test_an_unknown_kind_value_is_rejected(client):
    series_id = await _series(None)
    response = await client.post(f"/api/series/{series_id}/kind", json={"kind": "audio"})
    assert response.status_code == 422


async def test_setting_the_kind_of_a_missing_series_is_404(client):
    response = await client.post("/api/series/999999/kind", json={"kind": "prose"})
    assert response.status_code == 404
```

Check what `GET /api/series` returns in `tests/test_series_list_counts.py`, a list or an object, and keep only the branch that matches.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_series_kind_api.py -q`
Expected: FAIL on the four new tests.

- [ ] **Step 3: Implement**

In `LIST_SQL` and `LIST_SQL_ONE`, change the line `s.auto_download,` to `s.auto_download, s.kind,`. Both group by `s.id`, so `s.kind` needs no `group by` change.

In `_row_to_series`, after `"auto_download": row.auto_download,` add:

```python
        "kind": row.kind,
```

Add a request model next to `AutoDownloadIn`:

```python
class KindIn(BaseModel):
    kind: Literal["comic", "prose"]
```

(add `Literal` to the `typing` import), and the route after `set_auto_download`:

```python
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
    await session.commit()
    return {"ok": True, "kind": body.kind}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_series_kind_api.py tests/test_series_list_counts.py tests/test_series_detail_links.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_series.py backend/tests/test_series_kind_api.py
git commit -m "feat(api): expose a series' kind and let the user set it"
```

---

### Task 10: The image reader refuses prose chapters

**Files:**
- Modify: `backend/app/api/reader_service.py` (`ChapterRow`, `chapter`), `backend/app/api/routes_reader.py` (`service_errors`)
- Test: `backend/tests/test_reader_api.py` (append)

**Interfaces:**
- Produces: `class ProseChapter(RuntimeError)` in `reader_service`; `ChapterRow.series_kind: str | None`. Every reader route answers 409 with detail `"this is a light novel chapter; read it in Komga"` for a chapter of a prose series.

- [ ] **Step 1: Write the failing test**

Read `backend/tests/test_reader_api.py` to reuse its client fixture and series/chapter helpers. Append:

```python
async def test_a_prose_chapter_is_refused_with_a_pointer_to_komga(client):
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('N', 'n', false, '{}'::jsonb, 'prose') returning id"
                )
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state)"
                    " values (:s, 1, 'downloaded') returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.commit()

    response = await client.get(f"/api/reader/chapters/{chapter_id}")
    assert response.status_code == 409
    assert "Komga" in response.json()["detail"]
```

Use the route prefix that file already uses for reader routes; `routes_reader.py` declares the paths as `/chapters/{chapter_id}` under its router prefix.

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_reader_api.py -q`
Expected: FAIL on the new test, with a status other than 409.

- [ ] **Step 3: Implement**

In `reader_service.py`, add after `PageFailed`:

```python
class ProseChapter(RuntimeError):
    """A light novel chapter. This reader draws page images, and an EPUB opened
    as a zip would show its embedded illustrations as if they were the pages."""
```

Add `series_kind: str | None` as the last field of `ChapterRow`. In `chapter()`, add `s.kind as series_kind` to the select list, and replace the final `return ChapterRow(**row._mapping)` with:

```python
    found = ChapterRow(**row._mapping)
    if found.series_kind == "prose":
        raise ProseChapter(f"chapter {chapter_id} belongs to a light novel")
    return found
```

In `routes_reader.py` `service_errors`, add before the `NoMapping` clause:

```python
    except service.ProseChapter as exc:
        raise HTTPException(
            status_code=409, detail="this is a light novel chapter; read it in Komga"
        ) from exc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_reader_api.py tests/test_reader_downloads.py tests/test_reader_progress.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reader_service.py backend/app/api/routes_reader.py backend/tests/test_reader_api.py
git commit -m "feat(reader): refuse light novel chapters with a pointer to Komga"
```

---

### Task 11: Download prose chapters as EPUB

**Files:**
- Create: `backend/app/downloader/prose_fetch.py`, `backend/app/handlers/prose_download.py`
- Modify: `backend/app/handlers/download_batch.py`, `backend/app/handlers/download_chapter.py`, `backend/app/handlers/chapter_discover.py` (`reconcile_with_disk`)
- Test: `backend/tests/test_prose_fetch.py`, `backend/tests/test_prose_download.py`

**Interfaces:**
- Consumes: `ProseSource`, `ChapterText`, `get_prose_source` (Task 3); `EpubChapter`, `write_epub` (Task 6); `chapter_path(..., kind=)`, `existing_chapter_file` (Task 5); `fetch_pages` (`app.downloader.fetcher`); `fetch_series_artwork` (`app.handlers.komga_scan`); `build_comicinfo` (`app.handlers.download_chapter`).
- Produces:
  - `async fetch_prose_chapter(source: ProseSource, chapter_url: str, client: SiteClient) -> tuple[ChapterText, list[bytes]]` in `app/downloader/prose_fetch.py`.
  - `async write_prose_chapter(ctx: JobContext, row: dict[str, Any], source: ProseSource, client: SiteClient, cover: bytes | None, destination: Path) -> None` in `app/handlers/prose_download.py`. `row` is a `load_batch` / `load_context` row.
  - `async cover_for(ctx: JobContext, series_id: int) -> bytes | None` in the same module (best effort, never raises).
  - `load_batch` and `load_context` rows gain `kind` (`s.kind`).

- [ ] **Step 1: Write the failing test for the fetcher**

`backend/tests/test_prose_fetch.py`:

```python
"""fetch_prose_chapter fetches the text and every image the text references."""

import httpx

from app.downloader.prose_fetch import fetch_prose_chapter
from app.sources.base import ChapterText, PageRef, ProseSource
from app.sources.net import CatalogueRow, SiteClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class Fake(ProseSource):
    site = "fake"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        return ChapterText(
            title="T",
            body="<p>{{img:0}}</p>",
            images=[PageRef(url="https://img.test/a.png", headers={"Referer": chapter_url})],
        )


async def test_images_are_fetched_with_their_referer():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    client = SiteClient(
        CatalogueRow(key="fake-prose-fetch", base_url="https://site.test"),
        transport=httpx.MockTransport(handler),
    )
    text, images = await fetch_prose_chapter(Fake(), "https://site.test/c/1", client)
    assert text.title == "T"
    assert images == [PNG]
    assert seen[0].headers["referer"] == "https://site.test/c/1"


async def test_a_chapter_without_images_makes_no_requests():
    class NoImages(Fake):
        async def fetch_chapter(self, chapter_url, *, language="en"):
            return ChapterText(title=None, body="<p>x</p>", images=[])

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = SiteClient(
        CatalogueRow(key="fake-prose-none", base_url="https://site.test"),
        transport=httpx.MockTransport(handler),
    )
    _, images = await fetch_prose_chapter(NoImages(), "https://site.test/c/1", client)
    assert images == []
```

Read `SiteClient.__init__` in `backend/app/sources/net.py` (line 248) first. If it doesn't accept a `transport` argument, build the client the way `tests/test_fetcher.py` builds one for `fetch_pages`, and use that construction in both tests instead.

- [ ] **Step 2: Run the test to verify it fails**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_fetch.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.downloader.prose_fetch'`.

- [ ] **Step 3: Implement the fetcher**

`backend/app/downloader/prose_fetch.py`:

```python
"""Fetch one prose chapter: its text from the source, its images like pages.

Images go through fetch_pages rather than a fetch of their own, so they obey
the site's rate limit, carry the referer the source attached, and are checked
for being images at all - the same sites that answer a hotlinked comic page
with 200 text/html do the same to an illustration.
"""

from app.downloader.fetcher import fetch_pages
from app.sources.base import ChapterText, ProseSource
from app.sources.net import SiteClient


async def fetch_prose_chapter(
    source: ProseSource, chapter_url: str, client: SiteClient
) -> tuple[ChapterText, list[bytes]]:
    text = await source.fetch_chapter(chapter_url)
    images = await fetch_pages(client, text.images) if text.images else []
    return text, images
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_fetch.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing handler tests**

`backend/tests/test_prose_download.py` reuses the stub-server and database helpers from `test_download_batch_handler.py`. Import them rather than copying: `from tests.test_download_batch_handler import Stub, _catalogue, _chapter, _context, _series, clean  # noqa: F401`. If `tests` isn't importable as a package (there is a `tests/__init__.py`, so it is), copy the helpers instead.

```python
"""A prose series downloads through the same handlers, as EPUB."""

import zipfile

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.downloader.paths import chapter_path
from app.handlers import download_batch, download_chapter
from app.sources.base import (
    ChapterText,
    ChapterUnavailable,
    PageRef,
    ProseSource,
    RegisteredSource,
    install_registry,
)
from tests.test_download_batch_handler import (  # noqa: F401 - clean is an autouse fixture
    Stub,
    _catalogue,
    _chapter,
    _context,
    _series,
    clean,
)

pytestmark = pytest.mark.asyncio

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeProse(ProseSource):
    domains = ()

    def __init__(self, site: str, locked: frozenset[str] = frozenset()) -> None:
        self.site = site
        self._locked = locked

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        if chapter_url in self._locked:
            raise ChapterUnavailable("locked")
        return ChapterText(
            title=None, body="<p>Text {{img:0}}</p>", images=[PageRef(url="/art.png")]
        )


async def _make_prose(session, series_id: int) -> None:
    await session.execute(
        text("update series set kind = 'prose' where id = :id"), {"id": series_id}
    )
    await session.commit()


async def test_a_prose_batch_writes_epubs():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [await _chapter(session, series_id, str(n), u) for n, u in zip((1, 2), urls)]
            ctx = await _context(session, ids)
            await download_batch.handle(ctx)
            await session.commit()
            rows = (
                await session.execute(
                    text("select state, file_path from chapter order by number")
                )
            ).all()
        assert [r.state for r in rows] == ["downloaded", "downloaded"]
        for row in rows:
            assert row.file_path.endswith(".epub")
            with zipfile.ZipFile(row.file_path) as archive:
                assert archive.read("mimetype") == b"application/epub+zip"
                assert "OEBPS/images/001.png" in archive.namelist()
    finally:
        stub.close()


async def test_a_locked_prose_chapter_is_skipped_not_fatal():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        urls = [f"{stub.base_url}/n/1/{n}" for n in (1, 2)]
        source = FakeProse(stub.key, locked=frozenset({urls[1]}))
        install_registry({stub.key: RegisteredSource(source, stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            ids = [await _chapter(session, series_id, str(n), u) for n, u in zip((1, 2), urls)]
            ctx = await _context(session, ids)
            await download_batch.handle(ctx)
            await session.commit()
            states = (
                await session.execute(text("select state from chapter order by number"))
            ).scalars().all()
        assert states == ["downloaded", "skipped"]
    finally:
        stub.close()


async def test_a_prose_batch_skips_a_chapter_already_on_disk_as_cbz(tmp_path):
    from app.config import get_settings

    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            existing = chapter_path(
                get_settings().library_path, "rebirth-monarch-of-the-dead",
                __import__("decimal").Decimal("1"), "Chapter 1",
            )
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"old comic file")
            ctx = await _context(session, [chapter_id])
            await download_batch.handle(ctx)
            await session.commit()
            row = (await session.execute(text("select state, file_path from chapter"))).one()
        assert row.state == "downloaded"
        assert row.file_path == str(existing)
    finally:
        stub.close()


async def test_a_single_prose_chapter_job_writes_an_epub():
    stub = Stub(lambda path: (200, "image/png", PNG))
    try:
        url = f"{stub.base_url}/n/1/1"
        install_registry({stub.key: RegisteredSource(FakeProse(stub.key), stub.base_url)})
        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _make_prose(session, series_id)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", url)
            from app.enums import JobType
            from app.handlers.base import JobContext
            from app.queue import repo
            from tests.test_download_batch_handler import EVERY_TYPE

            await repo.enqueue(session, JobType.DOWNLOAD_CHAPTER, {"chapter_id": chapter_id})
            await session.commit()
            job = await repo.lease(session, types=EVERY_TYPE)
            await session.commit()
            await download_chapter.handle(JobContext(session=session, job=job))
            await session.commit()
            path = (await session.execute(text("select file_path from chapter"))).scalar_one()
        assert path.endswith(".epub")
    finally:
        stub.close()
```

Clean up the inline imports (`__import__`, function-level imports) into top-level imports when you write the file; they are inline here only so each test reads on its own.

- [ ] **Step 6: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_download.py -q`
Expected: FAIL. The handlers call `list_pages` on a `ProseSource`, which raises `AttributeError`.

- [ ] **Step 7: Implement the shared prose writer**

`backend/app/handlers/prose_download.py`:

```python
"""The prose half of the download handlers.

download_batch and download_chapter keep everything around the archive write -
leasing, batching, the unavailable/failed bookkeeping, the Komga scan after -
and branch only here, so a light novel chapter is retried, skipped and
requeued by exactly the rules a manga chapter is.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from app.downloader.epub import EpubChapter, write_epub
from app.downloader.prose_fetch import fetch_prose_chapter
from app.handlers.base import JobContext
from app.handlers.download_chapter import build_comicinfo
from app.handlers.komga_scan import fetch_series_artwork
from app.sources.base import ProseSource
from app.sources.net import SiteClient


async def cover_for(ctx: JobContext, series_id: int) -> bytes | None:
    """The series cover, or None. Never a reason to fail a chapter.

    Komga takes each book's thumbnail from the EPUB's cover-image, and a scraped
    chapter has no art of its own - but a provider CDN being down for a minute
    is not worth a chapter, so any failure here just ships it without one.
    """
    try:
        return await fetch_series_artwork(ctx, series_id)
    except Exception as exc:  # noqa: BLE001 - best effort by design, logged
        await ctx.log(f"cover unavailable, chapters ship without one: {exc}", level="warning")
        return None


async def write_prose_chapter(
    ctx: JobContext,
    row: dict[str, Any],
    source: ProseSource,
    client: SiteClient,
    cover: bytes | None,
    destination: Path,
) -> None:
    text, images = await fetch_prose_chapter(source, row["chapter_url"], client)
    # ComicInfo's fields are the series metadata this pipeline already
    # resolves from every provider; the EPUB carries the same answers.
    info = await build_comicinfo(ctx.session, row)
    number = Decimal(str(row["number"]))
    await write_epub(
        EpubChapter(
            series=row["canonical_title"],
            number=number,
            identifier=f"soshuhen:{row['series_id']}:{number.normalize()}",
            title=row["title"] or text.title,
            body=text.body,
            images=images,
            cover=cover,
            authors=[info.writer] if info.writer else [],
            summary=info.summary,
        ),
        destination,
    )
```

- [ ] **Step 8: Branch `download_batch`**

In `backend/app/handlers/download_batch.py`:

1. Add `s.kind` to `load_batch`'s select list (after `s.meta`).
2. Import `existing_chapter_file` with `chapter_path`, `write_prose_chapter` and `cover_for` from `app.handlers.prose_download`, and `ProseSource` from `app.sources.base`.
3. After `slug = first["slug"]`, add `kind = first["kind"] or "comic"`.
4. Replace the pre-check in the first loop:

```python
        destination = existing_chapter_file(library_root, slug, number, row["title"])
        if destination is not None:
            await mark_downloaded(ctx.session, row["id"], destination)
            already += 1
            continue
```

5. After `source = source_for_url(...)`, add:

```python
    if kind == "prose" and not isinstance(source, ProseSource):
        raise PermanentError(
            f"series {first['series_id']} is prose but its mapping points at "
            f"{source.site}, a comic source - choose a new mapping in Review"
        )
    if kind != "prose" and isinstance(source, ProseSource):
        raise PermanentError(
            f"series {first['series_id']} is a comic but its mapping points at "
            f"{source.site}, a prose source - choose a new mapping in Review"
        )
    cover = await cover_for(ctx, first["series_id"]) if kind == "prose" else None
```

6. In the loop, replace the `try:` block that calls `fetch_chapter`, and the lines from `info = await build_comicinfo(...)` through `await mark_downloaded(...)`, with:

```python
            destination = chapter_path(library_root, slug, number, row["title"], kind=kind)
            try:
                if kind == "prose":
                    await write_prose_chapter(ctx, row, source, client, cover, destination)
                    counted = 1
                    page_bytes: list[bytes] = []
                else:
                    # Listing and fetching together, so a page that 404s can ask for
                    # the list again: the at-home address rotates, and this is what
                    # cost eighteen chapters of one series - a single stale page
                    # failed the whole batch (#169).
                    page_bytes = await fetch_chapter(
                        source, row["chapter_url"], client, on_page=keep_lease
                    )
```

Keep the existing `except ChapterUnavailable` and `except (httpx.HTTPStatusError, PageFetchError)` clauses unchanged, with their comments. After them:

```python
            if kind != "prose":
                info = await build_comicinfo(ctx.session, row)
                await write_cbz(page_bytes, destination, info)
            await mark_downloaded(ctx.session, row["id"], destination)
            placed += 1
```

7. Change the per-chapter log line so it reads for both kinds:

```python
            detail = "saved as EPUB" if kind == "prose" else f"{len(page_bytes)}/{counted} pages"
            await ctx.log(
                f"chapter {number}: {detail} ({index}/{total} chapters)",
                pct=100.0 * index / total,
            )
```

- [ ] **Step 9: Branch `download_chapter`**

In `backend/app/handlers/download_chapter.py`:

1. Add `s.kind` to `load_context`'s select list.
2. In `handle`, replace the destination block:

```python
    kind = row["kind"] or "comic"
    library_root = Path(settings.library_path)
    existing = existing_chapter_file(library_root, row["slug"], number, row["title"])
    if existing is not None:
        await ctx.log(f"chapter {number} already in the library", pct=100)
        await mark_downloaded(ctx.session, chapter_id, existing)
        if from_cache:
            reader_cache_files.remove(settings.reader_cache_path, chapter_id)
        return
    destination = chapter_path(library_root, row["slug"], number, row["title"], kind=kind)
```

3. Replace the page-fetch-and-write block (from `if from_cache:` through `await write_cbz(...)`) with:

```python
    if kind == "prose":
        source, client, semaphore = await _site(ctx, row)
        if not isinstance(source, ProseSource):
            raise PermanentError(
                f"series {row['series_id']} is prose but {source.site} is a comic source"
            )
        cover = await cover_for(ctx, row["series_id"])
        try:
            async with semaphore:
                await write_prose_chapter(ctx, row, source, client, cover, destination)
        except ChapterUnavailable as exc:
            raise PermanentError(f"chapter {number} unavailable: {exc}") from exc
    else:
        if from_cache:
            page_bytes = await pages_from_cache(ctx, row, chapter_id, number)
        else:
            page_bytes = await pages_from_source(ctx, row, chapter_id, number)
        info = await build_comicinfo(ctx.session, row)
        await write_cbz(page_bytes, destination, info)
```

4. Imports: `existing_chapter_file` from `app.downloader.paths`, `ProseSource` from `app.sources.base`. Import `cover_for` and `write_prose_chapter` **inside** `handle` (`from app.handlers.prose_download import cover_for, write_prose_chapter`), with this comment: `# prose_download imports build_comicinfo from this module; importing it at module level would be circular.`
5. Check how `pages_from_source` maps `ChapterUnavailable` today and keep the prose mapping consistent with it. If it lets it propagate to the queue, which maps it to `PermanentError`, drop the explicit `try/except` above and rely on the same path.

- [ ] **Step 10: Reconcile either extension from disk**

In `backend/app/handlers/chapter_discover.py` `reconcile_with_disk`, replace the two `chapter_path` lookups with:

```python
        path = existing_chapter_file(library_root, slug, Decimal(str(row.number)), row.title)
        if path is not None:
```

and update the import (`existing_chapter_file` instead of `chapter_path`, if `chapter_path` has no other use in the file).

- [ ] **Step 11: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_prose_download.py tests/test_prose_fetch.py tests/test_download_batch_handler.py tests/test_download_chapter_handler.py tests/test_opt_in_downloads.py tests/test_reader_downloads.py -q`
Expected: PASS, including every existing comic test unchanged.

- [ ] **Step 12: Commit**

```bash
git add backend/app/downloader/prose_fetch.py backend/app/handlers/prose_download.py backend/app/handlers/download_batch.py backend/app/handlers/download_chapter.py backend/app/handlers/chapter_discover.py backend/tests/test_prose_fetch.py backend/tests/test_prose_download.py
git commit -m "feat(download): write prose chapters as EPUB through the same handlers"
```

---

### Task 12: lolobun source

**Files:**
- Create: `backend/app/sources/lolobun.py`
- Create fixtures: `backend/tests/fixtures/sources/lolobun_search.json`, `lolobun_book.html`, `lolobun_chapter.html`, `lolobun_locked.html`
- Modify: `backend/app/sources/registry.py` (`NATIVE_SOURCES`)
- Test: `backend/tests/test_source_lolobun.py`

**Verified facts (fetched 2026-10-14):**
- LoLoBun is the English storefront of SF Light Novel (SFACG). It's an official, paid platform. **Most chapters are locked to the app or coins**: the recorded book has 589 chapters, 569 marked locked, and the web serves only the first 20. A locked chapter page still answers 200, with a ~130-character teaser in `.text-content-box`. The only markup difference between a free and a locked page is `.order-vip-container`: it carries the class `hidden` on a free chapter and lacks it on a locked one. (`.vip-app-guide` and `.auto-unlock-box` are on both pages, so neither works as a marker.)
- Search: `GET /ajax/Common.ashx?op=getSearchSuggest&keyword=<q>` with `X-Requested-With: XMLHttpRequest`. It returns JSON `{"status": {"errorCode": 200}, "data": [{"EntityId", "EntityType", "Title", "AuthorName", "Url", "Weight"}]}`. `EntityType` is `"Novel"` or `"Comic"`; novels have `Url` `/n/<id>`, comics `/c/<id>`. No cover in the search payload.
- Book page `/n/<id>`: the full catalogue is in the HTML, grouped into 5 `.catalog-volume` blocks. Each block holds a `.catalog-volume-title` and its `.catalog-item`s, 589 items in all. Each item holds `.title a[href="/n/<id>/<cid>"]` with text like `Chapter 12: Title`, and an `.icon-box` containing `img[src*="icon_lock"]` when the chapter is locked. Items run oldest first. The series title is `.header-item-info .name`.
- selectolax returns a comma selector's matches grouped by selector, **not** in document order, so walk `.catalog-volume` blocks and read the items inside each one.
- **Chapter numbers are not reliably in the titles**: 17 of the first chapters read "Chapter Three: ...", "Chapter Seven, ...", and one title is missing its closing parenthesis. The **catalogue position** (1-based, oldest first) is the chapter number.
- Chapter page `/n/<id>/<cid>`: the body is `.text-content-box` and contains only `<p>` elements (63 in the recorded chapter, 7,044 characters).

**Interfaces:**
- Consumes: `ProseSource`, `ChapterText`, `ChapterRef`, `Candidate`, `ChapterUnavailable` (`app.sources.base`); `clean_chapter_html` (`app.sources.prose`); `get_client`, `CatalogueRow` (`app.sources.net`); `best_similarity` (`app.text_utils`).
- Produces: `LolobunSource(ProseSource)` with `site = "lolobun"`, `domains = ("lolobun.com",)`, and pure parsers `parse_search(payload: dict, titles: list[str]) -> list[Candidate]`, `parse_chapters(html: str) -> list[ChapterRef]`, `parse_chapter(html: str, chapter_url: str) -> ChapterText`.

- [ ] **Step 1: Record the fixtures**

```bash
mkdir -p backend/tests/fixtures/sources
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
curl -s -A "$UA" -H "X-Requested-With: XMLHttpRequest" "https://www.lolobun.com/ajax/Common.ashx?op=getSearchSuggest&keyword=dragon" -o backend/tests/fixtures/sources/lolobun_search.json
curl -sL -A "$UA" https://www.lolobun.com/n/5320143 -o backend/tests/fixtures/sources/lolobun_book.html
curl -sL -A "$UA" https://www.lolobun.com/n/5320143/7123286 -o backend/tests/fixtures/sources/lolobun_chapter.html
curl -sL -A "$UA" https://www.lolobun.com/n/5320143/7124349 -o backend/tests/fixtures/sources/lolobun_locked.html
```

Copies recorded during planning sit in the session scratchpad (`.../scratchpad/ln/lolobun_*`). If the live site has changed so that the counts below no longer hold, update the numeric assertions to match the newly recorded fixture, and say so in the commit message.

- [ ] **Step 2: Write the failing tests**

```python
"""Golden tests for LoLoBun, driven by recorded responses."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.base import ChapterUnavailable
from app.sources.lolobun import LolobunSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def _source() -> LolobunSource:
    # client is never reached: every test here calls a pure parser directly.
    return LolobunSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_offers_novels_only():
    payload = json.loads(_read("lolobun_search.json"))
    found = _source().parse_search(payload, ["Shut up, Evil Dragon"])
    assert found
    assert all(c.source_url.startswith("https://www.lolobun.com/n/") for c in found)
    assert {c.source_site for c in found} == {"lolobun"}
    # The same title exists as a comic (/c/20103) in the recorded payload.
    assert not any("/c/" in c.source_url for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_chapters_are_numbered_by_catalogue_position():
    chapters = _source().parse_chapters(_read("lolobun_book.html"))
    assert len(chapters) == 589
    assert [c.number for c in chapters[:3]] == [Decimal(1), Decimal(2), Decimal(3)]
    assert chapters[0].url == "https://www.lolobun.com/n/5320143/7123286"
    assert chapters[0].title == "Chapter 1: The Brave is Coming to Attack the City! (Part 1)"
    # Spelled-out numbers in the title do not matter; position does.
    assert chapters[2].title.startswith("Chapter Three")
    assert chapters[-1].number == Decimal(589)


def test_volumes_travel_with_their_chapters():
    chapters = _source().parse_chapters(_read("lolobun_book.html"))
    assert chapters[0].volume == "Volume One: Twin Shining Stars"


def test_a_free_chapter_parses_to_paragraphs():
    text = _source().parse_chapter(
        _read("lolobun_chapter.html"), "https://www.lolobun.com/n/5320143/7123286"
    )
    assert text.body.startswith("<p>The autumn wind blows coldly.</p>")
    assert text.body.count("<p>") == 63
    assert text.images == []


def test_a_locked_chapter_is_unavailable_not_a_teaser():
    with pytest.raises(ChapterUnavailable, match="locked"):
        _source().parse_chapter(
            _read("lolobun_locked.html"), "https://www.lolobun.com/n/5320143/7124349"
        )
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_lolobun.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.sources.lolobun'`.

- [ ] **Step 4: Implement**

`backend/app/sources/lolobun.py`:

```python
"""LoLoBun (lolobun.com), the English storefront of SF Light Novel.

An official, paid platform: the web serves the first chapters of a book and
locks the rest behind its app and coins. Locked chapters are listed like any
other and refused when fetched, so they land as `skipped` with a reason
rather than vanishing from the series.
"""

from decimal import Decimal
from typing import ClassVar

from selectolax.parser import HTMLParser

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    ChapterUnavailable,
    PageRef,
    ProseSource,
)
from app.sources.net import CatalogueRow, get_client
from app.sources.prose import clean_chapter_html
from app.text_utils import best_similarity

SITE = "lolobun"
BASE_URL = "https://www.lolobun.com"


class LolobunSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("lolobun.com",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            "/ajax/Common.ashx",
            params={"op": "getSearchSuggest", "keyword": query},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        response = await self.client.get(url)
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        response = await self.client.get(chapter_url)
        if response.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        response.raise_for_status()
        return self.parse_chapter(response.text, chapter_url)

    def parse_search(self, payload: dict, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload.get("data") or []:
            # The suggest endpoint mixes the storefront's comics in with its
            # novels, often under the very same title.
            if item.get("EntityType") != "Novel":
                continue
            title = (item.get("Title") or "").strip()
            url = item.get("Url") or ""
            if not title or not url.startswith("/n/"):
                continue
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{BASE_URL}{url}",
                    title=title,
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        # Volume by volume rather than one selector over headings and items:
        # selectolax returns a comma selector's matches grouped by selector,
        # not in document order, which would detach every chapter from its
        # volume.
        for block in HTMLParser(html).css(".catalog-volume"):
            heading = block.css_first(".catalog-volume-title")
            volume = " ".join(heading.text().split()) if heading else None
            for item in block.css(".catalog-item"):
                link = item.css_first(".title a[href]")
                if link is None:
                    continue
                # Position, not the title: early chapters spell their numbers
                # out ("Chapter Three: ...") and later ones drop punctuation,
                # while the catalogue order is the one thing the site keeps
                # consistent.
                chapters.append(
                    ChapterRef(
                        number=Decimal(len(chapters) + 1),
                        url=f"{BASE_URL}{link.attributes['href']}",
                        title=" ".join(link.text().split()) or None,
                        volume=volume or None,
                    )
                )
        return chapters

    def parse_chapter(self, html: str, chapter_url: str) -> ChapterText:
        tree = HTMLParser(html)
        # A locked chapter still answers 200 and still fills the text box - with
        # a teaser of its first lines. Shipping that as the chapter would look
        # like a working download. The purchase panel is the one element that
        # differs: present on every page, hidden only when the chapter is free.
        purchase = tree.css_first(".order-vip-container")
        if purchase is not None and "hidden" not in (purchase.attributes.get("class") or "").split():
            raise ChapterUnavailable(f"{chapter_url} is locked to the LoLoBun app")
        box = tree.css_first(".text-content-box")
        if box is None:
            raise ChapterUnavailable(f"{chapter_url} has no chapter text")
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
```

If you re-recorded the fixtures, confirm the locked marker still holds. This should print `order-vip-container hidden` for the free chapter and `order-vip-container ` (no `hidden`) for the locked one:

```bash
grep -o 'class="order-vip-container[^"]*"' backend/tests/fixtures/sources/lolobun_chapter.html backend/tests/fixtures/sources/lolobun_locked.html
```

In `backend/app/sources/registry.py`, import `LolobunSource` and add `"lolobun": LolobunSource(),` to `NATIVE_SOURCES`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_lolobun.py tests/test_source_registry.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/sources/lolobun.py backend/app/sources/registry.py backend/tests/test_source_lolobun.py backend/tests/fixtures/sources/lolobun_*
git commit -m "feat(sources): add LoLoBun as a prose source"
```

---

### Task 13: novelight source

**Files:**
- Create: `backend/app/sources/novelight.py`
- Create fixtures: `backend/tests/fixtures/sources/novelight_search.html`, `novelight_book.html`, `novelight_chapters.json`, `novelight_chapter.json`, `novelight_locked.json`
- Modify: `backend/app/sources/registry.py` (`NATIVE_SOURCES`)
- Test: `backend/tests/test_source_novelight.py`

**Verified facts (fetched 2026-10-14):**
- There is no challenge; a browser-like User-Agent is enough. **Every `/ajax` and `/book/ajax` call needs `X-Requested-With: XMLHttpRequest`**, or it answers 403 HTML. No CSRF token or cookie is needed.
- Search: `GET /catalog/?search=<q>` returns server-rendered HTML.
  - Items are `.manga-grid-list a.item`, with the title in `.title` and the cover in `img[src]`, a relative `/media/...` path.
  - The page holds 30 items; no pagination is needed for matching.
- Book page: the numeric id is in a script, `const BOOK_ID = "403"`.
- Full chapter list: `GET /book/ajax/chapter-pagination?book_id=<id>&page=1&pagination=0` returns JSON `{"html": ...}` with every chapter.
  - Items are `a.chapter[href="/book/chapter/<id>"]`, newest first.
  - `.title` reads `74 chapter - <span>Name</span>`, or `12 vol. 66.2 chapter - ...`.
  - Locked chapters carry `.chapter-info .cost .fa-lock`.
- **Chapter numbers restart in every volume**: one 1,325-chapter book runs vol. 1 = 1–195, vol. 2 = 1–107. List position is the chapter number.
- Chapter text is **not in the chapter page**. It comes from `GET /book/ajax/read-chapter/<chapter_id>` as JSON `{"class": "<random>", "content": "<div class=\"chapter-text <random>\">..."}`.
  - Paragraphs are direct child `div`s. The junk is `div.advertisment` (sic) and `script`.
  - A locked chapter answers 200 with an empty `.chapter-text`.

**Interfaces:**
- Consumes: as Task 12.
- Produces: `NovelightSource(ProseSource)` with `site = "novelight"` and pure parsers:
  - `parse_search(html: str, titles: list[str]) -> list[Candidate]`
  - `parse_book_id(html: str) -> str`
  - `parse_chapters(html: str) -> list[ChapterRef]`
  - `parse_chapter(content: str, chapter_url: str) -> ChapterText`

- [ ] **Step 1: Copy the recorded fixtures**

These were recorded during planning:

```bash
for f in novelight_search.html novelight_book.html novelight_chapters.json novelight_chapter.json novelight_locked.json; do cp /private/tmp/claude-501/-Users-jackson-mafra-Downloads-Projects-soshuhen/aa9ec06c-f56d-43b2-86eb-e4332ea25803/scratchpad/ln/fx/$f backend/tests/fixtures/sources/; done
```

If that scratch directory is gone, re-record them (`book_id` 403):

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
D=backend/tests/fixtures/sources
curl -s -A "$UA" "https://novelight.net/catalog/?search=dragon" -o $D/novelight_search.html
curl -s -A "$UA" "https://novelight.net/book/the-long-journey-after-becoming-an-ancient-dragon" -o $D/novelight_book.html
curl -s -A "$UA" -H "X-Requested-With: XMLHttpRequest" "https://novelight.net/book/ajax/chapter-pagination?book_id=403&page=1&pagination=0" -o $D/novelight_chapters.json
curl -s -A "$UA" -H "X-Requested-With: XMLHttpRequest" "https://novelight.net/book/ajax/read-chapter/178702" -o $D/novelight_chapter.json
curl -s -A "$UA" -H "X-Requested-With: XMLHttpRequest" "https://novelight.net/book/ajax/read-chapter/217220" -o $D/novelight_locked.json
```

Re-recorded fixtures may change the counts. If they do, update the numeric assertions to match and say so in the commit message.

- [ ] **Step 2: Write the failing tests**

```python
"""Golden tests for Novelight, driven by recorded responses."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.base import ChapterUnavailable
from app.sources.novelight import NovelightSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
CHAPTER_URL = "https://novelight.net/book/chapter/178702"


def _source() -> NovelightSource:
    # client is never reached: every test here calls a pure parser directly.
    return NovelightSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_the_catalogue_grid():
    found = _source().parse_search(_read("novelight_search.html"), ["Shut Up, Malevolent Dragon"])
    assert len(found) == 7
    assert {c.source_site for c in found} == {"novelight"}
    assert found[0].source_url == (
        "https://novelight.net/book/"
        "shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you"
    )
    assert found[0].cover_url.startswith("https://novelight.net/media/")
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_the_book_id_is_read_from_the_page_script():
    assert _source().parse_book_id(_read("novelight_book.html")) == "403"


def test_chapters_run_oldest_first_numbered_by_position():
    html = json.loads(_read("novelight_chapters.json"))["html"]
    chapters = _source().parse_chapters(html)
    assert len(chapters) == 74
    assert chapters[0].number == Decimal(1)
    assert chapters[0].url == "https://novelight.net/book/chapter/178702"
    assert chapters[0].title == "The Beginning"
    assert chapters[-1].number == Decimal(74)
    assert chapters[-1].url == "https://novelight.net/book/chapter/217220"
    assert chapters[-1].title == "Negotiation"


def test_a_chapter_drops_the_ads_and_keeps_every_paragraph():
    content = json.loads(_read("novelight_chapter.json"))["content"]
    text = _source().parse_chapter(content, CHAPTER_URL)
    assert text.body.startswith(
        "<p>Deruo was, to put it simply, a rather unimpressive person.</p>"
    )
    assert "script" not in text.body
    assert "advertisment" not in text.body
    assert text.body.count("<p>") == 56


def test_a_locked_chapter_is_unavailable():
    content = json.loads(_read("novelight_locked.json"))["content"]
    with pytest.raises(ChapterUnavailable, match="locked"):
        _source().parse_chapter(content, CHAPTER_URL)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_novelight.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.sources.novelight'`.

- [ ] **Step 4: Implement**

`backend/app/sources/novelight.py`:

```python
"""Novelight (novelight.net).

Two things about this site shape everything below. Chapter text is never in
the page: the reader fetches it from an AJAX endpoint after load, and that
endpoint - like the chapter list - answers 403 without X-Requested-With.
And chapter numbers restart in every volume, so the number a title shows is
not unique within a book; the position in the full list is.
"""

import re
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    ChapterUnavailable,
    PageRef,
    ProseSource,
)
from app.sources.net import CatalogueRow, get_client
from app.sources.prose import clean_chapter_html
from app.text_utils import best_similarity

SITE = "novelight"
BASE_URL = "https://novelight.net"
AJAX = {"X-Requested-With": "XMLHttpRequest"}

_BOOK_ID = re.compile(r'const BOOK_ID = "(\d+)"')
_CHAPTER_ID = re.compile(r"/book/chapter/(\d+)")
_VOLUME = re.compile(r"^\s*(\d+)\s*vol\.", re.IGNORECASE)


class NovelightSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("novelight.net",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get("/catalog/", params={"search": query})
        response.raise_for_status()
        return self.parse_search(response.text, titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        page = await self.client.get(url)
        page.raise_for_status()
        book_id = self.parse_book_id(page.text)
        # pagination=0 is the whole list in one answer; without it the
        # endpoint pages by fifty.
        response = await self.client.get(
            "/book/ajax/chapter-pagination",
            params={"book_id": book_id, "page": 1, "pagination": 0},
            headers=AJAX,
        )
        response.raise_for_status()
        return self.parse_chapters(response.json()["html"])

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        match = _CHAPTER_ID.search(chapter_url)
        if match is None:
            raise ChapterUnavailable(f"{chapter_url} is not a Novelight chapter address")
        response = await self.client.get(
            f"/book/ajax/read-chapter/{match.group(1)}",
            headers={**AJAX, "Referer": chapter_url},
        )
        if response.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        response.raise_for_status()
        return self.parse_chapter(response.json()["content"], chapter_url)

    def parse_book_id(self, html: str) -> str:
        match = _BOOK_ID.search(html)
        if match is None:
            raise ChapterUnavailable("the book page no longer names its BOOK_ID")
        return match.group(1)

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in HTMLParser(html).css(".manga-grid-list a.item"):
            href = item.attributes.get("href")
            label = item.css_first(".title")
            title = " ".join(label.text().split()) if label else ""
            if not href or not title:
                continue
            image = item.css_first("img")
            cover = image.attributes.get("src") if image else None
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=urljoin(BASE_URL, href),
                    title=title,
                    cover_url=urljoin(BASE_URL, cover) if cover else None,
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        links = HTMLParser(html).css("a.chapter")
        chapters: list[ChapterRef] = []
        # The list arrives newest first; numbering runs from the oldest.
        for link in reversed(links):
            href = link.attributes.get("href")
            if not href:
                continue
            label = link.css_first(".title")
            name = label.css_first("span") if label else None
            volume = _VOLUME.match(label.text()) if label else None
            chapters.append(
                ChapterRef(
                    # Position, not the printed number: numbers restart every
                    # volume, and two chapters numbered 12 would collide on
                    # the (series, number) the pipeline keys chapters by.
                    number=Decimal(len(chapters) + 1),
                    url=urljoin(BASE_URL, href),
                    title=" ".join(name.text().split()) if name else None,
                    volume=volume.group(1) if volume else None,
                )
            )
        return chapters

    def parse_chapter(self, content: str, chapter_url: str) -> ChapterText:
        tree = HTMLParser(content)
        box = tree.css_first(".chapter-text")
        # A locked chapter answers 200 with the text container left empty.
        if box is None or not box.text().strip():
            raise ChapterUnavailable(f"{chapter_url} is locked or empty on Novelight")
        for junk in box.css(".advertisment, script"):
            junk.decompose()
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
```

In `backend/app/sources/registry.py`, import `NovelightSource` and add `"novelight": NovelightSource(),` to `NATIVE_SOURCES`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_novelight.py tests/test_source_registry.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/sources/novelight.py backend/app/sources/registry.py backend/tests/test_source_novelight.py backend/tests/fixtures/sources/novelight_*
git commit -m "feat(sources): add Novelight as a prose source"
```

---

### Task 14: empirenovel source, and seeding the three prose sites

**Files:**
- Create: `backend/app/sources/empirenovel.py`, `backend/alembic/versions/0020_seed_prose_sources.py`
- Create fixtures: `backend/tests/fixtures/sources/empirenovel_search.json`, `empirenovel_book.html`, `empirenovel_chapters.html`, `empirenovel_chapter.html`
- Modify: `backend/app/sources/registry.py` (`NATIVE_SOURCES`)
- Test: `backend/tests/test_source_empirenovel.py`, `backend/tests/test_source_registry.py` (append)

**Verified facts (fetched 2026-10-14 through the local FlareSolverr):**
- A plain request gets 403 with `cf-mitigated: challenge`. Replaying FlareSolverr's cookies with its User-Agent, which `SiteClient` already does, gets 200 for HTML and JSON. No extra headers are needed.
- Search: `GET /search-live?q=<q>` returns a JSON array of `{name, slug, status_id, summary, otherNames, cover}`.
  - `cover` is a flag, not a URL. The book page uses `/uploads/novel/<slug>/cover/cover_250x350.jpg`.
  - `/novels-list?search=` ignores the query.
- Book page `/novel/<slug>`: the "First Chapter" link is `.col-6.text-center a`, e.g. `/novel/<slug>/1`.
- Full chapter list in one request: `GET /select-partial/<slug>/<an existing chapter number>`.
  - Options are `select#chapter-list option[value="/novel/<slug>/<n>"]`, newest first.
  - It needs a chapter that exists; a bad one is 404.
- **The number is the URL's last segment, and it's messy**: one book has both `/01` and `/1`, others skip numbers that then 404. The first URL for a number wins, and a gap stays a gap.
- Chapter page `/novel/<slug>/<n>`: the body is `#read-novel`, made of `<p>`s with some `em` / `strong`.
  - The chrome inside it is an `h3` heading and `div`s holding the next link and the reader footer.
  - selectolax's `node.css()` **also matches the node itself**, so the container has to be skipped when removing `div`s.
  - A missing chapter is 404. No paywall was seen.

**Interfaces:**
- Consumes: as Task 12.
- Produces: `EmpireNovelSource(ProseSource)` with `site = "empirenovel"` and pure parsers:
  - `parse_search(payload: list, titles: list[str]) -> list[Candidate]`
  - `parse_first_chapter(html: str) -> str`
  - `parse_chapters(html: str) -> list[ChapterRef]`
  - `parse_chapter(html: str, chapter_url: str) -> ChapterText`
- Migration `0020_seed_prose_sources` adds `site_catalogue` rows (template `native`, lang `en`) and `source_pref` rows:
  - `lolobun` and `novelight`, enabled;
  - `empirenovel`, **disabled**, because it only works with FlareSolverr.

- [ ] **Step 1: Copy the recorded fixtures**

```bash
for f in empirenovel_search.json empirenovel_book.html empirenovel_chapters.html empirenovel_chapter.html; do cp /private/tmp/claude-501/-Users-jackson-mafra-Downloads-Projects-soshuhen/aa9ec06c-f56d-43b2-86eb-e4332ea25803/scratchpad/ln/fx/$f backend/tests/fixtures/sources/; done
```

If the scratch directory is gone, re-record them through FlareSolverr with the stack's `flaresolverr` profile up. POST `{"cmd":"request.get","url":...,"maxTimeout":60000}` to `http://flaresolverr:8191/v1` from inside the `api` container and save `solution.response`. The URLs are:
- `/search-live?q=dragon`
- `/novel/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you`
- `/select-partial/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you/1`
- `.../1`

- [ ] **Step 2: Write the failing tests**

```python
"""Golden tests for EmpireNovel, driven by responses recorded through FlareSolverr."""

import json
from decimal import Decimal
from pathlib import Path

from app.sources.empirenovel import EmpireNovelSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
BOOK = "shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you"


def _source() -> EmpireNovelSource:
    # client is never reached: every test here calls a pure parser directly.
    return EmpireNovelSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_reads_the_typeahead_payload():
    payload = json.loads(_read("empirenovel_search.json"))
    found = _source().parse_search(payload, ["The Divine Nine-Dragon Cauldron"])
    assert len(found) == 55
    assert found[0].title == "The Divine Nine-Dragon Cauldron"
    assert found[0].source_url == "https://www.empirenovel.com/novel/the-divine-nine-dragon-cauldron"
    assert found[0].cover_url == (
        "https://www.empirenovel.com/uploads/novel/the-divine-nine-dragon-cauldron/"
        "cover/cover_250x350.jpg"
    )


def test_the_first_chapter_is_read_off_the_book_page():
    first = _source().parse_first_chapter(_read("empirenovel_book.html"))
    assert first == f"https://www.empirenovel.com/novel/{BOOK}/1"


def test_the_dropdown_lists_every_chapter_numbered_by_url():
    chapters = _source().parse_chapters(_read("empirenovel_chapters.html"))
    assert len(chapters) == 195
    assert chapters[0].number == Decimal(1)
    assert chapters[0].url == f"https://www.empirenovel.com/novel/{BOOK}/1"
    assert chapters[-1].number == Decimal(195)


def test_a_duplicated_number_keeps_its_first_address():
    html = (
        '<select id="chapter-list">'
        '<option value="/novel/x/2">Chapter 2</option>'
        '<option value="/novel/x/02">Chapter 02</option>'
        '<option value="/novel/x/1">Chapter 1</option>'
        "</select>"
    )
    chapters = _source().parse_chapters(html)
    assert [(c.number, c.url) for c in chapters] == [
        (Decimal(1), "https://www.empirenovel.com/novel/x/1"),
        (Decimal(2), "https://www.empirenovel.com/novel/x/02"),
    ]


def test_a_chapter_keeps_its_paragraphs_and_drops_the_reader_chrome():
    text = _source().parse_chapter(
        _read("empirenovel_chapter.html"), f"https://www.empirenovel.com/novel/{BOOK}/1"
    )
    assert text.body.count("<p>") == 112
    assert "chapter-right" not in text.body
    assert text.images == []
```

Append to `backend/tests/test_source_registry.py`, in that file's existing style for registry reload tests:

```python
async def test_the_prose_natives_are_seeded_with_empirenovel_off():
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                text(
                    """
                    select c.key, c.template, p.enabled
                      from site_catalogue c join source_pref p on p.key = c.key
                     where c.key in ('lolobun', 'novelight', 'empirenovel')
                     order by c.key
                    """
                )
            )
        ).all()
    assert [(r.key, r.template, r.enabled) for r in rows] == [
        ("empirenovel", "native", False),
        ("lolobun", "native", True),
        ("novelight", "native", True),
    ]
```

(add `from sqlalchemy import text` and `from app.db import get_sessionmaker` if that file lacks them). If an earlier test in that module truncates `site_catalogue`, this assertion needs the rows re-seeded first. In that case, put the test in a new module, `tests/test_seed_prose_sources.py`, which runs against the migrated schema from the session fixture.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_empirenovel.py tests/test_source_registry.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'app.sources.empirenovel'`, and the seed rows are missing.

- [ ] **Step 4: Implement the source**

`backend/app/sources/empirenovel.py`:

```python
"""EmpireNovel (empirenovel.com).

Behind a Cloudflare challenge. Nothing here deals with it: SiteClient detects
the challenge and replays FlareSolverr's clearance, so without the
`flaresolverr` profile this source fails exactly the way every other
challenged site does.

The chapter number is the last segment of the chapter URL, and the site is
not careful with it - one book carries both /01 and /1, another skips numbers
that then 404. The first URL for a number wins, and a gap stays a gap.
"""

from decimal import Decimal, InvalidOperation
from typing import ClassVar
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from app.sources.base import (
    Candidate,
    ChapterRef,
    ChapterText,
    ChapterUnavailable,
    PageRef,
    ProseSource,
)
from app.sources.net import CatalogueRow, get_client
from app.sources.prose import clean_chapter_html
from app.text_utils import best_similarity

SITE = "empirenovel"
BASE_URL = "https://www.empirenovel.com"


class EmpireNovelSource(ProseSource):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("empirenovel.com",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        # The typeahead endpoint is the only search that honours the query;
        # /novels-list ignores its search parameter.
        response = await self.client.get("/search-live", params={"q": query})
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        page = await self.client.get(url)
        page.raise_for_status()
        first = self.parse_first_chapter(page.text)
        # The chapter dropdown is the whole list in one request, where the
        # book page pages by thirty. It is served relative to any chapter that
        # exists, which is why the first one is read off the book page.
        response = await self.client.get(f"/select-partial{first.removeprefix(BASE_URL)}")
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText:
        response = await self.client.get(chapter_url)
        if response.status_code in (404, 410):
            raise ChapterUnavailable(f"{chapter_url} is gone")
        response.raise_for_status()
        return self.parse_chapter(response.text, chapter_url)

    def parse_search(self, payload: list, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload or []:
            slug = item.get("slug")
            title = (item.get("name") or "").strip()
            if not slug or not title:
                continue
            names = [title, *(item.get("otherNames") or [])]
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{BASE_URL}/novel/{slug}",
                    title=title,
                    # The payload only says whether a cover exists; the path
                    # is the one the book page itself uses.
                    cover_url=(
                        f"{BASE_URL}/uploads/novel/{slug}/cover/cover_250x350.jpg"
                        if item.get("cover")
                        else None
                    ),
                    alt_titles=[name for name in names[1:] if isinstance(name, str)],
                    score=round(
                        max(
                            (best_similarity([n for n in names if isinstance(n, str)], t)
                             for t in titles),
                            default=0.0,
                        ),
                        4,
                    ),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_first_chapter(self, html: str) -> str:
        for link in HTMLParser(html).css(".col-6.text-center a[href]"):
            href = link.attributes["href"]
            if "/novel/" in href:
                return urljoin(BASE_URL, href)
        raise ChapterUnavailable("the book page links to no chapter")

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        seen: set[Decimal] = set()
        chapters: list[ChapterRef] = []
        # Newest first in the dropdown; the pipeline does not care about
        # order, but reading it oldest first makes "first URL wins" mean the
        # lower, original address.
        for option in reversed(HTMLParser(html).css("select#chapter-list option")):
            value = option.attributes.get("value") or ""
            try:
                number = Decimal(value.rstrip("/").rsplit("/", 1)[-1])
            except InvalidOperation:
                continue
            if number in seen:
                continue
            seen.add(number)
            chapters.append(ChapterRef(number=number, url=urljoin(BASE_URL, value)))
        return chapters

    def parse_chapter(self, html: str, chapter_url: str) -> ChapterText:
        box = HTMLParser(html).css_first("#read-novel")
        if box is None:
            raise ChapterUnavailable(f"{chapter_url} has no chapter text")
        # The heading, the next-chapter link row and the reader footer all sit
        # inside the text container as divs and an h3. css() on a node also
        # matches the node itself, so the container is skipped by identity.
        for junk in box.css("div, h3"):
            if junk.attributes.get("id") != "read-novel":
                junk.decompose()
        body, images = clean_chapter_html(box.html, chapter_url)
        return ChapterText(
            title=None,
            body=body,
            images=[PageRef(url=url, headers={"Referer": chapter_url}) for url in images],
        )
```

In `backend/app/sources/registry.py`, import `EmpireNovelSource` and add `"empirenovel": EmpireNovelSource(),` to `NATIVE_SOURCES`.

- [ ] **Step 5: Seed the catalogue**

`backend/alembic/versions/0020_seed_prose_sources.py`, shaped after `0013_seed_v1_sites.py`:

```python
"""seed the three prose sources

Revision ID: 0020_seed_prose_sources
Revises: 0019_series_kind
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_seed_prose_sources"
down_revision: str | None = "0019_series_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# EmpireNovel arrives disabled: every request it makes meets a Cloudflare
# challenge, and without the flaresolverr profile enabling it would only add a
# source that fails every search. Turning it on is the user's call, made in the
# same place they turn on the solver.
SITES = [
    ("lolobun", "LoLoBun", "https://www.lolobun.com", True),
    ("novelight", "Novelight", "https://novelight.net", True),
    ("empirenovel", "EmpireNovel", "https://www.empirenovel.com", False),
]

CATALOGUE = sa.text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
    values (:key, :name, 'native', :base_url, 'en', false, '{}'::jsonb, '1', true)
    on conflict (key) do nothing
    """
)
PREFERENCE = sa.text(
    "insert into source_pref (key, enabled) values (:key, :enabled) on conflict (key) do nothing"
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, base_url, enabled in SITES:
        bind.execute(CATALOGUE, {"key": key, "name": name, "base_url": base_url})
        bind.execute(PREFERENCE, {"key": key, "enabled": enabled})


def downgrade() -> None:
    bind = op.get_bind()
    keys = [key for key, *_ in SITES]
    bind.execute(sa.text("delete from source_pref where key = any(:keys)"), {"keys": keys})
    bind.execute(sa.text("delete from site_catalogue where key = any(:keys)"), {"keys": keys})
```

Check the column list against `0013_seed_v1_sites.py` and the current `site_catalogue` schema. If a later migration added a not-null column without a default, include it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_source_empirenovel.py tests/test_source_registry.py tests/test_migration_chain.py tests/test_routes_sources.py tests/test_catalogue_repo.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/sources/empirenovel.py backend/app/sources/registry.py backend/alembic/versions/0020_seed_prose_sources.py backend/tests/test_source_empirenovel.py backend/tests/test_source_registry.py backend/tests/fixtures/sources/empirenovel_*
git commit -m "feat(sources): add EmpireNovel and seed the three prose sources"
```

---

### Task 15: Frontend: kind badge, kind control, Komga links for prose

**Files:**
- Create: `frontend/src/features/series/KindControl.tsx`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/features/series/useSeriesDetail.ts`, `frontend/src/features/series/SeriesDetailPage.tsx`, `frontend/src/features/series/SeriesHeader.tsx`, `frontend/src/features/series/ChapterTable.tsx`

**Interfaces:**
- Consumes: `kind` in series payloads and `POST /api/series/{id}/kind` (Task 9).
- Produces: `Series.kind: 'comic' | 'prose' | null`; `api.setKind(id: number, kind: 'comic' | 'prose')`; `useSeriesDetail(...).setKind(kind)`; `<KindControl kind onChange />`; `ChapterTable` prop `prose: boolean`.

- [ ] **Step 1: Types and API client**

In `frontend/src/lib/api.ts`, add to `interface Series` after `auto_download: boolean`:

```ts
  /** Comic or prose. Null when no provider said, which behaves as comic. */
  kind: 'comic' | 'prose' | null
```

and to the `api` object, after `setAutoDownload`:

```ts
  setKind: (id: number, kind: 'comic' | 'prose') =>
    request<{ ok: boolean; kind: 'comic' | 'prose' }>(`/api/series/${id}/kind`, {
      method: 'POST',
      body: JSON.stringify({ kind }),
    }),
```

- [ ] **Step 2: The hook**

In `frontend/src/features/series/useSeriesDetail.ts`, add a `setKind` callback beside `toggleAutoDownload`, with the same apply-then-confirm-and-roll-back shape, and return it from the hook:

```ts
  // Same rollback-on-rejection shape as the auto-download toggle above.
  const setKind = useCallback(
    async (kind: 'comic' | 'prose') => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current ? { ...current, series: { ...current.series, kind } } : current
      })
      try {
        await api.setKind(id, kind)
      } catch (failure) {
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )
```

- [ ] **Step 3: The control**

`frontend/src/features/series/KindControl.tsx`. Use only existing `ui/` primitives (`Card`, `SegmentedControl`) and classes that already appear in `DownloadControls.tsx`, so no new Tailwind class is introduced:

```tsx
import { useState } from 'react'

import { Card, SegmentedControl } from '../../ui'

type Kind = 'comic' | 'prose'

// What decides which sources a series is searched against and which file it
// is downloaded as. Most series never need it - the list providers say - and
// it is here for the ones whose provider said nothing or said it wrong.
export function KindControl({
  kind,
  onChange,
}: {
  kind: Kind | null
  onChange: (kind: Kind) => Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)

  const choose = (next: Kind) => {
    setError(null)
    onChange(next).catch((failure: unknown) =>
      setError(failure instanceof Error ? failure.message : String(failure)),
    )
  }

  return (
    <Card>
      <div className="flex flex-col gap-space-sm">
        <h3 className="text-title-md text-on-surface">Format</h3>
        <SegmentedControl<Kind>
          options={[
            { value: 'comic', label: 'Comic' },
            { value: 'prose', label: 'Light novel' },
          ]}
          value={kind ?? 'comic'}
          onChange={choose}
        />
        {error && <p className="text-body-sm text-error">{error}</p>}
      </div>
    </Card>
  )
}
```

Before keeping it, open `DownloadControls.tsx` and copy its actual heading and error-text class names in place of `text-title-md text-on-surface` / `text-body-sm text-error` if they differ. Then check that `Card` accepts `children` with no other required props.

- [ ] **Step 4: Wire it in**

In `SeriesDetailPage.tsx`, take `setKind` from `useSeriesDetail` and render, directly above `<DownloadControls`:

```tsx
          <KindControl kind={series.kind} onChange={setKind} />
```

and pass `prose={series.kind === 'prose'}` to `<ChapterTable`.

In `SeriesHeader.tsx`, after the auto-download badge:

```tsx
        {series.kind === 'prose' && <Badge tone="tertiary">Light novel</Badge>}
```

Skip the badge when the `format` badge already reads "Light Novel": check `formatSeriesFormat` in `lib/format.ts`. If it maps `NOVEL` / `LIGHT_NOVEL` to a label already, show the kind badge only when `format` is null.

In `ChapterTable.tsx`, add the prop `prose: boolean` (documented as "Prose chapters are EPUBs, which only Komga reads; the image reader would refuse them"). In the row actions, render the internal `Read` link only when `!prose`. When `prose` is true and the chapter has a `komga_book_id`, render the existing Komga link with the visible label "Read in Komga" (reusing the `Read` link's classes, an `<a>` with `target="_blank" rel="noreferrer"`) instead of the icon-only one.

- [ ] **Step 5: Build and verify the classes exist**

Run from `frontend/`:

```bash
npm run build
```

Expected: `tsc -b` and the Vite build both succeed. Then, for every class string in the new or changed JSX, confirm the built CSS contains it. For example:

```bash
grep -o 'gap-space-sm' dist/assets/*.css | head -1
```

Any class with no match does not exist. Replace it with one that does, as `CLAUDE.md` warns.

- [ ] **Step 6: Check it in the browser**

Start the stack (`docker compose build api && docker compose up -d --force-recreate api worker worker-download web`) or `npm run dev` against a running API. Open a series detail page and switch Format to "Light novel":
- the badge appears;
- the chapter rows lose the internal Read link;
- reloading keeps the choice.

Switch back to Comic.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(web): show and set a series' format, and read light novels in Komga"
```

---

### Task 16: Documentation

**Files:**
- Modify: `docs/architecture.md`, `docs/data-model.md`, `docs/features.md`, `CLAUDE.md`

- [ ] **Step 1: Read each file's current structure** and add to the matching sections, keeping each file's voice:

`docs/architecture.md`: under the job chain, one paragraph saying that `series.kind` routes a series to prose or comic sources (`match_search`, the mapping guard), and that the download handlers branch once at the archive write: `write_epub` for prose, `write_cbz` for comics, with batching, leasing and retries shared.

`docs/data-model.md`: the `series.kind` column (`comic` / `prose` / null, null behaves as comic, check constraint), how it's set (list sync from entries with mixed resolving to comic; `POST /api/series/{id}/kind`), and `meta.kind_locked`.

`docs/features.md`: a "Light novels" section covering:
- novels on MAL and AniList are recognised;
- they are searched on LoLoBun, Novelight and EmpireNovel;
- each chapter downloads as an EPUB and is read in Komga;
- LoLoBun locks most chapters to its app, and those show as skipped;
- EmpireNovel needs the `flaresolverr` compose profile;
- the Format control on the series page corrects a wrong kind.

`CLAUDE.md`, "Module boundaries": one paragraph:

> A source declares its `kind`. Comic sources subclass `Source` and list page images; prose sources subclass `ProseSource` and return a `ChapterText` from `fetch_chapter`. Ask a source its kind (`kind_of`) rather than checking for a method, and resolve a mapping's source with `get_comic_source` / `get_prose_source` where the kind matters, so a crossed mapping fails by name.

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md docs/data-model.md docs/features.md CLAUDE.md
git commit -m "docs: describe light novel support"
```

---

### Task 17: Full checks and end-to-end verification

- [ ] **Step 1: Full suite on a fresh database**

```bash
docker rm -f manga-pg-ln-fresh 2>/dev/null; docker run -d --name manga-pg-ln-fresh -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5435:5432 postgres:17-alpine
```

Wait until it accepts connections, then from `backend/`:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5435 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: all tests pass and ruff reports nothing. A failure only on the fresh database means some module truncates a table it doesn't own a fixture for; fix that, don't skip it.

- [ ] **Step 2: Rebuild the stack**

```bash
docker compose build api && docker compose up -d --force-recreate api worker worker-download web
```

- [ ] **Step 3: End to end, per source**

For one real novel on each of lolobun, novelight and empirenovel (empirenovel with the `flaresolverr` profile up):
1. Make sure the series exists (from a list, or with "track locally") and its Format reads "Light novel".
2. Run search, confirm the mapping in Review, and download chapters 1–3.
3. Confirm in the Jobs screen that the batch finished, with locked chapters logged as unavailable.
4. In Komga (`:25600`): the series appears once, its books are ordered 1, 2, 3, titles read "<Series> - Chapter N: ...", thumbnails show the series cover, and the web reader opens a chapter.
5. Read one chapter to the end in Komga's reader, run a Komga scan for the series, and confirm `progress_push` advances the list entry (or the local progress).

- [ ] **Step 4: Report**

Write down which of the steps above passed, with any that failed and how. Then use superpowers:finishing-a-development-branch.
