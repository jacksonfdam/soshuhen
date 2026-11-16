# Device Offload and Storage Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Android app verify that the marked series are fully on the device, offer to delete the server's copies (new `offloaded` state), and show how much space the app's folder uses.

**Architecture:** The server gains an `offloaded` state for chapters and volumes, a `POST /api/offload` endpoint that only enqueues, and an `offload` job on the download lane that deletes a file only when the phone's ETag still matches. Reconcile paths and the J-Novel Club sync learn to leave `offloaded` alone; the web shows it as "On device" and can download it again. The app adds a Sync flow (import, verify, ask) and a storage section in Settings.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, Alembic, Postgres 17, pytest; React + Tailwind 4; Kotlin Multiplatform, Compose Multiplatform, Room, Ktor.

**Spec:** `docs/superpowers/specs/2026-11-16-device-offload-design.md`

## Global Constraints

- The state value is exactly `offloaded`, for both `chapter.state` and `volume.state`.
- The server never deletes a file unless the phone's ETag **and** size match the current file; a mismatch skips the item.
- Nothing ever queues an `offloaded` item automatically (cron, `auto_download`, discovery, J-Novel Club revision). Only an explicit user download does.
- `api` never writes `/manga`; deletion runs only in the `offload` job, registered on `Lane.DOWNLOAD`.
- In the app, **Keep on server** is the default and deletion is offered only when every item in scope is verified.
- Backend tests: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest …` from `backend/`; lint with `.venv/bin/python -m ruff check app/ tests/`.
- Frontend: no hex/px/rem literals; verify any new class with `grep` over `frontend/dist/` after `npm run build`.
- App: colours and sizes only from `ui/theme/Tokens.kt`; tests via `./gradlew :shared:jvmTest` from `mobile/` with `JAVA_HOME` on JDK 21.
- Komga's API is read from Komga's own OpenAPI document (`http://localhost:25600/v3/api-docs`), never from memory.
- Commits: English, microcommits, explicit file lists, no assistant attribution.

## Review Focus

1. **The phone posts an item that was rebuilt on the server after it copied it** — the file must stay. (Task 2 test `test_offload_skips_rebuilt_file`.)
2. **Komga still lists a deleted book after the scan** — the chapter/volume must stay `offloaded`, not flip back to `downloaded`. (Task 3 tests.)
3. **The same offload is posted twice (double tap, retry)** — the second run skips items no longer `downloaded` and does not fail. (Task 2 test `test_offload_twice_is_harmless`.)
4. **A file the user deleted by hand on the phone after it was indexed** — Sync must report it unverified and must not offer deletion. (Task 8 test `sync_report_blocks_when_file_missing`.)
5. **The user deletes an offloaded chapter from the phone** — they are warned that it is the only copy, and afterwards the row says how to get it back. (Task 9 tests.)

---

### Task 1: `offloaded` state for volumes and the `offload` job type

**Files:**
- Create: `backend/alembic/versions/0031_volume_offloaded.py`
- Modify: `backend/app/enums.py` (add `JobType.OFFLOAD = "offload"`, add it to `_DOWNLOAD_LANE`)
- Test: `backend/tests/test_lanes.py`, `backend/tests/test_migration_chain.py` (only if the chain test lists heads explicitly)

**Interfaces:**
- Produces: `JobType.OFFLOAD`; `volume_state_check` allowing `('known','queued','downloading','downloaded','failed','offloaded')`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lanes.py
def test_offload_runs_on_the_download_lane():
    assert lane_of(JobType.OFFLOAD) is Lane.DOWNLOAD

# tests/test_volume_offloaded_migration.py
async def test_volume_accepts_offloaded_state():
    # insert a prose series + volume, then:
    await session.execute(text("update volume set state = 'offloaded' where id = :id"), {"id": vid})
    await session.commit()  # no CheckViolation
```

- [ ] **Step 2: Run them to verify they fail**

Run: `… pytest tests/test_lanes.py tests/test_volume_offloaded_migration.py -q`
Expected: FAIL (`AttributeError: OFFLOAD`, `CheckViolationError`).

- [ ] **Step 3: Implement** the enum value and lane entry (comment: it deletes from `/manga`, which only `worker-download` mounts read-write), and migration `0031` (down_revision `0030`) that drops and recreates `volume_state_check` with `offloaded`. The downgrade raises if any volume is `offloaded` (`select 1 from volume where state = 'offloaded' limit 1`) rather than rewriting it.

- [ ] **Step 4: Run the tests to verify they pass**, plus `tests/test_migration_chain.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/enums.py backend/alembic/versions/0031_volume_offloaded.py backend/tests/test_lanes.py backend/tests/test_volume_offloaded_migration.py
git commit -m "feat(offload): add the offloaded volume state and the offload job type"
```

### Task 2: The `offload` handler

**Files:**
- Create: `backend/app/handlers/offload.py`
- Modify: `backend/app/handlers/__init__.py` (import the module so `@register` runs, as the others are)
- Test: `backend/tests/test_offload_handler.py`

**Interfaces:**
- Consumes: `JobType.OFFLOAD` (Task 1); `library_file` semantics from `app/api/routes_chapters.py` (re-implement the inside-library check through `app.reader.archive.inside` rather than importing from `api/`).
- Produces: payload shape `{"chapters": [{"id": int, "etag": str, "size": int}], "volumes": [...]}`; `def served_etag(path: Path) -> str` in `app/handlers/offload.py`, returning exactly the ETag `FileResponse` serves — compute it as `FileResponse(path, stat_result=os.stat(path)).headers["etag"]` so the two can never drift.

- [ ] **Step 1: Write the failing tests** (pattern: `tests/test_volume_download.py` — `LIBRARY_PATH` monkeypatched to `tmp_path`, truncate `series, job`)

```python
async def test_offload_deletes_matching_chapter_and_marks_it():
    # chapter downloaded, file written under tmp_path
    await run_offload(chapters=[{"id": cid, "etag": served_etag(f), "size": f.stat().st_size}])
    assert not f.exists()
    assert row.state == "offloaded" and row.file_path is None

async def test_offload_skips_rebuilt_file():
    # etag captured, then file rewritten with different bytes
    assert f.exists() and row.state == "downloaded"

async def test_offload_skips_size_mismatch(): ...          # same etag string, wrong size -> kept
async def test_offload_skips_row_not_downloaded(): ...     # state 'queued' -> untouched
async def test_offload_refuses_path_outside_library(): ... # file_path=/etc/hosts -> untouched, file kept
async def test_offload_marks_missing_file_offloaded(): ... # file already gone -> 'offloaded'
async def test_offload_deletes_volume(): ...               # same for a volume row
async def test_offload_removes_empty_series_folder(): ...
async def test_offload_twice_is_harmless(): ...            # second run: no error, nothing changes
async def test_offload_queues_one_komga_scan_per_series():
    assert [j.type for j in jobs] == ["komga_scan"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `… pytest tests/test_offload_handler.py -q` — Expected: FAIL (module not found).

- [ ] **Step 3: Implement `@register(JobType.OFFLOAD) async def handle(ctx: JobContext) -> None`**, one transaction per item, in this order: re-read row (`state = 'downloaded'` and same `file_path`), inside-library check, compare `served_etag` and size, `unlink`, `update … set state = 'offloaded', file_path = null`, then `rmdir` the series folder if empty. One bad item is logged and skipped, never raised. After the loop, enqueue `komga_scan` once per affected `series_id` with the same payload shape `download_batch` uses for its scan. Log deleted/skipped counts and bytes freed.

- [ ] **Step 4: Run the tests to verify they pass.**

- [ ] **Step 5: Commit** `backend/app/handlers/offload.py backend/app/handlers/__init__.py backend/tests/test_offload_handler.py` — `feat(offload): delete server copies the device has verified`

### Task 3: Keep `offloaded` from being undone

**Files:**
- Modify: `backend/app/handlers/chapter_discover.py` (`reconcile_with_komga`, the update near line 203)
- Modify: `backend/app/handlers/komga_scan.py` (volume match near line 433)
- Modify: `backend/app/handlers/jnc_library_sync.py` (`needs_download`)
- Test: `backend/tests/test_offload_guards.py`

**Interfaces:**
- Produces: `needs_download(..., state=...)` returns `False` when `state == "offloaded"`; new helper `def has_newer_revision(downloaded_updated: datetime | None, last_updated: datetime | None) -> bool` in `jnc_library_sync.py`, used by Task 4's API field.

- [ ] **Step 1: Write the failing tests**

```python
async def test_komga_reconcile_leaves_offloaded_chapter():
    # chapter offloaded, file_path null; fake Komga client lists a book with the same number
    await reconcile_with_komga(...)
    assert row.state == "offloaded" and row.file_path is None

async def test_komga_scan_leaves_offloaded_volume(): ...

def test_needs_download_false_for_offloaded_even_after_revision():
    assert not needs_download(status="owned", has_link=True, state="offloaded",
                              downloaded_updated=OLD, last_updated=NEW)

def test_has_newer_revision():
    assert has_newer_revision(OLD, NEW) and not has_newer_revision(NEW, NEW) and not has_newer_revision(None, NEW)

async def test_chapter_discover_never_queues_offloaded(): ...  # auto_download on, chapter offloaded -> no job
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement** — add `and state <> 'offloaded'` to both reconcile updates (with a comment: Komga keeps deleted books in its trash, so it keeps reporting them), and the `offloaded` early return in `needs_download`.

- [ ] **Step 4: Run the tests and the existing `test_jnc_library_sync.py`, `test_komga_volumes.py`, `test_reclaim_orphaned_chapters.py` to verify they pass.**

- [ ] **Step 5: Commit** — `fix(offload): keep Komga and J-Novel Club from undoing an offload`

### Task 4: API — offload endpoint, downloading back, counts

**Files:**
- Create: `backend/app/api/routes_offload.py` (router prefix `/api/offload`), register in `backend/app/api/main.py`
- Modify: `backend/app/api/routes_volumes.py` (add `POST /{volume_id}/download`)
- Modify: `backend/app/api/routes_series.py` (`download_range` state list; `offloaded` counts in list and detail queries near lines 122 and 183; `newer_revision` on each detail volume)
- Modify: `backend/app/api/library_content.py` (count `offloaded` as content)
- Test: `backend/tests/test_offload_api.py`

**Interfaces:**
- Consumes: `JobType.OFFLOAD`, `has_newer_revision` (Task 3).
- Produces:
  - `POST /api/offload` body `{"chapters": [{"id","etag","size"}], "volumes": [...]}` → `{"queued": int, "skipped": [{"id": int, "kind": "chapter"|"volume", "reason": str}]}`; 422 on an empty body. Enqueues one `OFFLOAD` job with the accepted items.
  - `POST /api/volumes/{id}/download` → `{"queued": bool}`; enqueues `VOLUME_DOWNLOAD` at priority 0 with `dedupe_key=f"volume_download:{id}"`, sets `state='queued'` when enqueued; 404 unknown; 409 unless `offloaded`, `failed` or `known`.
  - Series list/detail counts gain `offloaded: int`; each detail volume gains `newer_revision: bool`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_offload_endpoint_queues_one_job_and_reports_skips():
    r = await client.post("/api/offload", json={"chapters": [ok, {"id": queued_id, "etag": "x", "size": 1}]})
    assert r.json()["queued"] == 1 and r.json()["skipped"][0]["reason"] == "not downloaded"
    assert job_types() == ["offload"]

async def test_offload_endpoint_never_touches_files(): ...       # file still exists after the request
async def test_download_range_picks_offloaded_chapters(): ...
async def test_volume_download_queues_once(): ...                 # second call: queued False, one job
async def test_series_detail_reports_offloaded_and_newer_revision(): ...
async def test_fully_offloaded_series_stays_in_library(): ...
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement** as specified above. Close the session before returning only if the route streams (it does not here).

- [ ] **Step 4: Run the tests and `test_series_list_counts.py`, `test_series_detail_volumes.py`, `test_opt_in_downloads.py` to verify they pass.** Then `ruff check`.

- [ ] **Step 5: Commit** — `feat(offload): expose offloading and downloading back over the API`

### Task 5: Remove offloaded books from Komga

**Files:**
- Modify: `backend/app/komga/client.py` (one new method)
- Modify: `backend/app/handlers/offload.py` (call it after the scan is queued, or from `komga_scan` — see step 3)
- Test: `backend/tests/test_komga_client.py`, `backend/tests/test_offload_handler.py`

**Interfaces:**
- Produces: a `KomgaClient` method whose name and route come from Komga's OpenAPI document (e.g. a series- or library-scoped empty-trash call, or a per-book delete).

- [ ] **Step 1: Read Komga's OpenAPI document** from the running stack (`curl -s localhost:25600/v3/api-docs | jq '.paths | keys[]' | grep -i -E 'trash|books/\{bookId\}'`). Record the chosen route and why in the method's comment. Prefer the narrowest scope that removes only the deleted books; a library-wide trash empty is acceptable only because every deleted file in this library is one Soshuhen removed on purpose — say so in the comment.

- [ ] **Step 2: Write the failing tests** — client test asserting the exact method and path against an `httpx.MockTransport`; handler test asserting `komga_book_id` is cleared for offloaded rows once Komga no longer lists the book.

- [ ] **Step 3: Implement.** If the call must follow the scan, do it in `komga_scan` for rows `state = 'offloaded' and komga_book_id is not null`, so the order is guaranteed by the job chain instead of a sleep.

- [ ] **Step 4: Run the tests to verify they pass.**

- [ ] **Step 5: Commit** — `feat(offload): drop offloaded books from Komga`

### Task 6: Web — show offloaded, download a volume again

**Files:**
- Modify: `frontend/src/features/series/ChapterTable.tsx` (`TONE`/`LABEL`: `offloaded` → "On device"; the "Downloaded" filter excludes it)
- Modify: `frontend/src/features/series/VolumesPanel.tsx` (`stateBadge`: "On device", plus "Newer revision on J-Novel Club" when `newer_revision`; a "Download again" button for `offloaded`)
- Modify: `frontend/src/lib/api.ts` (`SeriesVolume.newer_revision: boolean`, `offloaded` count field, `api.downloadVolume(id)`)
- Modify: the series header component that shows downloaded counts — add "N on device only" when `offloaded > 0`

**Interfaces:**
- Consumes: Task 4 endpoints and fields.

- [ ] **Step 1: Implement** using existing `Badge` tones and button primitives only.
- [ ] **Step 2: Build and verify**: `cd frontend && npm run build`, then `grep -o 'On device' dist/assets/*.js | head -1` and grep `dist/assets/*.css` for any new class used.
- [ ] **Step 3: Commit** — `feat(web): show offloaded chapters and volumes, and download them again`

### Task 7: App — API, storage sums, free space

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/app/soshuhen/api/SoshuhenApi.kt`, `api/Models.kt`
- Modify: `mobile/shared/src/commonMain/kotlin/app/soshuhen/db/DeviceChapterEntity.kt`, `DeviceVolumeEntity.kt` (sum queries)
- Modify: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/LocalStore.kt`, `core/Platform.kt`
- Modify: `mobile/androidApp/src/main/kotlin/app/soshuhen/AndroidPlatform.kt`
- Test: `commonTest/.../api/SoshuhenApiTest.kt`, `commonTest/.../core/LocalStoreTest.kt`, `core/FakePlatform.kt`

**Interfaces:**
- Produces:
  - `suspend fun SoshuhenApi.offload(request: OffloadRequest): OffloadResult`; `@Serializable data class OffloadItem(val id: Long, val etag: String, val size: Long)`, `OffloadRequest(chapters: List<OffloadItem>, volumes: List<OffloadItem>)`, `OffloadResult(queued: Int, skipped: List<OffloadSkip>)`.
  - `SeriesVolume.newerRevision: Boolean = false` (`@SerialName("newer_revision")`).
  - `fun LocalStore.storageBySeries(): Flow<Map<Long, Long>>` (chapters + volumes, bytes) and `fun LocalStore.storageTotal(): Flow<Long>`.
  - `Platform.freeSpace(treeUri: String): VolumeSpace?` with `data class VolumeSpace(val free: Long, val total: Long)`; null when the volume cannot be resolved.

- [ ] **Step 1: Write the failing tests** — `offload_posts_items_and_decodes_result` (MockEngine asserts path `/api/offload` and JSON body), `storage_sums_chapters_and_volumes_per_series` (index two chapters of series 1 and a volume of series 2 → `{1: a+b, 2: c}`, total `a+b+c`).
- [ ] **Step 2: Run `./gradlew :shared:jvmTest` to verify they fail.**
- [ ] **Step 3: Implement.** Android `freeSpace`: resolve the tree URI's volume via `StorageManager.getStorageVolume(uri)` / `directory`, then `StatFs`; return null on any failure. `FakePlatform` returns a settable value.
- [ ] **Step 4: Run the tests to verify they pass**, and `./gradlew :androidApp:assembleDebug`.
- [ ] **Step 5: Commit** — `feat(mobile): offload API, storage sums and free space`

### Task 8: App — Sync report and the question

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/SyncCheck.kt` (pure rules)
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/Sync.kt` (orchestration: import, check, offload)
- Modify: `core/AppGraph.kt` (wire `Sync`)
- Test: `commonTest/.../core/SyncCheckTest.kt`, `commonTest/.../core/SyncTest.kt`

**Interfaces:**
- Consumes: `ImportRunner.run(...)`, `LocalStore.deviceChapter/deviceVolume`, `ChapterFolder.exists`, `SoshuhenApi.seriesDetail`, `SoshuhenApi.offload` (Task 7).
- Produces:
  - `data class SyncReport(val seriesCount: Int, val held: List<Held>, val missing: List<Missing>, val revised: List<Long>)` with `val allVerified: Boolean get() = missing.isEmpty() && held.isNotEmpty()` and `val bytes: Long` (sum of held sizes).
  - `data class Held(val ref: BookRef, val etag: String, val size: Long)`; `data class Missing(val ref: BookRef, val reason: MissingReason)`; `enum class MissingReason { NotCopied, FileGone, SizeMismatch, NoEtag, Unreadable }`.
  - `fun checkSync(details: List<SeriesDetail>, device: DeviceState): SyncReport` — pure; `DeviceState` holds the indexed rows and which URIs exist.
  - `class Sync { suspend fun run(scope: Set<Long>?, onProgress: (Int, Int) -> Unit): SyncReport; suspend fun offload(report: SyncReport): OffloadResult }` — `scope == null` means every marked series; `offload` refuses (throws `IllegalStateException`) unless `report.allVerified`.

- [ ] **Step 1: Write the failing tests**

```kotlin
@Test fun sync_report_all_verified() { assertTrue(checkSync(listOf(detail(ch1, ch2)), device(ch1, ch2)).allVerified) }
@Test fun sync_report_blocks_when_file_missing() { /* ch2 indexed, uri gone */ assertEquals(MissingReason.FileGone, r.missing.single().reason); assertFalse(r.allVerified) }
@Test fun sync_report_blocks_on_size_mismatch() { … }
@Test fun sync_report_blocks_on_null_or_unreadable_etag() { … }   // UNREADABLE_ETAG counts as Unreadable
@Test fun sync_report_ignores_offloaded_and_not_downloaded() { … } // only state=="downloaded" with filePath is in scope
@Test fun sync_report_lists_revised_offloaded_volumes() { … }     // newerRevision -> revised
@Test fun sync_offload_refuses_unverified_report() { assertFailsWith<IllegalStateException> { … } }
@Test fun sync_offload_posts_held_items() { /* fake api records request: ids, etags, sizes */ }
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement.** `Sync.run` calls `ImportRunner.run` first (the existing last-byte probe fills missing ETags), then refreshes details for the scope and calls `checkSync`. Refuses to run away from home (`Session` says not at home → report with a problem, no import).
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** — `feat(mobile): check the device against the server before offloading`

### Task 9: App — screens

**Files:**
- Modify: `settings/SettingsScreen.kt`, `settings/SettingsViewModel.kt` (storage block, per-series list, Sync button and dialog)
- Modify: `detail/SeriesDetailScreen.kt`, `detail/SeriesDetailViewModel.kt` (Sync action scoped to the series; only-copy warning on delete and unmark)
- Modify: `core/ChapterRows.kt` (labels), `detail/DetailRules.kt`
- Test: `commonTest/.../core/ChapterRowsTest.kt`, `commonTest/.../detail/DetailRulesTest.kt`, `commonTest/.../detail/SeriesDetailViewModelTest.kt`

**Interfaces:**
- Consumes: `Sync`, `SyncReport`, `LocalStore.storageBySeries/storageTotal`, `Platform.freeSpace` (Tasks 7–8).
- Produces: copy, exactly:
  - Question: `"All {n} chapters of {s} series are on this device. Free {size} on the server?"` — buttons `"Keep on server"` (default, dismiss) and `"Delete from server"`.
  - Not verified: `"{held} of {total} on device · {missing} could not be copied"` with the reasons listed; no delete button.
  - Row on device + offloaded: `"On device only"`. Row not on device + offloaded: `"Removed from server — download again from the web"`.
  - Delete/unmark warning for an offloaded item: `"This is the only copy. It will have to be downloaded again from the source."`
  - Storage: `"Used by Soshuhen {used} · Free on this card {free}"`; only `"Used by Soshuhen {used}"` when `freeSpace` is null.

- [ ] **Step 1: Write the failing tests** — `offloaded_on_device_row_label`, `offloaded_not_on_device_is_unavailable` (DetailRules `next` skips it), `deleting_offloaded_chapter_asks_first` (view model emits the warning before deleting; cancelling keeps the file).
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** with `Tokens` only; sizes formatted through the existing `ui/Format.kt` helper (add `formatBytes` there if absent, with a test).
- [ ] **Step 4: Run tests and `./gradlew :androidApp:assembleDebug`.** Install on a device at home and walk through: Sync with one file deleted by hand (no delete offered), Sync clean (question shown, Keep), Sync clean → Delete (server file gone, web shows "On device"), web "Download range" brings it back.
- [ ] **Step 5: Commit** — `feat(mobile): sync screen, offload question and storage indicator`

### Task 10: Docs

**Files:**
- Modify: `docs/data-model.md` (chapter and volume states: `offloaded`), `docs/architecture.md` (fifth download-lane job, the guards in Task 3), `docs/features.md` (Sync, storage indicator, downloading back), `mobile/README.md` if it lists features.

- [ ] **Step 1: Update the docs** from the code as built.
- [ ] **Step 2: Commit** — `docs: describe offloading to the device`
