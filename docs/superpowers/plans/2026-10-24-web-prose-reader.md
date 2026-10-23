# Web Prose Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read prose EPUBs already in the library from the web interface, list a novel's volumes on its page, and stop asking source-less series with library content for a mapping.

**Architecture:** A pure `reader/epub_text.py` reads and sanitises EPUB sections. `reader_service.py` and `routes_reader.py` gain prose routes under `/api/reader/prose/…`, volume completion, and position by volume. The frontend gets a `ProseContents` list on the series page and a new `features/prose-reader/` screen.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, Alembic, selectolax; React 19, react-router 7, Tailwind 4 (tokens in `frontend/tailwind.config.ts`).

**Spec:** `docs/superpowers/specs/2026-10-24-web-prose-reader-design.md`

## Global Constraints

- Commits: microcommits, English, **no attribution trailer of any kind**.
- Never touch `backend/app/api/routes_chapters.py`, `backend/app/api/routes_volumes.py`, or `mobile/`.
- `GET /api/reader/series/{id}/resume` keeps the shape `{chapter_id, page}`.
- `POST /api/reader/volumes/{id}/complete` accepts an optional `{"read_at": <aware datetime>}` body and answers `{"progress_queued": bool, "komga_queued": bool}`; 404 unknown, 409 web edition.
- Series detail volume objects carry `id`, `file_path`, `first_part`, `last_part`, `readable`.
- No colour, size, radius or spacing literal in a component; tokens live in `frontend/tailwind.config.ts`. Verify new classes by grepping `frontend/dist/` after `npm run build`.
- Feature folders never import from each other.
- Comments explain why, never what.
- Tests: `POSTGRES_HOST=localhost POSTGRES_PORT=5435 .venv/bin/python -m pytest tests -q` from `backend/`; `ruff check app/ tests/`.
- The user's PDFs/EPUBs are never fixtures; tests build their own EPUBs.

## Review Focus

1. A malicious or sloppy EPUB (`<script>`, `onload=`, `javascript:` links, remote `<img src="http://…">`, `style` attributes) must render as plain text and local images only. Test in Task 4.
2. A row whose `file_path` points outside the library or at a missing file: no Read button (`readable: false`) and the route answers 404, never a file read. Tests in Tasks 2 and 5.
3. Rereading an earlier volume after a later one must not lower any list. Test in Task 6 (`progress_push` path, existing `pushable_volume`), asserted by a test that completing volume 3 when MAL stands at 10 still queues jobs but pushes nothing.
4. An image `href` that escapes the EPUB (`../../etc/passwd`) or names a non-image manifest item is 404. Test in Task 4/5.
5. A position saved for a volume must not break the comic `/resume` or the reading-recency ordering. Test in Task 3.

---

### Task 1: `local` series state

**Files:**
- Modify: `backend/app/api/routes_series.py` (LIST_SQL, LIST_SQL_ONE, `_state_of`, REVIEW_QUEUE_SQL)
- Modify: `backend/app/api/routes_dashboard.py` (MAPPINGS_SQL)
- Modify: `backend/app/mcp/tools.py` (`SERIES_STATES`)
- Modify: `docs/data-model.md` or `docs/features.md` where series states are listed
- Test: `backend/tests/test_local_state.py`

**Interfaces:**
- Produces: `series.state == "local"` in list and detail; LIST_SQL rows carry `volumes_downloaded: int`.

- [ ] Step 1: Tests: `test_unmapped_series_with_a_downloaded_volume_is_local`, `test_unmapped_series_with_a_downloaded_chapter_is_local`, `test_unmapped_series_with_nothing_downloaded_needs_review`, `test_a_failed_chapter_still_reads_failed`, `test_local_series_leave_the_review_queue` (GET `/api/series/review` excludes it), `test_local_series_leave_the_dashboard_pending_count`.
- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Add a separately grouped `volume` subquery (`count(*) filter (where state='downloaded') as downloaded`) joined like `ch`; `_state_of` returns `"local"` when `not row.source_url and (row.downloaded or row.volumes_downloaded)`. Review queue and MAPPINGS_SQL add the same `not exists (… downloaded chapter) and not exists (… downloaded volume)` condition. Add `"local"` to `SERIES_STATES`.
- [ ] Step 4: Run full suite, PASS (fix any test that relied on the old state).
- [ ] Step 5: Commit `feat(series): call a source-less series with library content local`.

### Task 2: Volume and chapter fields in series detail

**Files:**
- Modify: `backend/app/api/routes_series.py` (detail volume and chapter queries)
- Test: `backend/tests/test_series_detail_volumes.py`

**Interfaces:**
- Produces: volume `{id, number, edition, title, status, state, last_updated, revised, komga_book_id, file_path, first_part, last_part, readable}`; chapter gains `readable`.
- `readable` = `file_path` set, `Path(file_path).is_file()`, and `archive.inside(path, get_settings().library_path)`. A helper `readable(file_path: str | None) -> bool` in `reader_service.py`, reused by Task 5.

- [ ] Step 1: Tests: volume with a real file under a tmp library (monkeypatch `library_path`) has `readable True` and its `id`/`file_path`; missing file → `False`; file outside library → `False`; web volume exposes `first_part`/`last_part` as floats.
- [ ] Step 2–4: fail, implement, pass.
- [ ] Step 5: Commit `feat(series): expose volume ids, files and ranges in series detail`.

### Task 3: Position by volume (migration 0029)

**Files:**
- Create: `backend/alembic/versions/0029_reading_position_volume.py` (revises `0028_volume_edition`)
- Modify: `backend/app/models.py` (`ReadingPosition`)
- Modify: `backend/app/api/reader_service.py` (`save_position`, `resume`)
- Modify: `backend/app/api/routes_reader.py` (`PositionIn`)
- Modify: `docs/data-model.md` (`reading_position`)
- Test: `backend/tests/test_reader_position_volume.py`

**Interfaces:**
- Produces: `save_position(session, series_id, *, chapter_id: int | None, volume_id: int | None, page: int, fraction: float | None = None, read_at=None) -> bool`. Callers updated to keyword form.
- `PositionIn`: `chapter_id: int | None`, `volume_id: int | None`, `page >= 0`, `fraction: float | None` in `[0, 1]`, `read_at`; a model validator requires exactly one id (422 otherwise).
- Migration: `chapter_id` nullable; add `volume_id` (FK `volume.id` on delete cascade, nullable), `fraction` (`Float`, nullable); check `reading_position_one_target` = `(chapter_id is null) <> (volume_id is null)`. Downgrade deletes volume rows first.

- [ ] Step 1: Tests: put a volume position → row has `volume_id`, `chapter_id` null, `fraction`; volume from another series → 404; both ids → 422; neither → 422; existing chapter body unchanged still works; comic `/resume` with a saved volume position falls through to the furthest-read fallback; `last_read_at` in the library list still reflects the volume position's `updated_at`.
- [ ] Step 2–4: fail, implement, pass. `test_migration_chain.py` must pass.
- [ ] Step 5: Commit `feat(reader): save a reading position inside a volume`.

### Task 4: EPUB text module

**Files:**
- Create: `backend/app/reader/epub_text.py`
- Test: `backend/tests/test_epub_text.py` (builds EPUB 2 and EPUB 3 zips in `tmp_path`, plus one from `downloader.epub.write_epub`)

**Interfaces:**
- Produces:
  - `class EpubBroken(ValueError)`
  - `@dataclass(frozen=True) class Section: index: int; title: str | None; href: str`
  - `sections(path: Path) -> list[Section]` — linear spine items, nav document excluded; titles from EPUB 3 nav, else NCX, else None.
  - `section_html(path: Path, index: int, resource_url: Callable[[str], str]) -> str` — sanitised body; `IndexError` for a bad index.
  - `resource(path: Path, href: str) -> tuple[bytes, str]` — `(data, media_type)` for a manifest item whose media type starts with `image/`; `KeyError` otherwise.
- Allowlist tags: `p h1 h2 h3 h4 h5 h6 em i b strong u s small span div section blockquote ul ol li br hr img figure figcaption sup sub table thead tbody tr th td a`. Attributes kept: `img[src, alt]` only. `a` loses `href`. Removed with content: `script style iframe object embed svg math head noscript template form button input`. Other tags unwrap. `img src` resolved relative to the section's href (posix), normalised; a src that leaves the EPUB root or is absolute/remote is dropped with its `img`.

- [ ] Step 1: Tests: `test_sections_follow_the_spine_with_nav_titles`, `test_ncx_titles_when_there_is_no_nav`, `test_written_chapter_epub_has_one_section`, `test_script_and_handlers_are_removed`, `test_remote_and_escaping_images_are_dropped`, `test_local_images_point_at_the_resource_route`, `test_resource_refuses_non_images_and_unknown_hrefs`, `test_broken_zip_raises_epub_broken`.
- [ ] Step 2–4: fail, implement with `zipfile` + `selectolax.parser.HTMLParser` (or lexbor), pass.
- [ ] Step 5: Commit `feat(reader): read and sanitise EPUB sections`.

### Task 5: Prose reader routes

**Files:**
- Modify: `backend/app/api/reader_service.py`
- Modify: `backend/app/api/routes_reader.py`
- Modify: `backend/app/settings_store.py` (`READER_PROSE_FONT_SIZE = "reader_prose_font_size"` default `"3"`, `READER_PROSE_THEME = "reader_prose_theme"` default `"dark"`)
- Modify: `backend/tests/test_reader_api.py` (prose refusal message now names the web reader, not Komga)
- Test: `backend/tests/test_prose_reader_api.py`

**Interfaces:**
- Consumes: Task 2 `readable`, Task 3 position columns, Task 4 module.
- Produces (service): `ProseBook` dataclass `{kind: Literal['chapter','volume'], id, series_id, series_title, title, number: Decimal, edition: str | None, path: Path}`; `prose_book(session, kind, id) -> ProseBook` raising `ChapterMissing` (404, unknown or not readable), `WrongKind` (409: comic chapter, web volume); `prose_neighbours`, `prose_position`, `prose_prefs`, `save_prose_prefs`, `prose_resume(session, series_id) -> dict`.
- Produces (routes):
  - `GET /api/reader/prose/{kind}/{id}` → `{kind, id, series:{id,title}, title, number, edition, sections:[{index,title}], previous:{kind,id,number,title}|null, next: same|null, position:{section,fraction}|null, prefs:{font_size,theme}}`
  - `GET /api/reader/prose/{kind}/{id}/sections/{index}` → `{index, title, html}`; images point at `/api/reader/prose/{kind}/{id}/resources/{href}`
  - `GET /api/reader/prose/{kind}/{id}/resources/{href:path}` → bytes, `Cache-Control: IMMUTABLE`
  - `GET|PUT /api/reader/prose/prefs` `{font_size: int 1..7, theme: 'light'|'sepia'|'dark'}`
  - `GET /api/reader/prose/series/{id}/resume` → `{kind, id, section, fraction}`; 404 when nothing readable.
  - `EpubBroken` → 422. `reader_service.chapter()` drops the prose refusal; `manifest` and `page` raise `ProseChapter` themselves (409, detail `"this is a light novel chapter; open it in the novel reader"`).
- Neighbours: chapters by number among readable prose chapters; volumes by number within the same edition among readable volumes.
- Resume order: saved position (if its book is readable) → first readable light volume with number > max `user_progress_volume` → first readable chapter with number > furthest read → first readable book.

- [ ] Step 1: Tests: manifest for a light volume (sections, next volume, position null then set after a PUT position); section HTML for a written chapter EPUB; resource bytes; web volume → 409; comic chapter → 409; volume with missing file → 404; prefs default then saved; resume returns saved volume position, then first unread volume when none saved.
- [ ] Step 2–4: fail, implement, pass.
- [ ] Step 5: Commit `feat(reader): serve prose EPUBs to the web reader`.

### Task 6: Completing prose chapters and volumes

**Files:**
- Modify: `backend/app/api/routes_reader.py` (`complete`, new `complete_volume`)
- Modify: `backend/app/handlers/komga_read_progress.py`
- Test: `backend/tests/test_reader_progress.py` (extend), `backend/tests/test_volume_complete.py`

**Interfaces:**
- `KOMGA_READ_PROGRESS` payload gains optional `push_series_id: int`; after marking, the handler enqueues `JobType.PROGRESS_PUSH` `{"series_id": n}` with `dedupe_key=f"progress_push:{n}"` (check the cron's own key in `app/cron.py` and reuse it if it has one).
- `POST /api/reader/volumes/{id}/complete` body `CompleteIn | None`.

- [ ] Step 1: Tests: prose chapter complete queues `PROGRESS_WRITE` like a comic one; light volume complete with a book id queues `KOMGA_READ_PROGRESS` `{"book_id": b, "push_series_id": s}` and answers `{"progress_queued": True, "komga_queued": True}`; without a book id answers both False and queues nothing; web volume → 409; unknown → 404; accepts `{"read_at": "…Z"}`; running the handler with a fake Komga client queues one `PROGRESS_PUSH`; running it twice leaves one pending push. Rereading: with MAL at volume 10, `pushable_volume(3, None, 10)` is None (existing unit) — add a route-level test that the push job runs and leaves `user_progress_volume` at 10 using the existing `test_progress_push.py` fakes.
- [ ] Step 2–4: fail, implement, pass.
- [ ] Step 5: Commit `feat(reader): finish a light volume from the reader`.

### Task 7: Frontend API and `local` in the interface

**Files:**
- Modify: `frontend/src/lib/api.ts` (`SeriesState` adds `'local'`; `SeriesVolume` adds `id, file_path, first_part, last_part, readable`; `SeriesChapter` adds `readable`; types `ProseKind`, `ProseManifest`, `ProseSection`, `ProsePrefs`, `ProseResume`; clients `proseManifest(kind,id)`, `proseSection(kind,id,index)`, `proseResume(seriesId)`, `proseResourceUrl`, `saveProsePrefs`, `saveProsePosition(seriesId, {kind,id,page,fraction})`, `completeVolume(id)`)
- Modify: `frontend/src/features/library/CoverCard.tsx`, `frontend/src/features/library/SeriesTable.tsx`, `frontend/src/features/series/SeriesHeader.tsx`, `frontend/src/features/series/MappingPanel.tsx`

**Interfaces:**
- `MappingPanel` gains prop `local: boolean`: when true, the header copy reads "Reads from files in your library" and research/remap sit behind a "Find a source" secondary button.
- CoverCard: `local` note `{ text: 'In your library', icon: 'book', tone: 'text-on-surface-variant' }`; no warning styling.
- SeriesHeader: `<Badge tone="tertiary">Local</Badge>`. SeriesTable label `Local`, neutral tone (`bg-surface-container-high text-on-surface-variant`).

- [ ] Step 1: `npm run build` passes; grep `frontend/dist/assets/*.css` for every new class.
- [ ] Step 2: Commit `feat(web): show local series without asking for a mapping`.

### Task 8: Volumes in the main column for prose

**Files:**
- Create: `frontend/src/features/series/ProseContents.tsx`
- Modify: `frontend/src/features/series/SeriesDetailPage.tsx` (tab label "Contents", render `ProseContents` and skip `VolumesPanel` when `series.kind === 'prose'`)

**Interfaces:**
- `ProseContents({ volumes, chapters, progress, volumeProgress, komgaBaseUrl, onBookmark })`; `volumeProgress` = max `user_progress_volume` over `detail.entries` (null-safe).
- Groups: both editions → "Light novel" then "Web novel" headings; one edition → no heading. Web volume rows expand to chapters with `first_part <= number <= last_part`; the volume holding the first unread chapter starts expanded. Chapters in no range → "Other chapters". Read link: `/read/prose/volume/:id` and `/read/prose/chapter/:id`, shown only when `readable`. Read marks per spec.

- [ ] Step 1: `npm run build`; grep dist for new classes.
- [ ] Step 2: Commit `feat(web): list a novel's volumes on its page`.

### Task 9: The prose reader screen

**Files:**
- Modify: `frontend/tailwind.config.ts` (colours `prose-light #faf8f3`, `on-prose-light #1f1d1a`, `prose-sepia #f4ecd8`, `on-prose-sepia #3b2f22`, `prose-dark #121212`, `on-prose-dark #d6d3cc`; fontSize `prose-1`..`prose-7` from 0.875rem to 1.625rem in 0.125rem steps with line height 1.7; maxWidth `prose-column: 40rem`)
- Modify: `frontend/src/styles/index.css` (`.prose-text` descendant rules from tokens via `theme()`: paragraph spacing, headings, images max-width 100%, centred figures)
- Create: `frontend/src/features/prose-reader/ProseReaderPage.tsx`, `ProseSettings.tsx`, `ProseContentsSheet.tsx`, `EndOfBook.tsx`, `useProsePosition.ts`
- Move: `frontend/src/features/reader/ReaderSheet.tsx` → `frontend/src/ui/ReaderSheet.tsx` (both readers use it; update imports)
- Modify: `frontend/src/app/routes.tsx` (`read/prose/:kind/:id` outside the shell, before `read/:chapterId`)
- Modify: `frontend/src/features/reader/ResumePage.tsx` (for a prose series, ask `proseResume` and navigate to `/read/prose/:kind/:id`). It needs the series kind: add a `?prose=1` query from the link in SeriesHeader, or try `proseResume` when `readerResume` 404s — use the latter, it needs no caller change.
- Modify: `docs/features.md` (reading novels)

**Interfaces:**
- Route component keyed by `${kind}-${id}` (fresh state per book, as `ReaderRoute` does).
- Loads manifest, then all sections in parallel; renders them in order inside `.prose-text` with `text-prose-N` and the theme's bg/text classes on the page root.
- `useProsePosition(seriesId, kind, id)`: tracks the section whose top is last above the viewport's top third and its scrolled fraction; saves debounced 1500 ms and on `pagehide`/unmount via `saveProsePosition`. On load, scrolls to `position` after sections render.
- Top bar: back to `/series/:id`, title, current section title, contents and settings buttons; hides on scroll down, shows on scroll up.
- Settings: font size − / + (1..7), theme segmented control (light, sepia, dark); applies at once, saves via `saveProsePrefs`.
- End: "Mark as read" → `completeChapter` or `completeVolume`; "Next …" when `next`, which completes then navigates.

- [ ] Step 1: `npm run build`; grep dist for `text-prose-`, `bg-prose-`, `max-w-prose-column`, `.prose-text`.
- [ ] Step 2: Commit in microcommits: tokens + css; ReaderSheet move; screen + route; resume branch; docs.

### Task 10: Verify end to end on series 308

- [ ] Restore a dump of the live database into a new database `manga_copy` on the 5435 container (`docker exec soshuhen-postgres-1 pg_dump -U manga manga | docker exec -i manga-pg-web-reader psql -U manga -d manga_copy`), run `alembic upgrade head` on it, start the worktree api against it with `LIBRARY_PATH` pointing at the host library read-only, and the frontend dev server; open series 308, read a volume, change font/theme, reload to check resume, mark read and check the queued `komga_read_progress` job. Do not let that api's worker run (no jobs reach the real Komga or lists).
- [ ] Full backend suite + ruff + `npm run build` pass.
- [ ] Open PR, wait for all checks, merge with `--merge`.
