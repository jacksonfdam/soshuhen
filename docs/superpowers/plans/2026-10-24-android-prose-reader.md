# Android Prose Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prose series appear in the Android app, their EPUBs (prose chapters and light novel volumes) copy to the device like CBZs, and a native Compose reader renders them offline with the manga reader's four directions, adjustable typography, a stable position, and completions sent through the outbox.

**Architecture:** The server gains two EPUB archive routes. The app generalises its copy, index and part bookkeeping from "chapter" to a `BookRef` (chapter or volume), parses an unpacked EPUB into blocks in `commonMain`, paginates them lazily around a `(section, block, offset)` position through a measuring seam, and renders paged, double and scroll modes in a new prose screen beside the manga reader in `reader/`.

**Tech Stack:** FastAPI + pytest (Postgres); Kotlin Multiplatform, Compose Multiplatform, Room KMP, Ktor, Okio.

**Spec:** `docs/superpowers/specs/2026-10-24-android-prose-reader-design.md`

## Global Constraints

- Comments explain why a line exists, never what it does (`CLAUDE.md`).
- Microcommits, English, no attribution trailer of any kind.
- Do not edit `reader_service.py`, `routes_reader.py`, `routes_series.py` or `frontend/` (web session's). `app/api/main.py` gets a one-line router registration only.
- Nothing in the prose reader may fetch a URL: remote `src`/`href` are dropped when the book is parsed.
- No colour, size or spacing literal outside `ui/theme/Tokens.kt`.
- Backend tests: `cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5436 .venv/bin/python -m pytest tests -q` against `manga-pg-android-reader` (port 5436). Lint: `.venv/bin/python -m ruff check app/ tests/`.
- App tests: `cd mobile && ./gradlew :shared:jvmTest :androidApp:assembleDebug` (what CI runs).
- The user's PDFs/EPUBs are copyrighted: never commit or quote their text. Test fixtures are written in the tests.
- Contract (web session): volume JSON carries `id`, `file_path`, `first_part`, `last_part`, `readable`; `POST /api/reader/volumes/{id}/complete` takes optional `{"read_at"}`, 404 unknown, 409 for a `web` volume. Decode every new field with a default so `main` before their merge still decodes.

## Review Focus

1. **A light volume whose copy is cut off and resumed** must append only onto its own archive: part ETags for volume 7 and chapter 7 must not collide. Test in Task 4.
2. **An EPUB with a remote image or stylesheet** must render without fetching it. Test in Task 6.
3. **Changing font size mid-book** must keep the first visible character on screen. Test in Task 8.
4. **A volume finished away from home** must reach `/api/reader/volumes/{id}/complete` once, in order, and a 409 must be dropped, not retried forever. Test in Task 3.
5. **A prose series with only light volumes and no chapters** (series 308) must import, list and open. Tests in Tasks 5 and 10.

---

### Task 1: Chapter archive serves prose EPUBs

**Files:**
- Modify: `backend/app/api/routes_chapters.py`
- Test: `backend/tests/test_routes_chapters.py` (create if absent; follow the fixtures of the existing archive route test, `grep -rn "archive" backend/tests` first)

**Interfaces:**
- Produces: `GET /api/chapters/{id}/archive` → `application/epub+zip` for a chapter whose series has `kind = 'prose'`; comics unchanged.

- [ ] **Step 1: Start the worktree's Postgres** — `docker run -d --name manga-pg-android-reader -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5436:5432 postgres:17-alpine`; `cd backend && uv venv && uv pip install -e ".[dev]"`.
- [ ] **Step 2: Write failing tests** — `test_prose_chapter_archive_is_served_as_epub` (a prose series' chapter with `file_path` to a file inside `library_path` → 200, `content-type == "application/epub+zip"`, body equals file bytes); `test_prose_chapter_archive_honours_range` (`Range: bytes=2-` → 206); `test_comic_archive_is_still_cbz` (→ `application/vnd.comicbook+zip`); `test_archive_outside_library_is_404`.
- [ ] **Step 3: Run, expect the prose tests to fail with 409.**
- [ ] **Step 4: Implement.** Replace the `service.chapter()` call with a local query `select c.file_path, s.kind from chapter c join series s on s.id = c.series_id where c.id = :id` (404 when no row). Resolve the path with `app.reader.archive.inside(path, get_settings().library_path)` and `is_file()` as `reader_service.archive_of` does. Media type `application/epub+zip` when `kind == "prose"`, else the CBZ type. Keep `await session.close()` before responding and its comment.
- [ ] **Step 5: Run tests and ruff; expect PASS.**
- [ ] **Step 6: Commit** `feat(api): serve prose chapter archives as EPUB`.

### Task 2: Volume archive route

**Files:**
- Create: `backend/app/api/routes_volumes.py`
- Modify: `backend/app/api/main.py` (one `include_router` line)
- Test: `backend/tests/test_routes_volumes.py`

**Interfaces:**
- Produces: `GET /api/volumes/{id}/archive` → `FileResponse(path, media_type="application/epub+zip", filename=path.name)`; 404 for unknown volume, null `file_path`, missing file, or path outside the library.

- [ ] **Step 1: Write failing tests** — `test_volume_archive_serves_the_file` (200, epub type, `etag` header present, bytes equal); `test_volume_archive_resumes_with_range` (206, `content-range` total equals size); `test_volume_without_file_is_404`; `test_volume_file_outside_library_is_404`; `test_unknown_volume_is_404`. Volume rows need `source_volume_id` (NOT NULL, unique per series) and `edition`.
- [ ] **Step 2: Run, expect 404 from the router not existing.**
- [ ] **Step 3: Implement** the router (prefix `/api/volumes`, tag `volumes`) with the same session-close-before-streaming pattern and comment as the chapter route; register it.
- [ ] **Step 4: Run tests and ruff; expect PASS.**
- [ ] **Step 5: Commit** `feat(api): serve a light novel volume's EPUB for the app to copy`.

### Task 3: Models, API client and outbox for volumes

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/app/soshuhen/api/Models.kt`, `api/SoshuhenApi.kt`, `core/Outbox.kt`
- Test: `commonTest/.../api/SoshuhenApiTest.kt`, `commonTest/.../core/OutboxTest.kt`, `api/Fixtures.kt`

**Interfaces:**
- Produces:
  - `@Serializable data class SeriesVolume(val id: Long? = null, val number: Double, val edition: String, val title: String? = null, val state: String? = null, @SerialName("file_path") val filePath: String? = null, @SerialName("first_part") val firstPart: Double? = null, @SerialName("last_part") val lastPart: Double? = null, val readable: Boolean = false)`
  - `@Serializable data class SeriesEntry(val provider: String, @SerialName("user_progress_volume") val userProgressVolume: Int? = null)`
  - `SeriesDetail.volumes: List<SeriesVolume> = emptyList()`, `SeriesDetail.entries: List<SeriesEntry> = emptyList()`
  - `SoshuhenApi.volumeArchive(volumeId: Long, from: Long, ifRange: String? = null, read: suspend (ArchiveDownload) -> T): T` (shares a private body with `archive`)
  - `SoshuhenApi.completeVolume(volumeId: Long, readAt: Instant)`
  - `Outbox.completeVolume(seriesId: Long, volumeId: Long)`, kind `VOLUME_COMPLETE = "volume_complete"`, volume id stored in the `chapter_id` column (no schema change).

- [ ] **Step 1: Failing tests** — `decodesVolumesWithTheWebSessionsFields` (fixture JSON with `id`, `file_path`, `first_part`, `last_part`, `readable`); `decodesVolumesWithoutThem` (main's current shape: no `id`/`file_path` → nulls, `readable == false`); `volumeArchiveRequestsTheVolumeRoute` (MockEngine sees `/api/volumes/7/archive` and `Range: bytes=10-`, `If-Range`); `completeVolumePostsReadAt` (path `/api/reader/volumes/7/complete`, body `{"read_at":"…"}`); in OutboxTest `volumeCompletionIsSentInOrder` (position, complete chapter, complete volume → three calls in that order) and `aRefusedVolumeCompletionIsDropped` (409 → dropped == 1, remaining == 0).
- [ ] **Step 2: Run `./gradlew :shared:jvmTest --tests '*SoshuhenApiTest*' --tests '*OutboxTest*'`, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** in two: `feat(mobile): decode a series' volumes and list entries`, `feat(mobile): copy and complete volumes through the API and outbox`.

### Task 4: Local index for volumes and kind-keyed parts and log

**Files:**
- Create: `core/BookRef.kt`, `db/DeviceVolumeEntity.kt`
- Modify: `db/ImportPartEntity.kt`, `db/ImportLogEntity.kt`, `db/SoshuhenDatabase.kt` (version 3, `AutoMigration(from = 2, to = 3)`), `core/LocalStore.kt`, `core/DeviceLibrary.kt`; regenerate `mobile/shared/schemas/.../3.json` by building.
- Test: `commonTest/.../core/LocalStoreTest.kt`, `DeviceLibraryTest.kt`

**Interfaces:**
- Produces:
  - `enum class BookKind(val key: String) { Chapter("chapter"), Volume("volume") }`; `data class BookRef(val kind: BookKind, val id: Long)`
  - `data class DeviceVolume(val volumeId: Long, val seriesId: Long, val number: Double, val fileName: String, val uri: String, val etag: String?, val size: Long, val importedAt: Instant)`
  - Tables: `device_volume` (PK `volume_id`); `import_part` and `import_log` gain `kind TEXT NOT NULL DEFAULT 'chapter'` and become PK `(kind, chapter_id)`. If Room's auto-migration cannot change the PK, write the `Migration(2, 3)` by hand (create new, copy, drop, rename) and test it with Room's migration test helper.
  - `LocalStore`: `deviceVolumes(seriesId): Flow<List<DeviceVolume>>`, `deviceVolume(volumeId): DeviceVolume?`, `indexVolume(v)`, `forgetVolume(volumeId)`, `markVolumeUnreadable(volumeId)`; `savePartEtag(ref: BookRef, etag)`, `partEtag(ref)`, `forgetPart(ref)` replace the chapter-id versions; `seriesWithChapters()` includes series with volumes; `belongTo` also clears `device_volume`; `raiseVolumeProgress(seriesId, number: Int)` and `volumeProgress(seriesId): Int?` (snapshot key `volumes/$id`, never lowers).
  - `ImportLogEntity(kind: String = "chapter", chapterId, …)`.
  - `DeviceLibrary.deleteVolume(volumeId)`; `unmark(…, deleteFiles = true)` and `deleteRead(detail)` cover volumes (a volume is read when `floor(number) <= max(entries' userProgressVolume, local volumeProgress)`).

- [ ] **Step 1: Failing tests** — `partEtagsOfAChapterAndAVolumeWithTheSameIdAreApart` (save `Chapter 7` "a", `Volume 7` "b"; read both back; forget one, other remains); `volumeIndexRoundTrips`; `volumeProgressNeverLowers`; `switchingServerForgetsVolumes`; `unmarkWithFilesDeletesVolumes`; `deleteReadDeletesReadVolumes`; `logKeepsAChapterAndAVolumeWithTheSameId`.
- [ ] **Step 2: Run, expect FAIL (compile).**
- [ ] **Step 3: Implement; update every caller of the old part/log signatures (`ImportRunner`) mechanically with `BookRef(BookKind.Chapter, id)`.**
- [ ] **Step 4: `./gradlew :shared:jvmTest`, expect PASS; commit the schema JSON with it.**
- [ ] **Step 5: Commit** `feat(mobile): index volumes and key copy parts by kind`.

### Task 5: Import copies prose chapters and light volumes

**Files:**
- Create: `core/EpubCheck.kt` (`fun interface EpubCheck { suspend fun opens(source: Source): Boolean }`)
- Modify: `core/ImportRunner.kt`, `core/AppGraph.kt`, `core/NotificationText.kt`, `core/ImportWorker.kt` (androidMain, notification text), `updates/UpdatesViewModel.kt`/`UpdatesScreen.kt` (show "Volume N")
- Test: `commonTest/.../core/ImportRunnerTest.kt`, `NotificationTextTest.kt`, `Fakes.kt`

**Interfaces:**
- Consumes: Task 3 API, Task 4 store.
- Produces: `ImportRunner(session, store, folder, outbox, check: ArchiveCheck, epubCheck: EpubCheck, clock)`; `ImportReport.importedVolumes: Map<Long, List<Double>>` (default empty); `newVolumesText(title, numbers): Pair<String, String>` ("Tsukimichi: 2 new volumes" shape, matching `newChaptersText`).

`Work` carries a `BookRef`, the series, the number, the file name (from `filePath`), and does its fetch through `api.archive` or `api.volumeArchive` by kind; indexing goes to `indexChapter` or `indexVolume`. The check is `epubCheck.opens` when the name ends `.epub` (case-insensitive), else `check.pageCount > 0`. Prose series are no longer skipped. Volumes queue when `edition == "light" && readable && id != null && filePath != null`; chapters as today. Volumes before chapters within a series is not required; keep "oldest first" by number per kind.

- [ ] **Step 1: Failing tests** — `copiesALightVolumeOfAProseSeries` (series kind prose, one volume, no chapters → `volumeArchive` called, volume indexed, `importedVolumes[series] == [1.0]`); `copiesAProseChapterAndChecksItAsEpub` (epubCheck consulted, not ArchiveCheck); `aVolumeNotReadableOnTheServerIsSkipped`; `aCutOffVolumeResumesOntoItsOwnPart` (part ETag recorded under `Volume`, resume sends `If-Range` with it); `anUnchangedVolumeCostsOneByteProbe`; `newVolumesTextCountsVolumes`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** In `AppGraph` the `epubCheck` comes from the platform like `archiveCheck` (Task 7 provides it; until then pass a fake from tests and wire `EpubFiles` in Task 7).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): copy prose chapters and light novel volumes`, then `feat(mobile): announce imported volumes`.

### Task 6: Reading an EPUB into blocks

**Files:**
- Create: `commonMain/.../reader/Xml.kt` (a small tolerant XML tokenizer), `reader/Epub.kt` (container → OPF → spine → blocks), `reader/ProsePosition.kt`
- Test: `commonTest/.../reader/EpubTest.kt`, `XmlTest.kt` (build fixture EPUB trees in `okio.fakefilesystem.FakeFileSystem`; add `libs.okio.fakefilesystem` to `commonTest` if absent)

**Interfaces:**
- Produces:
  - `enum class Emphasis { Bold, Italic }`; `data class Span(val start: Int, val end: Int, val emphasis: Emphasis)`; `data class Styled(val text: String, val spans: List<Span> = emptyList())`
  - `sealed interface Block { data class Heading(val level: Int, val text: Styled); data class Paragraph(val text: Styled); data class Image(val path: Path); data object Break }` — `Image.path` is inside the unpacked root.
  - `data class Book(val title: String?, val sections: List<List<Block>>)`; `class NotAnEpub(message: String) : Exception(message)`
  - `fun readBook(fs: FileSystem, root: Path): Book`
  - `data class ProsePosition(val section: Int, val block: Int, val offset: Int)` with `Book.length(): Int`, `Book.charsBefore(p: ProsePosition): Int`, `Book.positionAtChar(n: Int): ProsePosition`, `Book.clamp(p): ProsePosition` (Image/Break count as one char so the slider can land on them).

Parsing rules: `h1`–`h6` → Heading; `p`, `div` with direct text, `li`, `blockquote` → Paragraph; `br` → `\n` in the current text; `b`/`strong` → Bold, `i`/`em` → Italic; `img` and SVG `image` (`xlink:href`) → Image when the resolved path exists inside `root`; `hr` → Break; whitespace collapsed as HTML does; `script`, `style`, `head` skipped; named entities `amp lt gt quot apos nbsp mdash ndash hellip lsquo rsquo ldquo rdquo` plus numeric. A `src` with a scheme (`http:`, `https:`, `data:`, `//…`) is dropped. Empty paragraphs are dropped. Spine items missing from the zip are skipped; no spine items left → `NotAnEpub`.

- [ ] **Step 1: Failing tests** — `readsTheSpineInOrder`; `keepsBoldAndItalicAsSpans` (`<p>a <i>b</i> <b>c</b></p>` → text `"a b c"`, spans `[2,3) Italic`, `[4,5) Bold`); `collapsesWhitespaceAndKeepsBr`; `resolvesImagesRelativeToTheXhtml` (`../images/1.jpg` from `OEBPS/text/c.xhtml`); `dropsRemoteImagesAndStylesheets` (`<img src="https://x/y.jpg"/>` → no Image block); `decodesEntities`; `aMissingContainerIsNotAnEpub`; `aSingleSectionWithThousandsOfParagraphsParsesQuickly` (3,000 paragraphs, assert block count; no timing assertion); `positionsRoundTripThroughCharacterCounts`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): read an EPUB's spine into text blocks`.

### Task 7: Unpacking EPUBs into the cache

**Files:**
- Create: `jvmAndroidMain/.../reader/EpubFiles.kt`; `core/BookExtractor.kt` (`fun interface BookExtractor { suspend fun unpack(ref: BookRef, version: String, source: Source): Path }`)
- Modify: `androidApp/.../SoshuhenApplication.kt` (or wherever `AppGraph` is built) to pass `EpubFiles` as `epubCheck` and `books`; `core/AppGraph.kt` gains `val books: BookExtractor`
- Test: `jvmTest/.../reader/EpubFilesTest.kt`

**Interfaces:**
- Produces: `class EpubFiles(cacheDir: Path, fileSystem: FileSystem = FileSystem.SYSTEM) : EpubCheck, BookExtractor`. Unpacks under `cacheDir / "books" / "${ref.kind.key}-${ref.id}"` with the `.done`/`.from` markers, pruning and `NoRoomForPages` mapping exactly as `ZipPages` does (keep 3). `opens(source)` streams the zip once, requires `META-INF/container.xml`, its rootfile, and at least one spine item present, and drains every entry so a cut-off archive fails. Entry names with `..` or a leading `/` are skipped (zip slip).

- [ ] **Step 1: Failing tests** — `unpacksOnceAndReusesTheSameVersion`; `aNewVersionUnpacksAgain`; `opensAcceptsAWholeEpub`; `opensRejectsACutOffEpub` (truncate bytes); `opensRejectsAZipWithoutContainer`; `entriesEscapingTheRootAreSkipped`.
- [ ] **Step 2: Run `./gradlew :shared:jvmTest --tests '*EpubFilesTest*'`, expect FAIL.**
- [ ] **Step 3: Implement and wire.**
- [ ] **Step 4: Run all jvm tests and `:androidApp:assembleDebug`, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): unpack EPUBs into the reader's cache`.

### Task 8: Paginating around a position

**Files:**
- Create: `commonMain/.../reader/Paginator.kt`
- Test: `commonTest/.../reader/PaginatorTest.kt`

**Interfaces:**
- Produces:
  - `data class Line(val start: Int, val end: Int, val height: Int)`; `fun interface BlockMeasure { fun lines(block: Block, width: Int): List<Line> }` (Image/Break → one line with `start = end = 0`; an Image taller than the page is measured at page height by the caller)
  - `data class Page(val start: ProsePosition, val end: ProsePosition)` (end exclusive; `end` of the last page is `ProsePosition(sections.size, 0, 0)`)
  - `class Paginator(book: Book, measure: BlockMeasure, width: Int, height: Int, gap: Int)` with `fun pageFrom(p: ProsePosition): Page`, `fun pageBefore(p: ProsePosition): Page?` (the page that ends exactly at `p`, laid out backwards), `fun isLast(page: Page): Boolean`.
  - A position not on a line start snaps to the start of the line containing it, so a page always starts on a line boundary.

Measured blocks are cached by `(section, block)` for the paginator's width; nothing measures a whole section up front. Each section starts a new page.

- [ ] **Step 1: Failing tests** (fake measure: every paragraph char is one 10-px line of 10 chars) — `aPageHoldsAsManyLinesAsFit`; `aParagraphSplitsAcrossPages`; `pageFromThenPageBeforeReturnsTheSamePage`; `aSectionStartsANewPage`; `aPositionInsideALineSnapsToItsStart`; `resizingKeepsTheFirstCharacterVisible` (position from a 100-px page, new Paginator at 60 px, `pageFrom(pos)` contains pos); `onlyBlocksNearThePositionAreMeasured` (counting measure, open at block 2,500 of 3,000 → fewer than 50 calls).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): paginate prose around a position`.

### Task 9: Prose reader state

**Files:**
- Create: `commonMain/.../reader/ProseReaderViewModel.kt`, `reader/ProseStyle.kt`
- Modify: `core/LocalStore.kt` (prose position, style, mode)
- Test: `commonTest/.../reader/ProseReaderViewModelTest.kt`

**Interfaces:**
- Consumes: Tasks 3, 4, 6, 7.
- Produces:
  - `@Serializable data class ProseStyle(val fontSize: Int = 18, val font: String = "serif", val background: String = "black")`; fonts `serif | sans | app`; backgrounds `black | gray | white | sepia`; sizes 14..28 step 2.
  - `LocalStore`: `prosePosition(ref): ProsePosition?`, `saveProsePosition(ref, p)` (key `prose/${kind}/$id`), `proseStyle(): ProseStyle`, `saveProseStyle(s)` (key `prose-style`), `proseMode(seriesId): String?`, `saveProseMode(seriesId, mode)` (key `prose-mode/$id`; default `paged_ltr`).
  - `data class ProseUi(val seriesId: Long, val ref: BookRef, val title: String, val book: Book, val position: ProsePosition, val mode: String, val style: ProseStyle, val previous: BookRef?, val next: BookRef?, val chromeVisible: Boolean)`; `sealed interface ProseState { Loading; Ready(ui); Unavailable(message) }`
  - `class ProseReaderViewModel(seriesId: Long, ref: BookRef, api: StateFlow<SoshuhenApi?>, atHome: StateFlow<Boolean>, local: LocalStore, folder: ChapterFolder, books: BookExtractor, outbox: Outbox, fs: FileSystem = FileSystem.SYSTEM)` with `moveTo(p: ProsePosition)`, `finish()`, `setMode(m)`, `setStyle(s)`, `toggleChrome()`, `open(ref)`.

Opening: on device → `folder.read(uri)` → `books.unpack(ref, "$etag:$size", source)`; else at home with `readable`/`OnServer` → stream `api.archive`/`api.volumeArchive` into a temp file under the cache, then unpack with version = ETag; else `NOT_ON_DEVICE` / `NOT_DOWNLOADED`. Missing or unreadable device files reuse the manga reader's `FILE_MISSING`/`FILE_UNREADABLE` handling (forget / mark unreadable for the right kind). Position save is debounced 1 s like `queuePosition`. `finish()` once per open: chapter → `outbox.complete` + `raiseProgress(floor(number))`; volume → `outbox.completeVolume` + `raiseVolumeProgress(floor(number))`; then `sendIfHome`. `previous`/`next` follow the same edition's readable items by number.

- [ ] **Step 1: Failing tests** — `opensAVolumeFromTheDeviceAtItsSavedPosition`; `opensAServerVolumeAtHomeWithoutWritingTheFolder` (fake folder sees no write); `awayFromHomeAServerVolumeIsUnavailable`; `finishingAVolumeQueuesOneVolumeCompletion` (finish twice → one outbox row, kind `volume_complete`); `finishingAChapterQueuesAChapterCompletion`; `positionIsSavedAfterTheDebounce`; `styleIsGlobalAndModeIsPerSeries`; `aCorruptDeviceVolumeIsMarkedUnreadable`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): open, place and finish prose books`.

### Task 10: Series screen for prose

**Files:**
- Create: `commonMain/.../detail/ProseRows.kt`
- Modify: `detail/SeriesDetailViewModel.kt`, `detail/SeriesDetailScreen.kt`, `detail/DetailRules.kt`
- Test: `commonTest/.../detail/ProseRowsTest.kt`, `SeriesDetailViewModelTest.kt`

**Interfaces:**
- Produces:
  - `data class VolumeRow(val id: Long, val number: Double, val title: String?, val read: Boolean, val availability: Availability)`
  - `data class WebGroup(val volume: Double?, val rows: List<ChapterRow>)` (`volume == null` is "Other chapters")
  - `data class ProseRows(val editions: List<String>, val light: List<VolumeRow>, val web: List<WebGroup>)`
  - `fun proseRows(detail: SeriesDetail, onDeviceChapters: Set<Long>, onDeviceVolumes: Set<Long>, volumeProgress: Int?): ProseRows`
  - `fun defaultEdition(rows: ProseRows): String` ("light" unless only web exists)
  - `DetailUi.prose: ProseRows?` (null for comics), `DetailUi.continueVolume: VolumeRow?`; `SeriesDetailViewModel.deleteVolume(id)`, `edition: StateFlow<String>`, `setEdition(e)`.

Volume availability: on device if indexed; `OnServer` if `readable && id != null`; else `NotDownloaded`. Volume read: `floor(number) <= max(entries' userProgressVolume ?: 0, volumeProgress ?: 0)`. Web groups use `first_part..last_part`; a web volume without a range contributes no group. A volume with `id == null` (server before the web session's merge) is listed but not openable. The screen shows a two-segment switch only when `editions.size == 2`; tapping a row navigates to the prose route (Task 11). Continue for prose opens the first unread readable item of the shown edition.

- [ ] **Step 1: Failing tests** — `series308ListsTwentyLightVolumes` (fixture: 20 light volumes, no chapters → `editions == ["light"]`, 20 rows ascending); `webChaptersGroupUnderTheirVolumeRange`; `chaptersOutsideEveryRangeGoUnderOther`; `aVolumeIsReadByTheListsOrTheDevicesProgress`; `bothEditionsOfferTheSwitch`; `continueOpensTheFirstUnreadVolume`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement rules, then view model, then screen.** Volume rows reuse the chapter row's availability badge and delete action.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): list a novel's volumes and web chapters by edition`.

### Task 11: Prose reader screen and route

**Files:**
- Create: `commonMain/.../reader/ProseReaderScreen.kt`, `reader/ProseSettings.kt` (settings sheet), `reader/ComposeMeasure.kt` (`BlockMeasure` over `TextMeasurer`)
- Modify: `MainShell.kt` (new `@Serializable data class ProseRoute(val seriesId: Long, val kind: String, val id: Long, val title: String)` + `composable<ProseRoute>`), `ui/theme/Tokens.kt` (prose tokens: margins, line height multiplier, paragraph gap, sepia background and its text colour)
- Test: manual on device (Task 13); `ComposeMeasure` is exercised through the app.

Rendering per mode: `paged_ltr`/`paged_rtl` → one `Paginator` page at a time inside a `Box` with `TapZones` (forward edge follows the mode) and horizontal swipe; `double` → two consecutive pages side by side, offered only when the manga reader offers double (`wide`); `long_strip` → `LazyColumn` of blocks, position from `firstVisibleItemIndex` and offset mapped to the line's start char, finish when the last item is fully visible. Text uses the style's font (`FontFamily.Serif`, `FontFamily.SansSerif`, the app's Plus Jakarta family), size in sp, Bold/Italic spans as `SpanStyle`. Images via Coil from the file path, fitted to width (and page height when paged). Chrome reuses `ReaderChrome` pieces: top bar with title, bottom bar with a percentage slider (`charsBefore/length`), previous/next item, settings button opening `ProseSettings` (direction, font, size −/+, background). Volume keys through `ReaderKeys` with the existing invert/off switches. Chrome toggles with a middle tap.

- [ ] **Step 1: Implement `ComposeMeasure` (`rememberTextMeasurer`, measured width in px, `TextLayoutResult.getLineStart/End/Bottom`).**
- [ ] **Step 2: Implement the screen, settings sheet and route; wire Task 10's row taps and Continue.**
- [ ] **Step 3: `./gradlew :shared:jvmTest :androidApp:assembleDebug`, expect PASS.**
- [ ] **Step 4: `grep -rnE '#[0-9a-fA-F]{6}|[0-9]+\.dp|[0-9]+\.sp' mobile/shared/src/commonMain/kotlin/app/soshuhen/reader/Prose*.kt` returns nothing.**
- [ ] **Step 5: Commit** `feat(mobile): read prose in four directions with adjustable type`.

### Task 12: Library shows novels

**Files:**
- Modify: `library/LibraryRules.kt` (remove `comics()`, `visible` filters all), `library/LibraryScreen.kt` (a "Novel" label on prose covers; no "Needs a source mapping" for `state == "local"`), `detail/SeriesDetailScreen.kt` (same `local` rule)
- Test: `commonTest/.../library/LibraryRulesTest.kt`

- [ ] **Step 1: Failing tests** — `proseSeriesAreVisible` (replace the old exclusion test); `aLocalSeriesDoesNotAskForAMapping` (whatever function decides that label returns false for `"local"`; extract it into `LibraryRules` if it is inline in the screen).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(mobile): show novels in the library`.

### Task 13: Docs, device check, PR

**Files:**
- Modify: `docs/superpowers/specs/2026-10-20-android-client-design.md` (the "No prose" non-goal now points to the new design), `docs/features.md` (app reads novels), `mobile/README.md` if it lists what the app reads.

- [ ] **Step 1: Update docs; commit** `docs: the Android app reads novels`.
- [ ] **Step 2: Rebase on `main` after the web session's PR lands; rerun backend and app tests.**
- [ ] **Step 3: Ask the user before rebuilding their live stack** (`docker compose build api && docker compose up -d --force-recreate api worker worker-download`, then `docker compose ps`).
- [ ] **Step 4: On the phone** (`./gradlew :androidApp:installRelease` or debug over ADB): series 308 shows; mark it; a volume copies; airplane mode; it opens and reads; switch all four directions, font, size, background, rotate — place kept; finish it; back home the outbox drains and the server logs `POST /api/reader/volumes/{id}/complete` 200.
- [ ] **Step 5: Push as `jacksonfdam`, open the PR (body checked with `sh .github/attribution-check.sh <file> body`), wait for every check green, merge with `--merge`.**
