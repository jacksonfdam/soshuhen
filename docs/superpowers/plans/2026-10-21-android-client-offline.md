# Android Client, Part 3: Offline Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user marks series in the app, their downloaded chapters are copied to a folder the
user picked and kept current in the background at home, and they are read offline in a reader with
the web's four modes and volume keys, while progress made away from home reaches the server on
return.

**Architecture:** A Room (Kotlin Multiplatform) database in `shared` holds the offline snapshot, the marked series,
the index of chapters on the device, the outgoing progress queue and the import log. All rules
(what to import, what to send, how pages are ordered and grouped) live in `commonMain` behind small
interfaces and are tested on the JVM. Android supplies the folder (Storage Access Framework), zip
reading, WorkManager, notifications, the setup steps and the volume keys.

**Tech Stack:** As part 2, plus Room 2.8.5 (`androidx.room`, KMP) with `androidx.sqlite:sqlite-bundled`
2.7.1 and KSP 2.3.12, WorkManager 2.12.0, `androidx.documentfile` 1.1.0.

**Spec:** `docs/superpowers/specs/2026-10-20-android-client-design.md`. Parts 1 and 2:
`docs/superpowers/plans/2026-10-21-android-client-server.md`,
`docs/superpowers/plans/2026-10-21-android-client-foundation.md` (both done on this branch).

## Global Constraints

- Everything from part 2's Global Constraints still holds: JDK 21, `./gradlew :shared:jvmTest :androidApp:assembleDebug` before every commit, `Tokens.kt` the only home of colours and sizes, feature packages never import each other, only comics, only the Soshuhen server is ever contacted.
- **The app never deletes anything the user did not ask to delete.** Unmarking keeps the files by default; nothing prunes, expires or cleans the folder.
- **Only chapters whose server `state == "downloaded"` and `file_path != null` are importable or readable from the server.** A chapter that is not would make the server stream it from its source, which the app must never cause.
- Database: Room 2.8.5 for Kotlin Multiplatform with the bundled SQLite driver (**decided by the user: Room, because it is multiplatform too**). KSP runs for both targets (`kspAndroid`, `kspJvm`); the database class is `@ConstructedBy(SoshuhenDatabaseConstructor::class)` with the `expect object` Room requires outside Android. Schemas exported to `mobile/shared/schemas` by the `androidx.room` Gradle plugin and committed. Database file `soshuhen.db` in the app's private storage, never in the picked folder.
- **The layout is as close to the web as the platform allows (decided by the user).** Every screen mirrors its web counterpart in structure, order, labels, wording, colours and what each element shows: Library ← `frontend/src/features/library/` (`LibraryPage`, `CoverCard`, `ContinueReading`, `StatusTabs`); Series ← `features/series/SeriesDetailPage.tsx`, `ChapterTable.tsx`, `ProgressManager.tsx`; Reader ← `features/reader/` (`ReaderPage`, `PagedView`, `StripView`, `TabletChrome`, `ReaderSheet`, `SettingsPanel`, `PageSlider`, `EndOfChapter`, `ResumePage`); Settings ← `features/settings/SettingsPage.tsx` for the sections the app has. Before writing a screen, read its web files; where the phone needs something the web does not have (the folder, "On device", volume keys), it uses the same components and tokens as its neighbours. Deviations go in the ledger as rulings with the reason.
- Folder layout, exactly as the spec: `<picked folder>/Soshuhen/<series slug>/<the server's file name>.cbz`, the file name being the last segment of `chapter.file_path`.
- Page order and filtering are the server's (`backend/app/reader/archive.py`): skip directory entries, anything under `__MACOSX/`, any name whose last segment starts with `.`; keep names ending (case-insensitively) in `.jpg .jpeg .png .gif .webp .avif`; sort by natural order (digit runs compared as integers, the rest lower-cased).
- Double-page grouping is the web's (`frontend/src/features/reader/lib/spreads.ts`): page 0 alone, then pairs `[1,2] [3,4] …`, a trailing single page alone.
- Times sent to the server are UTC ISO-8601 with offset (`Instant.toString()`), as `read_at`.
- The worker runs only when the app is "at home" (part 2's `Session` located the saved `instance_id`). No request is made on mobile data except the one identity probe that finds out.
- Notification channels: `new_chapters` ("New chapters", default importance), `import_progress` ("Copying chapters", low importance). No other notification.

## Review Focus

1. **The SD card is removed, or the folder's permission is revoked, between two runs**: the next import stops with the banner "SD card or folder not available: pick the folder again in Settings", writes nothing elsewhere, and reading a chapter whose file is gone says so instead of crashing. Test in Task 4 (runner) and Task 7 (reader source).
2. **An import interrupted half-way** (Wi-Fi drops mid-file, Android stops the worker): no truncated `.cbz` is ever indexed; the next run resumes the `.part` file with `Range` and indexes it only after it opens as a zip with at least one page. Test in Task 4.
3. **Offline reading replayed out of order with web reading in between**: positions carry `read_at`, completions are sent oldest first, and a 4xx such as 404 for a chapter deleted on the server drops that one event without blocking the rest of the queue. Test in Task 3.
4. **A CBZ with odd contents** (`__MACOSX/._001.jpg`, `ComicInfo.xml`, `Page 10.jpg` vs `Page 2.jpg`, upper-case `.JPG`, nested folders): the app's page *n* is the server's page *n*, so a position means the same thing on both. Test in Task 6.
5. **The device is full**: the import stops at the first `ENOSPC`, removes its `.part`, shows the banner "Device full: free some space or delete read chapters", and does not retry chapter after chapter. Test in Task 4.

---

### Task 1: Local database and the offline library

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/db/` (`SoshuhenDatabase.kt`, one `@Entity` and one `@Dao` file per table below, `SoshuhenDatabaseConstructor` expect object)
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/LocalStore.kt`, `mobile/shared/src/androidMain/kotlin/app/soshuhen/db/DatabaseBuilder.android.kt`, `mobile/shared/src/jvmMain/kotlin/app/soshuhen/db/DatabaseBuilder.jvm.kt`
- Modify: `mobile/gradle/libs.versions.toml`, `mobile/shared/build.gradle.kts`, `.../core/AppGraph.kt`, `.../core/Session.kt`, `.../library/LibraryViewModel.kt`, `.../detail/SeriesDetailViewModel.kt`, `.../ui/LoadState.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/core/LocalStoreTest.kt`, extend `LibraryViewModelTest.kt`, `SeriesDetailViewModelTest.kt`, `SessionTest.kt`

**Interfaces:**
- Produces:
  - Room entities (table names as below, column names snake_case via `@ColumnInfo`):
    - `snapshot(key TEXT PRIMARY KEY, json TEXT NOT NULL, fetched_at INTEGER NOT NULL)`: `"series"` holds the `GET /api/series` body; `"series/<id>"` holds a `GET /api/series/{id}` body; `"prefs/<id>"` holds a series' reader prefs.
    - `marked(series_id INTEGER PRIMARY KEY, slug TEXT NOT NULL, marked_at INTEGER NOT NULL)`
    - `device_chapter(chapter_id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL, number REAL NOT NULL, file_name TEXT NOT NULL, uri TEXT NOT NULL, etag TEXT, size INTEGER NOT NULL, imported_at INTEGER NOT NULL)`
    - `outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, series_id INTEGER NOT NULL, chapter_id INTEGER, page INTEGER, read_at TEXT, body TEXT)`: kind is `position`, `complete` or `prefs`.
    - `import_log(chapter_id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL, series_title TEXT NOT NULL, number REAL NOT NULL, imported_at INTEGER NOT NULL)`: what the Updates tab lists.
    - `problem(id INTEGER PRIMARY KEY CHECK (id = 1), message TEXT NOT NULL, at INTEGER NOT NULL)`: the one current import problem, shown as a banner.
  - `fun databaseBuilder(context): RoomDatabase.Builder<SoshuhenDatabase>` on Android (`Room.databaseBuilder(context, "soshuhen.db")`); tests use `Room.inMemoryDatabaseBuilder<SoshuhenDatabase>()` on the JVM. Both `.setDriver(BundledSQLiteDriver()).setQueryCoroutineContext(Dispatchers.IO)`.
  - `class LocalStore(db: SoshuhenDatabase, clock: () -> Instant = { Clock.System.now() })` with:
    - `suspend fun saveSeries(json: String)`, `fun seriesSnapshot(): List<Series>?`
    - `suspend fun saveDetail(id: Long, json: String)`, `fun detailSnapshot(id: Long): SeriesDetail?`
    - `fun isMarked(seriesId: Long): Flow<Boolean>`, `fun markedIds(): Flow<Set<Long>>`, `suspend fun mark(seriesId: Long, slug: String)`, `suspend fun unmark(seriesId: Long)`
    - `fun deviceChapters(seriesId: Long): Flow<List<DeviceChapter>>`, `fun allDeviceChapterIds(): Flow<Set<Long>>`, `suspend fun indexChapter(c: DeviceChapter)`, `suspend fun forgetChapter(chapterId: Long)`
    - `fun problem(): Flow<String?>`, `suspend fun setProblem(message: String?)`
    - `data class DeviceChapter(chapterId: Long, seriesId: Long, number: Double, fileName: String, uri: String, etag: String?, size: Long, importedAt: Instant)`
  - `SoshuhenApi` gains `suspend fun seriesJson(): String` and `suspend fun seriesDetailJson(id: Long): String` (the raw bodies, so the snapshot stores exactly what the server said; `series()` and `seriesDetail()` decode those).
  - `Session` gains `val atHome: StateFlow<Boolean>`: true after `refreshLocation()` confirmed the `instance_id`, false after it could not. `refreshLocation()` now also runs every time the device's network changes (`NetworkInfo.changes: Flow<Unit>`, Android: `ConnectivityManager.registerDefaultNetworkCallback`) instead of on every composition, which also closes part 2's deferred minor about rescanning on rotation.
  - `const val OFFLINE = "Offline. Showing the last sync."` in `LoadState.kt`.
  - Covers must render offline. In `App.kt`, Coil's `ImageLoader` gets an explicit disk cache (`diskCache { DiskCache.Builder().directory(<platform cache dir>/covers).maxSizeBytes(256 MB).build() }`), and the Ktor fetcher ignores cache headers: the server sends `max-age=86400`, and without this Coil would revalidate the cover after a day, fail offline and show initials. The cost is that a changed cover only appears after the app's cache is cleared. **(Builder's call.)** The platform cache dir reaches common code through `AppGraph`.
  - Library and detail view models take a `LocalStore`: a successful load saves the snapshot; a failure with a snapshot present gives `Loaded(snapshot, refreshFailed = OFFLINE)` instead of `Failed`.

- [ ] **Step 1: Add Room to the build.** Catalogue: `room = "2.8.5"`, `sqlite = "2.7.1"`, `ksp = "2.3.12"`; libraries `room-runtime`, `room-compiler`, `sqlite-bundled`; plugins `com.google.devtools.ksp`, `androidx.room`. In `shared`: apply both plugins, `room { schemaDirectory("$projectDir/schemas") }`, `commonMain` depends on `room-runtime` and `sqlite-bundled`, and `dependencies { add("kspAndroid", libs.room.compiler); add("kspJvm", libs.room.compiler) }`. If KSP with the AGP 9 KMP library plugin needs a different configuration name, use the one Gradle lists and ledger it.

- [ ] **Step 2: Write the failing tests**

```kotlin
// LocalStoreTest (Room in-memory database on the JVM, bundled driver)
@Test fun aSavedLibraryReadsBack() = runTest { store.saveSeries(Fixtures.SERIES); assertEquals(2, store.seriesSnapshot()!!.size) }
@Test fun noSnapshotIsNull() = assertNull(store.seriesSnapshot())
@Test fun markingIsRemembered() = runTest { store.mark(7, "s"); assertTrue(store.isMarked(7).first()); store.unmark(7); assertFalse(store.isMarked(7).first()) }
@Test fun unmarkingKeepsTheIndexedChapters() = runTest { store.mark(7, "s"); store.indexChapter(chapter(70, series = 7)); store.unmark(7); assertEquals(1, store.deviceChapters(7).first().size) }
@Test fun theProblemIsOneRow() = runTest { store.setProblem("a"); store.setProblem("b"); assertEquals("b", store.problem().first()); store.setProblem(null); assertNull(store.problem().first()) }

// LibraryViewModelTest
@Test fun offlineWithASnapshotShowsTheSnapshot() = runTest { /* store has the fixture; api fails -> Loaded(rows, refreshFailed = OFFLINE) */ }
@Test fun offlineWithoutASnapshotIsFailed() = runTest { ... }
@Test fun aSuccessfulLoadSavesTheSnapshot() = runTest { ... }

// SeriesDetailViewModelTest
@Test fun detailOfflineShowsTheSnapshot() = runTest { ... }

// SessionTest
@Test fun atHomeIsTrueOnlyWhenTheInstanceAnswers() = runTest { ... }
@Test fun aNetworkChangeRelocates() = runTest { /* FakeNetworkInfo.changes emits; locator called again */ }
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest`
Expected: FAIL, unresolved `LocalStore`, `atHome`, `OFFLINE`.

- [ ] **Step 4: Implement the entities, DAOs, database, `LocalStore`, the builders, the API raw-body methods, `Session.atHome` and network-change relocation, and the view-model fallback.** `App.kt` drops its `LaunchedEffect { refreshLocation() }`; `Session` starts relocation itself in its scope.

- [ ] **Step 5: Run the tests and the build**

Run: `./gradlew :shared:jvmTest :androidApp:assembleDebug`
Expected: PASS, `BUILD SUCCESSFUL`.

- [ ] **Step 6: Commit**

```bash
git add mobile
git commit -m "feat(mobile): keep the last library on the device for reading away from home"
```

### Task 2: The folder, marking, and what is on the device

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/ChapterFolder.kt` (interface), `mobile/shared/src/androidMain/kotlin/app/soshuhen/core/SafChapterFolder.kt`, `mobile/shared/src/commonTest/kotlin/app/soshuhen/core/FakeChapterFolder.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/DeviceLibrary.kt`
- Modify: `.../detail/DetailRules.kt`, `.../detail/SeriesDetailViewModel.kt`, `.../detail/SeriesDetailScreen.kt`, `.../library/LibraryRules.kt`, `.../library/LibraryViewModel.kt`, `.../library/LibraryScreen.kt`, `.../core/ServerStore.kt` (folder URI), `DataStoreServerStore.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/core/DeviceLibraryTest.kt`, extend `DetailRulesTest.kt`, `LibraryRulesTest.kt`

**Interfaces:**
- Consumes: `LocalStore` (Task 1).
- Produces:
  - `interface ChapterFolder` (all suspend, all may throw `FolderUnavailable`):
    - `fun isAvailable(): Boolean`: the tree URI still has its permission and exists.
    - `suspend fun write(slug: String, fileName: String, append: Boolean, block: suspend (Sink) -> Unit)`: writes `<slug>/<fileName>`, creating `Soshuhen/<slug>/` as needed.
    - `suspend fun size(slug: String, fileName: String): Long?`, `suspend fun rename(slug: String, from: String, to: String): String` (returns the new URI), `suspend fun delete(uri: String)`, `suspend fun exists(uri: String): Boolean`, `suspend fun read(uri: String): Source`.
    - `class FolderUnavailable : Exception`, `class DeviceFull : Exception` (Android maps `ENOSPC` / `IOException("No space left on device")` to it).
  - `ServerStore` gains `val folder: Flow<String?>` and `suspend fun saveFolder(uri: String)`.
  - `class DeviceLibrary(store: LocalStore, folder: ChapterFolder)` with `suspend fun mark(series: Series)`, `suspend fun unmark(seriesId: Long, deleteFiles: Boolean)`, `suspend fun deleteChapter(chapterId: Long)`, `suspend fun deleteRead(detail: SeriesDetail)`: deletes only chapters on the device whose `floor(number) <= progress`.
  - `Availability` gains `OnDevice`; `chapterRows(detail, onDevice: Set<Long>)` sets it for indexed chapters (it wins over `OnServer`).
  - `LibraryRules`: `const val ON_DEVICE = "on_device"`, offered as a status chip after the five statuses, filtering to marked series. `visible(all, status, query, marked: Set<Long>)`.
  - Library away from home (`atHome == false`): an unmarked series is drawn dimmed, and tapping it shows "Not on this device. Mark it at home to read it here." instead of opening.
  - Detail: a "Keep on this device" switch (mark/unmark). Unmarking with chapters on the device asks "Delete the N chapters on this device too?" with **Keep them** as the default button and **Delete** as the other. Each device chapter row has a delete action; the header has "Delete read chapters". Rows show "on device" in `Tokens.secondary`.

- [ ] **Step 1: Write the failing tests**

```kotlin
// DeviceLibraryTest with FakeChapterFolder (in-memory map of uri -> bytes)
@Test fun unmarkKeepsFilesByDefault() = runTest { /* mark, index 2, unmark(deleteFiles=false) -> folder still has 2, index still has 2 */ }
@Test fun unmarkWithDeleteRemovesFilesAndIndex() = runTest { ... }
@Test fun deleteReadKeepsUnread() = runTest { /* progress 2; device has 1, 2.5, 3 -> 3 remains */ }
@Test fun aFileAlreadyGoneIsStillForgotten() = runTest { /* folder.delete throws not-found -> index row removed anyway */ }

// DetailRulesTest
@Test fun indexedChapterIsOnDevice() { assertEquals(Availability.OnDevice, chapterRows(detail(0), onDevice = setOf(25)).single { it.id == 25L }.availability) }

// LibraryRulesTest
@Test fun onDeviceTabShowsOnlyMarked() { assertEquals(listOf(2L), visible(listOf(series(1), series(2)), ON_DEVICE, "", marked = setOf(2)).map { it.id }) }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement `DeviceLibrary`, the rules and the screen changes; then `SafChapterFolder`** on `DocumentFile.fromTreeUri`, `contentResolver.openOutputStream(uri, if (append) "wa" else "w")`, `openInputStream`, `DocumentsContract.renameDocument`, `DocumentFile.delete()`, with `isAvailable()` checking `contentResolver.persistedUriPermissions` holds the tree with read and write.

- [ ] **Step 4: Run the tests and the build**

Run: `./gradlew :shared:jvmTest :androidApp:assembleDebug`
Expected: PASS, `BUILD SUCCESSFUL`.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): mark a series to keep it on the device, and delete only on request"
```

### Task 3: Progress API and the outbox

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/Outbox.kt`, `.../api/ReaderModels.kt`
- Modify: `.../api/SoshuhenApi.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/core/OutboxTest.kt`, extend `SoshuhenApiTest.kt`

**Interfaces:**
- Consumes: `LocalStore` (`outbox` table).
- Produces:
  - `@Serializable data class ReaderPrefs(mode: String, scale: String, background: String, custom: Boolean = false)`. Values as the server's `PrefsIn`: mode `paged_ltr | paged_rtl | long_strip | double`, scale `fit_width | fit_height | fit_screen`, background `black | gray | white`.
  - `@Serializable data class Manifest(@SerialName("page_count") pageCount: Int, previous: ChapterRef? = null, next: ChapterRef? = null, position: Int? = null)` and `ChapterRef(id: Long, number: Double)`.
  - `SoshuhenApi` gains: `suspend fun putPosition(seriesId: Long, chapterId: Long, page: Int, readAt: Instant)` (PUT `/api/reader/series/{id}/position` with `read_at`), `suspend fun complete(chapterId: Long, readAt: Instant)` (POST `/api/reader/chapters/{id}/complete` with `{"read_at": …}`), `suspend fun prefs(seriesId: Long): ReaderPrefs`, `suspend fun putPrefs(seriesId: Long, prefs: ReaderPrefs)`, `suspend fun manifest(chapterId: Long): Manifest`, `fun pageUrl(chapterId: Long, index: Int): String`, and `suspend fun <T> archive(chapterId: Long, from: Long, read: suspend (ArchiveDownload) -> T): T` with `data class ArchiveDownload(val body: ByteReadChannel, val etag: String?, val total: Long?, val restarted: Boolean)`. It sends GET `/api/chapters/{id}/archive`, with `Range: bytes=<from>-` when `from > 0`. A 200 answer to a ranged request sets `restarted = true`, which tells the caller to start the file over.
  - `class Outbox(store: LocalStore, clock: () -> Instant)` with `suspend fun position(seriesId: Long, chapterId: Long, page: Int)` (replaces any queued position for that series: only the latest matters), `suspend fun complete(seriesId: Long, chapterId: Long)` (appends), `suspend fun prefs(seriesId: Long, prefs: ReaderPrefs)` (replaces any queued prefs for that series), `suspend fun drain(api: SoshuhenApi): DrainResult` and `data class DrainResult(sent: Int, dropped: Int, remaining: Int)`.
  - Drain order: by `id`, oldest first. An `ApiException` with status 400–499 other than 408 and 429 drops the event and counts it in `dropped`. Any other failure (5xx, timeout, no route) stops the drain, keeping that event and everything after it.

- [ ] **Step 1: Write the failing tests** (MockEngine on the test dispatcher, recording requests):

```kotlin
@Test fun positionsCoalescePerSeries() = runTest { outbox.position(1, 10, 3); outbox.position(1, 11, 5); outbox.position(2, 20, 1); /* drain -> two PUTs, series 1 says chapter 11 page 5 */ }
@Test fun completionsAreSentOldestFirstWithTheirReadAt() = runTest { /* complete 10 at t1, complete 11 at t2 -> POST bodies in that order with read_at t1, t2 */ }
@Test fun a404DropsThatEventAndContinues() = runTest { /* first POST 404, second 200 -> DrainResult(sent=1, dropped=1, remaining=0) */ }
@Test fun aServerErrorStopsAndKeepsTheRest() = runTest { /* first 500 -> sent 0, remaining 2 */ }
@Test fun aTimeoutStopsAndKeepsTheRest() = runTest { ... }
@Test fun readAtIsUtcIso() { /* body contains "read_at":"2026-10-21T08:10:00Z" */ }

// SoshuhenApiTest
@Test fun archiveAsksForTheRemainder() = runTest { /* from=100 -> request header Range: bytes=100- ; 206 -> restarted false */ }
@Test fun archiveA200ToARangeMeansStartOver() = runTest { /* from=100, server answers 200 -> restarted true */ }
@Test fun prefsParse() = runTest { ... }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement `ReaderModels`, the API methods and `Outbox`.** `archive` uses `client.prepareGet(...).execute { }`, so the body streams instead of buffering a 30 MB chapter in memory. That is why the channel is only valid inside `read`.

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): queue reading progress and send it home in order"
```

### Task 4: The import runner

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/ImportRunner.kt`, `.../core/ArchiveCheck.kt` (interface)
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/core/ImportRunnerTest.kt`

**Interfaces:**
- Consumes: `Session`, `LocalStore`, `ChapterFolder`, `Outbox`, `SoshuhenApi.archive`, `seriesJson`, `seriesDetailJson`.
- Produces:
  - `fun interface ArchiveCheck { suspend fun pageCount(source: Source): Int }`: Android implementation in Task 6 reads the zip with the page rules; a CBZ with 0 pages fails the check.
  - `data class ImportReport(val imported: Map<Long, List<Double>>, val seriesTitles: Map<Long, String>, val pending: Int, val problem: String?)`: chapters copied this run per series, how many importable chapters are still missing, and the problem if the run stopped on one.
  - `class ImportRunner(session, store, folder, outbox, check: ArchiveCheck, clock)` with `suspend fun run(budget: Duration = 45.minutes, onProgress: (done: Int, total: Int) -> Unit = { _, _ -> }): ImportReport`. Steps, in order:
    1. `session.refreshLocation()`; not `atHome` → `ImportReport(emptyMap(), emptyMap(), pending = 0, problem = null)`, nothing else.
    2. `outbox.drain(api)`.
    3. Save the series snapshot; for every marked series save its detail snapshot.
    4. For each marked series, each chapter importable (state `downloaded`, `file_path` set) and either not indexed or indexed with a different `etag` than the server's: download to `<file>.part` (appending from its current size when it exists), run `check` on it, rename to `<file>`, `indexChapter`, add an `import_log` row. Oldest chapter numbers first, so a series is readable from its start while the rest copies.
    5. Stop starting new chapters when `budget` is spent (the next periodic run continues). The default 45 minutes keeps each run well inside Android 15's six-hour daily `dataSync` limit even if the user marks a large backlog.
  - Problems, each stopping the run and set with `store.setProblem` (cleared by a run that finishes without one):
    - `FolderUnavailable` → "SD card or folder not available: pick the folder again in Settings"
    - `DeviceFull` → "Device full: free some space or delete read chapters" (the `.part` is deleted)
    - an archive that fails `check` → that chapter's `.part` is deleted and the run continues with the next; after 3 such failures in one run → "Some chapters on the server could not be read; they will be tried again later"
    - an `ApiException` or network failure mid-run → "Lost the server while copying; will continue next time" (the `.part` is kept for resuming)

- [ ] **Step 1: Write the failing tests** (FakeChapterFolder, fake `ArchiveCheck`, MockEngine serving series, detail and archive bytes; virtual time):

```kotlin
@Test fun awayFromHomeDoesNothing() = runTest { /* atHome false -> no archive request, report empty, outbox untouched */ }
@Test fun copiesOnlyMarkedDownloadedChapters() = runTest { /* 2 series, 1 marked; its 3 chapters: downloaded+path, known, downloaded+null path -> exactly 1 archive request */ }
@Test fun anIndexedChapterWithTheSameEtagIsSkipped() = runTest { ... }
@Test fun aChangedEtagIsCopiedAgain() = runTest { ... }
@Test fun anInterruptedCopyResumesWithRange() = runTest { /* .part exists with 100 bytes -> Range: bytes=100-, 206 -> final file = original bytes */ }
@Test fun aTruncatedArchiveIsNeverIndexed() = runTest { /* check returns 0 -> no index row, .part deleted, next chapter still copied */ }
@Test fun aRemovedFolderStopsWithTheBanner() = runTest { /* folder throws FolderUnavailable -> problem text exact, no index rows */ }
@Test fun aFullDeviceStopsOnceAndRemovesThePart() = runTest { /* first write throws DeviceFull -> one archive request total, .part gone, problem text exact */ }
@Test fun theBudgetStopsNewChapters() = runTest { /* each copy takes 20 virtual minutes, budget 45 -> 3 copied, pending > 0 */ }
@Test fun aCleanRunClearsAnOldProblem() = runTest { ... }
@Test fun theOutboxDrainsBeforeCopying() = runTest { /* request order: identity, PUT position, GET series, ..., archive */ }
@Test fun oldestChaptersFirst() = runTest { ... }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests '*ImportRunnerTest*'`
Expected: FAIL, unresolved `ImportRunner`.

- [ ] **Step 3: Implement `ImportRunner`.**

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): copy marked series' chapters from the server, resumably"
```

### Task 5: Background work, notifications, the Updates tab and the problem banner

**Files:**
- Create: `mobile/shared/src/androidMain/kotlin/app/soshuhen/core/ImportWorker.kt`, `.../core/ImportScheduler.kt`, `.../core/Notifier.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/updates/UpdatesViewModel.kt`, `.../updates/UpdatesScreen.kt`, `.../ui/ProblemBanner.kt`
- Modify: `.../MainShell.kt`, `.../library/LibraryScreen.kt`, `mobile/androidApp/src/main/AndroidManifest.xml`, `mobile/androidApp/src/main/kotlin/app/soshuhen/SoshuhenApplication.kt`, `MainActivity.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/updates/UpdatesViewModelTest.kt`, `.../core/NotificationTextTest.kt`

**Interfaces:**
- Consumes: `ImportRunner.run`, `LocalStore.problem()`, the `import_log` table.
- Produces:
  - `fun newChaptersText(title: String, numbers: List<Double>): Pair<String, String>` in commonMain: title `"<series>"`, text `"1 new chapter (141)"` or `"3 new chapters (139–141)"` (en dash, lowest–highest), the same wording as the web's notifications.
  - `ImportScheduler.schedule(context)`: a unique periodic `ImportWorker` every 1 hour with `NetworkType.CONNECTED` (`setRequiresBatteryNotLow(true)`), `ExistingPeriodicWorkPolicy.KEEP`; plus `runNow(context)`: a unique one-time request, `ExistingWorkPolicy.KEEP`, enqueued on app start, after marking a series, and from pull-to-refresh.
  - `ImportWorker : CoroutineWorker`: when more than 5 chapters are pending at the start, calls `setForeground(ForegroundInfo(id, notification, FOREGROUND_SERVICE_TYPE_DATA_SYNC))` with a progress notification on `import_progress`; then `ImportRunner.run`, then one `new_chapters` notification per series in the report (grouped under one summary when more than one series), tapping opens that series via an intent extra `series_id`. A `ForegroundServiceStartNotAllowedException` falls back to running without foreground.
  - Manifest: `POST_NOTIFICATIONS`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`; WorkManager's `SystemForegroundService` declared with `android:foregroundServiceType="dataSync"` via `tools:node="merge"`.
  - `UpdatesViewModel(store)`: `val rows: StateFlow<List<ImportLogRow>>`, newest first, grouped by day ("Today", "Yesterday", then the date).
  - Bottom bar becomes **Library · Updates · Settings**. `ProblemBanner` sits at the top of Library and Updates whenever `store.problem()` is non-null, in `Tokens.warning` / `Tokens.onWarning`.

- [ ] **Step 1: Write the failing tests**

```kotlin
@Test fun oneChapter() = assertEquals("Frieren" to "1 new chapter (141)", newChaptersText("Frieren", listOf(141.0)))
@Test fun severalChapters() = assertEquals("Frieren" to "3 new chapters (139–141)", newChaptersText("Frieren", listOf(141.0, 139.0, 140.0)))
@Test fun fractionalChapter() = assertEquals("Frieren" to "1 new chapter (23.5)", newChaptersText("Frieren", listOf(23.5)))
@Test fun updatesAreNewestFirstAndGroupedByDay() = runTest { ... }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest`
Expected: FAIL.

- [ ] **Step 3: Implement the text rule and `UpdatesViewModel`; then the worker, scheduler, notifier, manifest entries, the Updates screen, the banner, and the notification tap.** Notification channels are created in `SoshuhenApplication.onCreate`.

- [ ] **Step 4: Run the tests and the build**

Run: `./gradlew :shared:jvmTest :androidApp:assembleDebug`
Expected: PASS, `BUILD SUCCESSFUL`.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): copy new chapters in the background and say so"
```

### Task 6: Pages out of a CBZ

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/reader/PageRules.kt`, `.../reader/PageSource.kt` (interface)
- Create: `mobile/shared/src/androidMain/kotlin/app/soshuhen/reader/ZipPages.kt`, `mobile/shared/src/jvmMain/kotlin/app/soshuhen/reader/ZipPages.kt` (same `java.util.zip` code; a `jvmAndroid` intermediate source set is not worth its build configuration for one file — **builder's call**)
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/reader/PageRulesTest.kt`, `mobile/shared/src/jvmTest/kotlin/app/soshuhen/reader/ZipPagesTest.kt`

**Interfaces:**
- Produces:
  - `fun isPage(name: String): Boolean` and `fun naturalKey(name: String): List<Comparable<*>>` / `fun pageOrder(names: List<String>): List<String>`, exactly the server's rules (Global Constraints).
  - `fun spreads(pageCount: Int, mode: String): List<List<Int>>` and `fun spreadOf(groups: List<List<Int>>, page: Int): Int`, exactly `spreads.ts`.
  - `class ZipPages(cacheDir: Path)` with `suspend fun extract(chapterId: Long, source: Source): List<Path>`: streams the zip once (`ZipInputStream`), writes each page to `cacheDir/reader/<chapterId>/<index>.<ext>` in `pageOrder`, returns the paths; a second call for the same chapter returns the existing files without reading the zip. Keeps the 5 most recently opened chapters and deletes older extractions (this is the app's own cache, not the user's folder).
  - `ZipPages` also implements Task 4's `ArchiveCheck` (`pageCount` = number of `isPage` entries; a zip that cannot be read throws, which the runner treats as a failed check).
  - `sealed interface PageSource { data class Device(pages: List<Path>); data class Server(api: SoshuhenApi, chapterId: Long, pageCount: Int) }`.

- [ ] **Step 1: Write the failing tests**

```kotlin
// PageRulesTest
@Test fun macResourceForksAreNotPages() = assertFalse(isPage("__MACOSX/._001.jpg"))
@Test fun hiddenFilesAreNotPages() = assertFalse(isPage("ch1/.thumb.jpg"))
@Test fun comicInfoIsNotAPage() = assertFalse(isPage("ComicInfo.xml"))
@Test fun upperCaseExtensionIsAPage() = assertTrue(isPage("001.JPG"))
@Test fun directoriesAreNotPages() = assertFalse(isPage("ch1/"))
@Test fun naturalOrder() = assertEquals(listOf("Page 2.jpg", "Page 10.jpg"), pageOrder(listOf("Page 10.jpg", "Page 2.jpg")))
@Test fun nestedFoldersSortByFullName() = assertEquals(listOf("a/2.jpg", "a/10.jpg", "b/1.jpg"), pageOrder(listOf("b/1.jpg", "a/10.jpg", "a/2.jpg")))
@Test fun spreadsCoverAlone() = assertEquals(listOf(listOf(0), listOf(1, 2), listOf(3, 4), listOf(5)), spreads(6, "double"))
@Test fun spreadsSinglePagesOutsideDouble() = assertEquals(listOf(listOf(0), listOf(1)), spreads(2, "paged_rtl"))
@Test fun spreadOfFindsThePage() = assertEquals(2, spreadOf(spreads(6, "double"), 4))

// ZipPagesTest (JVM: builds a zip in a temp dir)
@Test fun extractsInServerOrderSkippingNonPages() { /* entries: ComicInfo.xml, __MACOSX/._001.jpg, 010.jpg, 002.jpg -> two files, 002 first */ }
@Test fun secondOpenDoesNotReread() { ... }
@Test fun keepsOnlyFiveChapters() { ... }
@Test fun pageCountOfAnEmptyZipIsZero() { ... }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement `PageRules`, `ZipPages` (both platforms) and `PageSource`.**

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): read a chapter's pages in the same order the server does"
```

### Task 7: Reader state

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/reader/ReaderViewModel.kt`, `.../reader/ReaderKeys.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/reader/ReaderViewModelTest.kt`

**Interfaces:**
- Consumes: `PageSource`, `ZipPages.extract`, `ChapterFolder.read`, `LocalStore` (device chapters, prefs snapshot `"prefs/<id>"`), `Outbox`, `Session.atHome`, `SoshuhenApi.manifest`/`prefs`, `chapterRows`.
- Produces:
  - `data class ReaderUi(seriesId: Long, chapter: ChapterRow, source: PageSource, pageCount: Int, page: Int, prefs: ReaderPrefs, previous: Long?, next: Long?, chromeVisible: Boolean)` and `sealed interface ReaderState { Loading; Ready(ui: ReaderUi); Unavailable(message: String) }`.
  - `class ReaderViewModel(seriesId: Long, chapterId: Long, startPage: Int?, deps…) : ViewModel` with `fun goTo(page: Int)`, `fun nextPage()`, `fun previousPage()` (both move by a spread in `double`), `fun openChapter(id: Long)`, `fun setPrefs(p: ReaderPrefs)`, `fun toggleChrome()`.
  - Choosing the source: the chapter on the device → `Device` (extract first); else, at home and the chapter `OnServer` → `Server`; else `Unavailable("Not on this device. It will be copied the next time you are home.")`. A device chapter whose file is gone → `Unavailable("This chapter's file is missing from the folder. It will be copied again at home.")` and the index row is forgotten so the next import restores it.
  - `previous`/`next`: neighbouring chapters by number that are readable from the chosen kind of source (device chapters away from home; device or on-server at home).
  - Every page change calls `outbox.position(seriesId, chapterId, page)`, debounced to 1 s. Reaching the last page (the last spread in `double`) calls `outbox.complete(seriesId, chapterId)` once per open, and marks the chapter read locally by raising the snapshot's `progress` to `floor(number)` when higher, so the library and detail show it at once.
  - Prefs: from the server at home (and saved as snapshot), else the snapshot, else the defaults `ReaderPrefs("paged_rtl", "fit_screen", "black")` (the server's own defaults). `setPrefs` saves the snapshot and calls `outbox.prefs`.
  - At home the outbox drains right after each queued event, so a phone that never leaves the house sends progress at once.
  - `object ReaderKeys { val events: SharedFlow<ReaderKey>; fun emit(k: ReaderKey): Boolean }`, `enum class ReaderKey { Next, Previous }`: the Android activity emits volume keys into it only while a reader is in front; `emit` returns whether a reader consumed it.

- [ ] **Step 1: Write the failing tests**

```kotlin
@Test fun aDeviceChapterOpensFromTheDevice() = runTest { ... }
@Test fun awayFromHomeAChapterNotOnTheDeviceIsUnavailable() = runTest { assertEquals("Not on this device. It will be copied the next time you are home.", (state as ReaderState.Unavailable).message) }
@Test fun atHomeAnOnServerChapterStreamsFromTheServer() = runTest { ... }
@Test fun atHomeANotDownloadedChapterIsUnavailable() = runTest { /* never calls manifest: that would make the server fetch from the source */ }
@Test fun aMissingFileIsUnavailableAndForgotten() = runTest { ... }
@Test fun pageChangesQueueOnePositionPerSecond() = runTest { /* goTo 1,2,3 within 500 ms -> one queued position page 3 */ }
@Test fun theLastPageCompletesOnce() = runTest { /* goTo last twice -> one complete */ }
@Test fun theLastSpreadCompletesInDoubleMode() = runTest { ... }
@Test fun completingRaisesLocalProgress() = runTest { ... }
@Test fun prefsFallBackToSnapshotThenDefaults() = runTest { ... }
@Test fun nextAwayFromHomeSkipsChaptersNotOnTheDevice() = runTest { ... }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests '*ReaderViewModelTest*'`
Expected: FAIL.

- [ ] **Step 3: Implement `ReaderViewModel` and `ReaderKeys`.**

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): know which chapter to read, from where, and what to send home"
```

### Task 8: Reader screen and volume keys

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/reader/ReaderScreen.kt`, `.../reader/PagedView.kt`, `.../reader/StripView.kt`, `.../reader/ReaderChrome.kt`
- Modify: `.../MainShell.kt` (reader route, full screen over the shell), `.../detail/SeriesDetailScreen.kt` (Continue and chapter rows open the reader), `.../settings/SettingsScreen.kt` (volume key switches), `.../core/ServerStore.kt` (two booleans), `mobile/androidApp/src/main/kotlin/app/soshuhen/MainActivity.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/reader/TapZonesTest.kt`

**Interfaces:**
- Consumes: `ReaderViewModel`, `ReaderUi`, `spreads`, `ReaderKeys`.
- Produces:
  - `fun tapAction(x: Float, width: Float, mode: String): TapAction` with `enum class TapAction { Previous, Next, Chrome }`: the left and right thirds turn, the middle third toggles the chrome; in `paged_rtl` the left third is **Next** (reading direction), in `paged_ltr` and `double` it is **Previous**; in `long_strip` every tap is `Chrome`.
  - Paged modes: `HorizontalPager` over `spreads(...)`, `reverseLayout = true` for `paged_rtl` and `double` (manga reads right to left; `double` follows the web, which lays spreads right to left). Long strip: `LazyColumn` of pages at full width. Each page is a Coil `AsyncImage` of the file path (device) or `api.pageUrl` (server), `ContentScale` from `scale` (`fit_width` → `FillWidth`, `fit_height` → `FillHeight`, `fit_screen` → `Fit`), background `Tokens.readerBlack/readerGray/readerWhite`. Pinch to zoom and pan with `Modifier.transformable`, reset on page change.
  - Chrome (toggled): top bar with back, series title and chapter; bottom with previous/next chapter, a page slider and the mode/scale/background choices. `double` is offered only when the window is at least medium width.
  - Settings: "Volume keys turn pages" (default on) and "Invert volume keys" (default off), stored in `ServerStore` as `volume_keys` / `volume_invert`.
  - `MainActivity.dispatchKeyEvent`: for `KEYCODE_VOLUME_DOWN` / `KEYCODE_VOLUME_UP` with `ACTION_DOWN`, when enabled, emits `Next` / `Previous` (swapped when inverted) into `ReaderKeys`; if `emit` returns true the event is consumed (no volume change), otherwise it passes through. `ACTION_UP` of a consumed key is consumed too. In `long_strip`, `Next`/`Previous` scroll by one screen height.
  - Detail: the "Continue chapter X" button is enabled and opens the reader at the resume page; tapping a chapter row opens it at page 0. A row that the reader would refuse (`Unavailable`) is drawn dimmed.

- [ ] **Step 1: Write the failing test**

```kotlin
@Test fun rtlLeftIsNext() = assertEquals(TapAction.Next, tapAction(10f, 900f, "paged_rtl"))
@Test fun ltrLeftIsPrevious() = assertEquals(TapAction.Previous, tapAction(10f, 900f, "paged_ltr"))
@Test fun middleToggles() = assertEquals(TapAction.Chrome, tapAction(450f, 900f, "paged_rtl"))
@Test fun stripAlwaysToggles() = assertEquals(TapAction.Chrome, tapAction(10f, 900f, "long_strip"))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./gradlew :shared:jvmTest --tests '*TapZonesTest*'`
Expected: FAIL.

- [ ] **Step 3: Implement `tapAction`, the screens, the settings switches and the key forwarding.**

- [ ] **Step 4: Run the tests, build, and read on the emulator** (`resizable_api36`, against the running stack; part 2's Task 6 ruling explains why not the phone): mark a series that has downloaded chapters, pull to refresh, wait for the "new chapters" notification, open a chapter in each mode, turn pages with the emulator's volume buttons, put the emulator in airplane mode, check that the library still shows its covers and the "Offline" banner, read another page, turn airplane mode off, and check the server's position for that series changed (`curl -s http://localhost:8080/api/reader/series/<id>/resume`).

Run: `./gradlew :shared:jvmTest :androidApp:installDebug`
Expected: PASS, `Installed on 1 device`, and each check above as described.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): read offline in the web's four modes, with volume keys"
```

### Task 9: First-run setup steps, release signing and docs

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/Platform.kt` (interface), `mobile/androidApp/src/main/kotlin/app/soshuhen/AndroidPlatform.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/onboarding/SetupScreen.kt`, `.../onboarding/SetupViewModel.kt`
- Modify: `.../App.kt`, `.../settings/SettingsScreen.kt`, `mobile/androidApp/build.gradle.kts`, `mobile/README.md`, `docs/features.md`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/onboarding/SetupViewModelTest.kt`

**Interfaces:**
- Consumes: `ServerStore.folder`/`saveFolder`, `ChapterFolder.isAvailable`.
- Produces:
  - `interface Platform { suspend fun pickFolder(): String?; suspend fun requestNotifications(): Boolean; val needsNotificationPermission: Boolean; fun isBatteryUnrestricted(): Boolean; fun openBatterySettings() }`. Android: `ACTION_OPEN_DOCUMENT_TREE` through an `ActivityResultLauncher` registered in `MainActivity.onCreate` and awaited with a `CompletableDeferred`, then `takePersistableUriPermission(READ|WRITE)`; `POST_NOTIFICATIONS` only when `SDK_INT >= 33`; `PowerManager.isIgnoringBatteryOptimizations`; `Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` with `package:app.soshuhen` (manifest permission `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`), falling back to `ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS`.
  - After a server is chosen and before the shell, `SetupScreen` shows three steps in order, each with a short why:
    1. "Where should chapters be kept?" → **Pick a folder** (required; the shell does not open without one).
    2. "Tell you about new chapters?" → **Allow** / **Not now** (only when `needsNotificationPermission`).
    3. "Let it copy in the background" (Samsung puts unused apps to sleep, and a sleeping app copies nothing) → **Open battery settings** / **Skip** (only when not already unrestricted).
  - `SetupViewModel(store, platform)` exposes `val step: StateFlow<SetupStep?>` (null when done) and remembers that steps 2 and 3 were offered once (`setup_offered` in `ServerStore`), so they are not asked again after "Not now" / "Skip".
  - Settings gains: the folder (with **Change folder**, which keeps existing imports indexed and copies new ones to the new folder), the battery status with **Open battery settings**, and the volume switches (Task 8).
  - `androidApp/build.gradle.kts`: a `release` signing config read from `mobile/keystore.properties` (`storeFile`, `storePassword`, `keyAlias`, `keyPassword`; gitignored) when it exists, else the debug signing config; `release` build type `isMinifyEnabled = false`. README: the one-time `keytool -genkeypair -v -keystore soshuhen.keystore -alias soshuhen -keyalg RSA -keysize 4096 -validity 36500`, the `keystore.properties` shape, `./gradlew :androidApp:installRelease`, and the warning that the keystore must never change.
  - `docs/features.md` "Android app" section: replace "come next" with what part 3 delivers (marking, folder, background copies, notifications, offline reading, volume keys, progress sent home), and say plainly that nothing is ever deleted unless you ask.

- [ ] **Step 1: Write the failing tests**

```kotlin
@Test fun theFolderStepComesFirstAndIsRequired() = runTest { /* no folder -> step Folder; pickFolder returns null -> still Folder */ }
@Test fun notificationsAreSkippedBelowAndroid13() = runTest { /* needsNotificationPermission false -> after folder, Battery */ }
@Test fun batteryIsSkippedWhenAlreadyUnrestricted() = runTest { ... }
@Test fun notNowIsNotAskedAgain() = runTest { /* decline notifications, recreate vm -> step null */ }
@Test fun aFolderThatLostItsPermissionAsksAgain() = runTest { /* store has folder, ChapterFolder.isAvailable false -> step Folder */ }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests '*SetupViewModelTest*'`
Expected: FAIL.

- [ ] **Step 3: Implement `Platform`, `AndroidPlatform`, `SetupViewModel`, `SetupScreen`, the Settings entries, the signing config, the README and the docs.**

- [ ] **Step 4: Run the tests, both builds, and the first run on a fresh emulator install**

Run: `./gradlew :shared:jvmTest :androidApp:assembleDebug :androidApp:assembleRelease` then `adb uninstall app.soshuhen; ./gradlew :androidApp:installDebug`
Expected: PASS and two `BUILD SUCCESSFUL`; on the emulator: server → folder picker → notification prompt → battery screen → library.

- [ ] **Step 5: Commit**

```bash
git add mobile docs/features.md
git commit -m "feat(mobile): set up the folder, notifications and battery on first run"
```

### Task 10: Web parity pass

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/app/soshuhen/library/LibraryScreen.kt`, `.../detail/SeriesDetailScreen.kt`, `.../updates/UpdatesScreen.kt`, `.../settings/SettingsScreen.kt`, `.../ui/theme/Tokens.kt` (typography and any token the web uses that the app lacks)
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/ui/theme/TypographyTest.kt`

**Interfaces:**
- Consumes: every screen built so far, and the web files named in Global Constraints.
- Produces:
  - `Tokens` gains the web's type scale (`display-lg` … `label-sm` from `frontend/tailwind.config.ts`, same sizes, line heights, letter spacing and weights) as a Material 3 `Typography` in `soshuhenTypography()`, and the web's fonts: Plus Jakarta Sans and JetBrains Mono, bundled as Compose resources from Google Fonts (OFL). `SoshuhenTheme` uses both.
  - The library card shows what `CoverCard.tsx` shows and nothing it does not: cover, title, the progress bar `progress / total` with its percentage, format and first genre, the unread count, and the same state badges for the series states the app can see. The Continue reading row matches `ContinueReading.tsx` (count, layout, chapter label, bar). The status chips match `StatusTabs.tsx` (order, labels, counts, "All" last).
  - The series screen follows `SeriesDetailPage.tsx`'s order for the parts the app has: header (cover, title, the same metadata line), the progress block as `ProgressManager.tsx` words it, then the chapter table as `ChapterTable.tsx` lays it out (columns, read marks, state wording), with the app's "on device" state and delete actions in the same row style.
  - Updates and Settings use the web's card and section styles from `SettingsPage.tsx`.

- [ ] **Step 1: Write the failing test**

```kotlin
@Test fun typeScaleMatchesTheWeb() {
    val t = soshuhenTypography()
    assertEquals(48.sp, t.displayLarge.fontSize); assertEquals(56.sp, t.displayLarge.lineHeight); assertEquals(FontWeight.ExtraBold, t.displayLarge.fontWeight)
    assertEquals(13.sp, t.labelMedium.fontSize); assertEquals(FontWeight.Medium, t.labelMedium.fontWeight)
    assertEquals(11.sp, t.labelSmall.fontSize); assertEquals(FontWeight.SemiBold, t.labelSmall.fontWeight)
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./gradlew :shared:jvmTest --tests '*TypographyTest*'`
Expected: FAIL, unresolved `soshuhenTypography`.

- [ ] **Step 3: Implement the typography and fonts, then bring each screen into line with its web file.** Work screen by screen: open the web page in the browser pane at 400 px and at 1280 px (`https://soshuhen.test`), screenshot the app on the emulator at the same widths, and change the app until the two read as the same screen. Record each remaining difference that is forced by the platform as a ruling.

- [ ] **Step 4: Run the tests and the build, and put the side-by-side screenshots in the workspace**

Run: `./gradlew :shared:jvmTest :androidApp:installDebug`
Expected: PASS, `Installed on 1 device`; one web/app screenshot pair per screen at each width.

- [ ] **Step 5: Commit**

```bash
git add mobile
git commit -m "feat(mobile): match the web's layout, type and wording screen by screen"
```
