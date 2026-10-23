# Novel PDF Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user drop novel PDFs on a prose series' page, review how each one was read and what it will be named, and import them as prose chapter EPUBs (web novel) or whole-volume EPUBs (light novel).

**Architecture:** A new pure edge package `app/importer/` reads PDFs, numbers their entries and turns page text into chapter XHTML, with no database access. `api` stages the uploads on the shared `reader-cache` volume and returns a plan built from them. The user's confirmation enqueues an `import_files` job on the download lane. That job, which runs in the only process allowed to write `/manga`, writes the EPUBs through the existing `write_epub`, inserts `chapter` and `volume` rows, and enqueues `komga_scan`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, pypdf (BSD-3, new), python-multipart (Apache-2.0, new, FastAPI's form parser), React + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-10-23-novel-pdf-import-design.md`

## Global Constraints

- `api` never writes `/manga`. Only the `import_files` job on `worker-download` does.
- `app/importer/` never touches the database, like `providers/`, `sources/` and `downloader/`.
- Nothing is written to `/manga` or to `chapter`/`volume` until the user presses **Import**.
- The import never marks anything read and never enqueues `progress_push`, `progress_write` or `list_write`.
- `volume.number` is the light novel's volume number for both editions.
- A light-novel PDF never produces `chapter` rows.
- Prose series only. An import on a comic series is refused with 409.
- File names come only from `downloader/paths.py` (`chapter_path`, `volume_path`), so normalisation and reconciliation agree.
- Tests never use the user's PDFs, which are copyrighted. Fixtures are generated in `tests/pdf_fixture.py`.
- No colour, size, radius or spacing literal in a component. Tokens come from `frontend/tailwind.config.ts`, and every new class is checked with `grep` over `frontend/dist/`.
- `feat/…`/`fix/…`/`docs/…` microcommits in English with no attribution trailer.

## Review Focus

1. **The same PDF dropped twice in one drop, or a re-drop of an already-imported volume.** The user expects "already exists" rather than a unique-key crash. Task 5 tests it.
2. **A PDF whose bookmarks are nested (a volume entry with chapters under it), or that has no bookmarks at all.** The user expects nested chapters to be read the same way as flat ones, and a bookmarkless file to be reported as unreadable rather than imported as one giant chapter. Task 2 tests it.
3. **Two bookmarks on the same page, or bookmarks out of page order.** The user expects no empty chapter and no chapter with a negative page range. Task 2 tests it.
4. **The staging directory vanishing between preview and Import** (the cache was cleaned or the api restarted). The user expects Import to answer "upload again" (410), not a job that fails later. Task 7 tests it.
5. **A worker killed halfway through an import.** The user expects a retry to finish the job without duplicate rows or orphaned `.part` files, because rows are upserted per entry and files are placed atomically. Task 8 tests it.

---

### Task 1: Dependencies and the PDF fixture builder

**Files:**
- Modify: `backend/pyproject.toml` (dependencies)
- Create: `backend/tests/pdf_fixture.py`
- Test: `backend/tests/test_pdf_fixture.py`

**Interfaces:**
- Produces: `make_pdf(entries: list[Entry], *, nested_under: str | None = None, producer: str = "Microsoft Word") -> bytes`, where `Entry = tuple[str | None, list[str]]`. Each entry is a bookmark title (or `None` for pages with no bookmark) followed by the text of each of its pages. Every page draws its text with Helvetica through a hand-written content stream, so `pypdf` extracts it again. With `nested_under`, every bookmark becomes a child of one top-level bookmark with that title.

- [ ] **Step 1:** Add `"pypdf>=5.1"` and `"python-multipart>=0.0.20"` to `dependencies`, each with a one-line comment giving its reason (licence and purpose). Run `uv pip install -e ".[dev]"`.
- [ ] **Step 2: Write the failing test** `test_fixture_round_trips_titles_and_text`. Build `make_pdf([("Cover", ["x"]), ("Chapter 1 Start", ["one", "two"])])`. Read it with `pypdf.PdfReader(io.BytesIO(data))` and assert there are 3 pages, the outline titles are `["Cover", "Chapter 1 Start"]`, and `"two" in reader.pages[2].extract_text()`.
- [ ] **Step 3:** Run `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_pdf_fixture.py -q`. Expected: FAIL (module missing).
- [ ] **Step 4:** Implement `make_pdf` with `pypdf.PdfWriter`: a blank page plus a `StreamObject` content stream (`BT /F1 12 Tf 72 720 Td (text) Tj ET`) and a `/Font /F1 Helvetica` resource, and `add_outline_item` for each titled entry.
- [ ] **Step 5:** Run the test. Expected: PASS.
- [ ] **Step 6:** Commit: `build: add pypdf and python-multipart, and a PDF fixture builder for tests`.

### Task 2: Reading a PDF into entries

**Files:**
- Create: `backend/app/importer/__init__.py`, `backend/app/importer/pdf.py`
- Test: `backend/tests/test_importer_pdf.py`

**Interfaces:**
- Consumes: `make_pdf` (Task 1).
- Produces:
  - `@dataclass(frozen=True) class PdfEntry: title: str; pages: list[str]; images: list[bytes]`. `pages` holds the extracted text per page, and `images` the image bytes in page order.
  - `@dataclass(frozen=True) class PdfBook: producer: str | None; entries: list[PdfEntry]`
  - `class UnreadablePdf(Exception)`
  - `read_pdf(data: bytes) -> PdfBook`

Rules: bookmarks are flattened depth-first. A bookmark with children that also has its own page contributes only its children. Entries are sorted by page. An entry runs from its page to the page before the next entry's page. Bookmarks that share a page keep only the last one on that page. Pages before the first bookmark are dropped. No bookmarks, or no extractable text on any page, raises `UnreadablePdf`.

- [ ] **Step 1: Write the failing tests:**
  - `test_one_entry_per_bookmark_with_its_page_range`: three entries of 1, 2 and 1 pages, and assert `[len(e.pages) for e in book.entries] == [1, 2, 1]`.
  - `test_nested_bookmarks_read_like_flat_ones`: use `nested_under="Volume 3"`, and the titles are the children only.
  - `test_bookmarks_sharing_a_page_keep_the_last`.
  - `test_bookmarks_out_of_order_are_sorted_by_page`.
  - `test_no_bookmarks_is_unreadable` and `test_no_text_is_unreadable`, both with `pytest.raises(UnreadablePdf)`.
  - `test_producer_is_read`: build with `producer="calibre 3.48.0"` and assert `book.producer.startswith("calibre")`.
- [ ] **Step 2:** Run `pytest tests/test_importer_pdf.py -q`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement `read_pdf` with `pypdf.PdfReader`, `reader.get_destination_page_number`, `page.extract_text()` and `page.images`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(importer): read a PDF's bookmarks into chapter entries`.

### Task 3: Numbering entries and recognising the edition

**Files:**
- Create: `backend/app/importer/numbering.py`
- Test: `backend/tests/test_importer_numbering.py`

**Interfaces:**
- Consumes: `PdfBook`, `PdfEntry` (Task 2).
- Produces:
  - `Edition = Literal["web", "light"]`
  - `@dataclass(frozen=True) class NumberedChapter: number: Decimal; title: str | None; entries: list[PdfEntry]`. `entries` holds the chapter's own entry, preceded by any front matter folded into it.
  - `@dataclass(frozen=True) class ReadVolume: volume: Decimal | None; edition: Edition; chapters: list[NumberedChapter]; cover: bytes | None`
  - `volume_from_filename(name: str) -> Decimal | None`
  - `number_book(book: PdfBook, filename: str, *, known_max: Decimal | None) -> ReadVolume`

Rules, from the spec:
- `Chapter <n> <title>` becomes `n` with the title being the rest.
- `Prologue <k>` becomes `0.k`. An unnumbered `Prologue …` takes the next fraction after the last prologue.
- An unnumbered side entry (`POV Chapter`, `Side Story`, `Interlude`, `Epilogue` with no number) takes the previous number plus `.5`, then `.6` for the next one, and so on.
- `Cover`, `Characters` and `Map` (case-insensitive, prefix match) are front matter. Their entries join the next chapter's `entries`, and the first image of `Cover` becomes `cover`.
- The edition is `light` when the first numbered chapter is 1 and `known_max` is greater than 1, or when `producer` starts with `calibre` and the numbers restart at 1. Otherwise it is `web`.
- The volume number comes from `_NN`, `Volume NN` or `Vol. NN` in the file name.

- [ ] **Step 1: Write the failing tests:**
  - `test_web_volume_one_numbers_prologues_and_pov`: entries `Cover, Characters, Prologue 1, Prologue 2, Prologue 3, Prologue POV, Chapter 1, …, Chapter 9, POV Chapter, Chapter 10`. Assert the numbers are `[0.1, 0.2, 0.3, 0.4, 1, …, 9, 9.5, 10]` and that the first chapter's `entries[0].title == "Cover"`.
  - `test_two_side_entries_after_one_chapter_take_5_then_6`.
  - `test_chapter_title_is_the_text_after_the_number`: `"Chapter 213 Today Kuzunoha leaves"` gives `title == "Today Kuzunoha leaves"`.
  - `test_restart_at_one_after_higher_known_chapters_is_light`: `known_max=Decimal(295)` gives `edition == "light"`.
  - `test_first_volume_starting_at_one_is_web`: `known_max=None` gives `web`.
  - `test_volume_from_filename` with a parametrised table: `"…Douchuu_01.pdf"` → 1, `"…_12_(v2).pdf"` → 12, `"…_15 (Chapter 213-231).pdf"` → 15, `"Tsukimichi Moonlit Fantasy - Volume 19.pdf"` → 19, `"notes.pdf"` → None.
- [ ] **Step 2:** Run `pytest tests/test_importer_numbering.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `number_book` and `volume_from_filename`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(importer): number web novel entries and tell a light novel volume apart`.

### Task 4: Page text to chapter XHTML

**Files:**
- Create: `backend/app/importer/xhtml.py`
- Test: `backend/tests/test_importer_xhtml.py`

**Interfaces:**
- Consumes: `PdfEntry` (Task 2).
- Produces: `entries_to_body(entries: list[PdfEntry]) -> tuple[str, list[bytes]]`. It returns XHTML that `downloader/epub.py`'s `EpubChapter.body` accepts (images referenced as `{{img:N}}`) and the images in that order.

Rules: XML-escape everything. A line on its own made only of digits, or matching `Page N`, is dropped. A line repeated at the top or bottom of most of an entry's pages is a running header or footer and is dropped. Lines join into paragraphs until a blank line or a line ending in sentence punctuation followed by a line starting with an uppercase letter or a quote. Each entry title becomes an `<h2>`.

- [ ] **Step 1: Write the failing tests:**
  - `test_paragraphs_are_joined_across_wrapped_lines`.
  - `test_page_numbers_and_running_headers_are_dropped`.
  - `test_markup_characters_are_escaped`: `"a < b & c"` appears as `a &lt; b &amp; c`.
  - `test_images_are_referenced_in_order`: two images give `{{img:0}}` before `{{img:1}}`.
  - `test_body_is_well_formed`: `xml.etree.ElementTree.fromstring(f"<div>{body}</div>")` does not raise.
- [ ] **Step 2:** Run `pytest tests/test_importer_xhtml.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `entries_to_body`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Run it once by hand on the user's `…Douchuu_01.pdf` and `Volume 19.pdf` with a throwaway script in the scratchpad, never committed. Check that paragraphs read naturally, and adjust the rules if they don't. Record what changed in the commit body.
- [ ] **Step 6:** Commit: `feat(importer): turn PDF page text into chapter XHTML`.

### Task 5: The import plan

**Files:**
- Create: `backend/app/importer/plan.py`
- Test: `backend/tests/test_importer_plan.py`

**Interfaces:**
- Consumes: `ReadVolume`, `NumberedChapter` (Task 3); `chapter_filename` and `volume_filename` from `app/downloader/paths.py`.
- Produces:
  - `@dataclass(frozen=True) class Existing: chapters: frozenset[Decimal]; volumes: frozenset[Decimal]`
  - `@dataclass(frozen=True) class Override: volume: Decimal | None = None; edition: Edition | None = None; replace: bool = False`
  - `@dataclass class PlannedFile: name: str; sha256: str; volume: Decimal | None; edition: Edition; chapters: list[Decimal]; outputs: list[str]; status: Literal["ready", "exists", "conflict", "unreadable", "duplicate"]; reason: str | None`. `outputs` holds the file names it will write.
  - `plan_import(slug: str, files: list[tuple[str, str, ReadVolume | None]], existing: Existing, overrides: dict[str, Override]) -> list[PlannedFile]`. Each file is `(name, sha256, read)`, with `None` for an unreadable file.

Rules: an override's `volume`/`edition` replaces what was read. A web volume's chapters, or a light volume's number, already in `existing` gives `exists` unless `replace`. Two files with the same sha256 or the same volume give `duplicate` for the second. A generated number that collides with a real chapter number in the same file gives `conflict` with the number in `reason`. A file with no volume number gives `conflict` with `reason="no volume number"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_web_volume_lists_its_chapter_files`: the outputs equal `chapter_filename(slug, n, title, kind="prose")` for each chapter.
  - `test_light_volume_is_one_volume_file`: `outputs == [volume_filename(slug, Decimal(19), …)]` and `chapters == []`.
  - `test_existing_chapters_are_exists_unless_replaced`.
  - `test_same_file_twice_is_duplicate` and `test_two_files_claiming_one_volume_is_duplicate`.
  - `test_generated_number_colliding_with_a_real_one_is_conflict`.
  - `test_override_flips_edition_and_volume`.
- [ ] **Step 2:** Run `pytest tests/test_importer_plan.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `plan_import`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(importer): plan an import and flag what already exists`.

### Task 6: Upload and preview route

**Files:**
- Create: `backend/app/api/routes_import.py`, `backend/app/importer/staging.py`
- Modify: `backend/app/api/main.py` (`include_router`)
- Test: `backend/tests/test_import_api.py`

**Interfaces:**
- Consumes: `read_pdf`, `number_book`, `plan_import`, `Existing` (Tasks 2, 3 and 5); `get_settings().reader_cache_path`.
- Produces:
  - `staging.py`: `stage(files: list[tuple[str, bytes]]) -> str`, which returns a token, writes `reader_cache_path / "imports" / token / <sha256>.pdf` plus `manifest.json` (`{sha256: original name}`), and removes import directories older than 24 h. Also `staged(token: str) -> list[tuple[str, str, bytes]] | None`, which returns `(name, sha256, data)`, or `None` when the token is gone. Also `discard(token: str) -> None`.
  - `POST /api/series/{series_id}/import`, multipart field `files` (repeatable). Its answer is `{"token": str, "files": [PlannedFile as JSON]}`. It answers 404 for an unknown series, 409 `"import is for prose series"` for a comic one, 413 when the drop is over 200 MB in total, and 415 for a file that does not start with `%PDF-`.
  - `known_max` for `number_book` is the highest of `max(chapter.number)` for the series and the highest web-edition chapter read earlier in the same drop, with files processed in volume order.

- [ ] **Step 1: Write the failing tests**, in the style of `tests/test_local_tracking.py` (own truncate fixture, `a_series` helper with `kind='prose'`):
  - `test_preview_returns_a_plan_and_writes_nothing`: the answer has `status == "ready"`, and afterwards `select count(*) from chapter` is 0 and `library_path` is untouched.
  - `test_preview_on_a_comic_series_is_409`.
  - `test_non_pdf_is_415`.
  - `test_existing_chapters_show_as_exists`.
- [ ] **Step 2:** Run `pytest tests/test_import_api.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `staging.py` and the route. Parse the PDFs with `asyncio.to_thread` so the event loop keeps serving.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(api): stage dropped PDFs and preview their import`.

### Task 7: Confirm route and job type

**Files:**
- Modify: `backend/app/enums.py` (`JobType.IMPORT_FILES = "import_files"`, added to `_DOWNLOAD_LANE`), `backend/app/api/routes_import.py`
- Test: `backend/tests/test_import_api.py`, `backend/tests/test_lanes.py`

**Interfaces:**
- Consumes: `staged`, `plan_import`, `Override`; `repo.enqueue`.
- Produces: `POST /api/series/{series_id}/import/{token}` with body `{"files": {sha256: {"volume": str | null, "edition": "web" | "light" | null, "replace": bool}}}`. It recomputes the plan with the overrides and enqueues `IMPORT_FILES` with payload `{"series_id": int, "token": str, "overrides": {...}}` and `dedupe_key=f"import_files:{token}"`. It answers 202 `{"job_id": int, "files": [PlannedFile]}`, 410 `"upload again"` when the token is gone, and 409 when no file is `ready` after the overrides.

- [ ] **Step 1: Write the failing tests:**
  - `test_confirm_enqueues_one_import_job_on_the_download_lane`: assert `JobType.IMPORT_FILES in types_for(Lane.DOWNLOAD)`, and that one `job` row has type `import_files`.
  - `test_confirm_after_staging_vanished_is_410`.
  - `test_confirm_with_nothing_ready_is_409`.
- [ ] **Step 2:** Run `pytest tests/test_import_api.py tests/test_lanes.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(api): confirm an import onto the download lane`.

### Task 8: The `import_files` handler

**Files:**
- Create: `backend/app/handlers/import_files.py`
- Modify: `backend/app/worker/main.py` (import the module so it registers), `backend/app/models.py` (rewrite the `Volume` docstring: it is a J-Novel Club volume *or* an imported one)
- Test: `backend/tests/test_import_files_handler.py`

**Interfaces:**
- Consumes: `staged`, `discard`, `plan_import`, `entries_to_body`; `EpubChapter`, `write_epub`; `chapter_path`, `volume_path`; `build_comicinfo` (for author and summary, as `prose_download.write_prose_chapter` does); `JobContext`, `register`, `PermanentError`.
- Produces: `@register(JobType.IMPORT_FILES) async def handle(ctx: JobContext) -> None`.

Behaviour:
- Recompute the plan from staging and act only on `ready` files. A missing token raises `PermanentError("staged files are gone; upload again")`.
- For each web chapter, write `chapter_path(..., kind="prose")` with `identifier=f"soshuhen:{series_id}:{number.normalize()}"`. Then upsert `chapter (series_id, number, title, state='downloaded', file_path, source_url=null)` `on conflict (series_id, number) do update` (only reached through `replace`).
- For each file, upsert `volume (series_id, number, source_volume_id=f"import:{sha256}", status='owned', state='downloaded', first_part, last_part, title)` `on conflict (series_id, number) do update`. `first_part`/`last_part` are the min and max chapter numbers for web volumes and null for light ones. A light volume writes one `EpubChapter` with `number=volume`, the whole book as body and `file_path` on the volume row. Every EPUB of a file carries that file's `ReadVolume.cover`, falling back to `prose_download.cover_for`.
- When replacing, unlink the previous `file_path` only when it sits in the same series folder and reads back as the same number, as in `volume_download._download`.
- Commit after each file. Call `ctx.log(f"imported volume {n}", pct=…)` after each one. Enqueue `KOMGA_SCAN` with `dedupe_key=f"komga_scan:{series_id}"` at the end, then call `discard(token)`.
- Never enqueue any progress job.

- [ ] **Step 1: Write the failing tests**, in the style of `tests/test_download_batch_handler.py` (`JobContext(session=..., job=...)`, `library_path` pointed at `tmp_path` via `get_settings` override):
  - `test_web_volume_writes_one_epub_per_chapter_and_a_volume_row`: files exist under `paths.chapter_path`, the chapter rows are `downloaded` with `file_path` set, and the volume row has `first_part`/`last_part`.
  - `test_light_volume_writes_one_volume_file_and_no_chapters`.
  - `test_import_marks_nothing_read`: `list_entry.user_progress_chapter` is unchanged, and no job of type `progress_push`, `progress_write` or `list_write` exists.
  - `test_import_enqueues_a_komga_scan`.
  - `test_rerun_after_a_crash_is_idempotent`: run the handler, delete the volume row of the second file only, and run it again. The chapter count is unchanged and no `*.part` files remain.
  - `test_replace_keeps_progress_and_removes_only_its_own_old_file`.
  - `test_imported_chapter_is_never_queued_for_download`: running `download_batch`'s row selection for the series returns nothing.
- [ ] **Step 2:** Run `pytest tests/test_import_files_handler.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the whole suite and lint: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q` and `.venv/bin/python -m ruff check app/ tests/`. Expected: all pass, no lint.
- [ ] **Step 5:** Commit: `feat(worker): write imported chapters and volumes from staged PDFs`.

### Task 9: The import area on the series page

**Files:**
- Modify: `frontend/src/lib/api.ts` (types `ImportFile`, `ImportPreview`; functions `previewImport(seriesId: number, files: File[]): Promise<ImportPreview>` and `confirmImport(seriesId: number, token: string, overrides: Record<string, ImportOverride>): Promise<{ job_id: number }>`)
- Create: `frontend/src/features/series/ImportPanel.tsx`
- Modify: `frontend/src/features/series/SeriesDetailPage.tsx` (a fourth `Panel`, `'import'`, shown only when `detail.series.kind === 'prose'`)

**Interfaces:**
- Consumes: the routes from Tasks 6 and 7; `useJobEvents` from `lib/useEvents.ts`; `Button`, `NoticeBar` and `Tabs` from `ui/`.
- Produces: `ImportPanel({ seriesId, onImported }: { seriesId: number; onImported: () => void })`.

Behaviour, matching mockup A:
- A drop zone that also opens a file picker (`accept="application/pdf"`, multiple).
- While uploading, a "Reading files…" state. After that, a table with File, Volume (editable number), Edition (web/light toggle), Read as, and Becomes (first and last output name plus a count). Rows that are `exists` get a Replace checkbox. `conflict`, `unreadable` and `duplicate` rows show their reason and are left out.
- A summary line, "N files · M chapters · K whole volumes", counted from the plan only.
- **Import N files** sends the overrides. Progress comes from `useJobEvents` for the returned `job_id`. When it finishes, `onImported()` reloads the series detail.
- A 410 resets the panel to the drop zone with "Upload again".

- [ ] **Step 1:** Implement the API functions and `ImportPanel`, using only existing tokens.
- [ ] **Step 2:** Run `cd frontend && npm run build`. Expected: `tsc -b` and vite pass.
- [ ] **Step 3:** `grep` `frontend/dist/assets/*.css` for each new class used in `ImportPanel.tsx`. Expected: every class is present.
- [ ] **Step 4:** Rebuild the stack (`docker compose build api && docker compose up -d --force-recreate api worker worker-download web`, then `docker compose ps`). Drop the user's `…Douchuu_01.pdf` and `Volume 19.pdf` on series 308 in the browser, check the review screen, and press Import. Expected: 33 chapters plus 1 volume appear, and Komga shows the series.
- [ ] **Step 5:** Commit: `feat(frontend): import PDFs from a prose series' page`.

### Task 10: Documentation

**Files:**
- Modify: `docs/features.md` (a section next to "Already own some chapters?": importing novel PDFs, web versus light novel, volumes numbered after the light novel), `docs/data-model.md` (`volume` rows also come from imports, `source_volume_id = 'import:<sha256>'`; a chapter can exist with no `source_url`), `docs/architecture.md` (the `import_files` job on the download lane, and why `api` only stages)

- [ ] **Step 1:** Write the three changes.
- [ ] **Step 2:** Commit: `docs: describe importing novel PDFs`.
