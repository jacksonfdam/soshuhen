# Profiles (Android) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Android app opens on a profile picker with avatars, asks for a PIN where one is set, sends every request as the chosen profile, and keeps each person's marks, queued progress and offline snapshots apart on a shared device.

**Architecture:**
- **Profile key.** The chosen profile is one `Long` kept with the saved server. `0` is the managing profile and sends no header, which is exactly how the server reads a request with no profile. Any other value is a profile id sent as `X-Soshuhen-Profile`.
- **API.** `SoshuhenApi` takes that key, and `forProfile(key)` derives a client for another one, so a queued event can still be sent as whoever recorded it.
- **Device data.** The device's per-person data is keyed by the profile key. Key `0` keeps today's storage untouched, so an upgraded install loses nothing. Chapter and volume files stay shared.

**Tech Stack:** Kotlin Multiplatform (`shared/commonMain`), Compose Multiplatform, Room 2 KMP (schema in `shared/schemas`), Ktor client with `MockEngine` in tests, DataStore preferences, `./gradlew :shared:jvmTest`.

**Spec:** `docs/superpowers/specs/2026-11-25-profiles-design.md` (sections "Android app" and "Avatars", plus the threat model under "Intent"). It builds on the server contract from `docs/superpowers/plans/2026-11-25-profiles-backend.md` (jacksonfdam/soshuhen#289), and reuses the avatar art from `docs/superpowers/plans/2026-11-26-profiles-web.md`.

## Global Constraints

- Branch from `main` once #289 and the web branch have merged, or from `feat/profiles-web` until then. Never commit Android work onto either of those branches.
- Server contract, quoted from the backend plan:
  - `GET /api/profiles` returns `[{id, name, avatar, has_pin, is_manager, position}]`.
  - `POST /api/profiles/{id}/unlock` takes `{pin}` and returns `{ok}`. A profile without a PIN answers `ok: true`.
  - A request without `X-Soshuhen-Profile` acts as the manager.
  - An unknown profile id gets a 400.
- Profile key: `0` means the managing profile and sends no header. Any other key is that profile's server id. The manager is always stored as `0`, never under its server id, so data recorded before profiles existed stays the manager's.
- PIN: `^\d{4,6}$`, checked only by the server. The app never stores a PIN or a hash of one.
- The PIN stops a wrong tap, not a determined user (spec, Intent). Copy never calls it security.
- **Offline (a ruling this plan makes; the spec is silent):**
  - A cold start away from home opens the last chosen profile without the picker.
  - "Switch profile" away from home lists the cached profiles. Profiles with a PIN are shown disabled with "Needs the server to check the PIN".
- **Picker:**
  - Shown on every cold start at home when the server has more than one profile.
  - With one profile it is skipped, so a single-person install looks unchanged.
  - A saved profile key the server no longer knows (a 400, or missing from `GET /api/profiles`) goes back to the picker.
- Offload (delete the server's copies) is offered only to the managing profile, because the files it deletes are shared by every profile.
- Every colour and size lives in `ui/theme/Tokens.kt`.
- Avatars are bundled PNGs rasterised from `frontend/public/avatars/*.svg` at 192×192. The SVGs are the source of truth.
- Verification for every task: `./gradlew :shared:jvmTest` green. For tasks that touch screens, also `./gradlew :androidApp:assembleDebug`.

## Review Focus

1. **Upgrading an install that already has marks and queued progress:** after the upgrade they belong to the manager (key 0), the manager's library still shows them, and the outbox still drains. Test in Task 3 (`MigrationTest`) and Task 4.
2. **Switching profiles with events still queued:** each event is sent as the profile that recorded it, not the one now selected. Test in Task 4 (`OutboxTest`).
3. **Two people with the same series marked on one tablet:** one unmarking it with "delete files", or deleting read chapters, must not delete files the other still has marked. Test in Task 5 (`DeviceLibraryTest`).
4. **The saved profile was deleted on the server:** the next start shows the picker instead of failing every request with 400. Test in Task 6 (`startRoute`).
5. **A wrong PIN, and offline:** a wrong PIN clears and stays on the pad. Offline, a PIN profile cannot be opened from the picker. Test in Task 6 (`ProfilesViewModelTest`).

---

### Task 1: The profile in every request

**Files:**
- Modify: `shared/src/commonMain/kotlin/app/soshuhen/api/SoshuhenApi.kt`, `api/Models.kt`
- Test: `shared/src/commonTest/kotlin/app/soshuhen/api/SoshuhenApiTest.kt`

**Interfaces:**
- Produces in `Models.kt`: `@Serializable data class Profile(val id: Long, val name: String, val avatar: String, @SerialName("has_pin") val hasPin: Boolean, @SerialName("is_manager") val isManager: Boolean, val position: Int)`.
- Produces in `Models.kt`: `fun Profile.key(): Long = if (isManager) 0 else id`.
- Produces in `SoshuhenApi.kt`:
  - `class SoshuhenApi(val baseUrl: String, client: HttpClient, val profileKey: Long = 0)`. When `profileKey != 0`, every request carries `X-Soshuhen-Profile: <profileKey>`. Implement it once, as `client.config { defaultRequest { header(...) } }` held in a private field, so no call site can forget it.
  - `fun forProfile(key: Long): SoshuhenApi`
  - `suspend fun profilesJson(): String`
  - `suspend fun profiles(): List<Profile>`
  - `suspend fun unlock(profileId: Long, pin: String): Boolean` posts to `/api/profiles/{id}/unlock`.

- [ ] **Step 1: Write the failing tests** in `SoshuhenApiTest` with `MockEngine`, recording each request's headers:
  - `noHeaderForTheManager`: `SoshuhenApi(base, client).series()` sends no `X-Soshuhen-Profile`.
  - `everyRequestCarriesTheProfile`: with `profileKey = 7`, `series()`, `putPosition(...)`, `complete(...)` and `coverUrl` fetching through the same client all send `X-Soshuhen-Profile: 7`.
  - `forProfileSwitchesOnlyTheCopy`: `api.forProfile(7)` sends `7`, and the original `api` still sends none.
  - `unlockReadsOk`: the mock answers `{"ok":false}` and `unlock(7, "1234")` returns `false`. The request body is `{"pin":"1234"}`.
  - `profilesDecode`: `profiles()` decodes the contract's JSON, and `key()` is `0` for `is_manager: true`.
- [ ] **Step 2: Run them and see them fail.** Run `./gradlew :shared:jvmTest --tests '*SoshuhenApiTest*'`. Expected: they fail to compile, because `profileKey`, `Profile` and `unlock` don't exist yet.
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run the tests.** Run `./gradlew :shared:jvmTest`. Expected: everything passes.
- [ ] **Step 5: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/app/soshuhen/api mobile/shared/src/commonTest/kotlin/app/soshuhen/api
git commit -m "feat(mobile): send the chosen profile with every request"
```

---

### Task 2: Remember the chosen profile

**Files:**
- Modify: `core/ServerStore.kt`, `core/DataStoreServerStore.kt` (androidMain), `core/InstanceGuard.kt`, `core/Session.kt`, `core/AppGraph.kt`
- Test: `commonTest/.../core/SessionTest.kt`, `core/Fakes.kt` (the fake store), and `core/ServerSwitchTest.kt`

**Interfaces:**
- Produces in `ServerStore`:
  - `val profileKey: Flow<Long?>`. Null means no profile has been chosen on this device yet.
  - `suspend fun selectProfile(key: Long?)`.
  - Stored beside the saved server. `clear()` (switching server) clears it too, because a profile id means nothing on another server.
- Produces in `Session`: `val api: StateFlow<SoshuhenApi?>` now combines the saved server with `profileKey ?: 0`.
- Produces in `Session`: `val profileKey: StateFlow<Long>`, which is `0` while none is chosen.

- [ ] **Step 1: Write the failing tests.**
  - `SessionTest.apiFollowsTheChosenProfile`: after `selectProfile(7)`, `session.api.value!!.profileKey == 7L`. After `selectProfile(null)`, it is `0L`.
  - `ServerSwitchTest.switchingServerForgetsTheProfile`: after a server switch, `profileKey.first()` is `null`.
- [ ] **Step 2: Run and see them fail.** Run `./gradlew :shared:jvmTest`. Expected: FAIL.
- [ ] **Step 3: Implement it.** DataStore key: `longPreferencesKey("profile_key")`. Removing the key stores null.
- [ ] **Step 4: Run the tests.** Run `./gradlew :shared:jvmTest`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(mobile): remember which profile this device is using`.

---

### Task 3: Per-person device data

**Files:**
- Modify: `db/MarkedEntity.kt`, `db/OutboxEntity.kt`, `db/SoshuhenDatabase.kt` (version 4, plus `MIGRATION_3_4`), `core/LocalStore.kt`, `core/AppGraph.kt`
- Create: `shared/schemas/app.soshuhen.db.SoshuhenDatabase/4.json` (generated by the build)
- Test: `jvmTest/.../db/MigrationTest.kt`, `commonTest/.../core/LocalStoreTest.kt`

**Interfaces:**
- `marked` changes to the primary key `(profile_key, series_id)`, with a `profile_key INTEGER NOT NULL DEFAULT 0` column.
- `outbox` gains `profile_key INTEGER NOT NULL DEFAULT 0`.
- `MIGRATION_3_4` is a manual `Migration`, because a primary key change needs the table rebuilt. Copy existing rows with `profile_key = 0`. Room's auto-migration cannot be trusted with a primary key change.
- `LocalStore(db, clock, profileKey: () -> Long = { 0 })`. AppGraph passes `{ session.profileKey.value }`.
  - Marks, the outbox and the per-person snapshots (`series`, `series/{id}`, `prefs/{id}`, `resume/{id}`) read and write under the current key.
  - Snapshot keys get the prefix `p{key}/` for keys other than 0. Key 0 keeps today's unprefixed names, so an upgraded install's snapshots stay the manager's.
  - Device chapter and volume rows stay unkeyed: the files are shared.
- Produces: `LocalStore.markedByOthers(seriesId: Long): Boolean`, which is true when a profile other than the current one has the series marked.
- Produces: `LocalStore.putProfiles(json: String)` and `LocalStore.profilesSnapshot(): List<Profile>?` under the unprefixed key `profiles`. The list is the server's, not one person's.

- [ ] **Step 1: Write the failing tests.**
  - `MigrationTest.marksAndOutboxBelongToTheManagerAfter3To4`:
    - Create the version 3 database with one `marked` row and one `outbox` row.
    - Migrate it to 4 with `MIGRATION_3_4`.
    - Both rows read back with `profile_key = 0`.
    - Inserting the same `series_id` for key 7 succeeds.
  - `LocalStoreTest.marksAreKeptApart`: mark series 5 under key 0, switch the key provider to 7. Then `markedIds()` is empty and `markedByOthers(5)` is `true`.
  - `LocalStoreTest.snapshotsAreKeptApart`: `saveSeries` under key 7 is not returned by `seriesSnapshot()` under key 0, and the reverse holds too.
  - `LocalStoreTest.theManagerKeepsUnprefixedSnapshots`: a row stored under the key `series` before profiles is what key 0 reads.
- [ ] **Step 2: Run and see them fail.** Run `./gradlew :shared:jvmTest`. Expected: FAIL.
- [ ] **Step 3: Implement it.** Bump the version and register `MIGRATION_3_4` where the database is built, in `DatabaseBuilder.android.kt` and `DatabaseBuilder.jvm.kt`. Let the build write `4.json`.
- [ ] **Step 4: Run the tests.** Run `./gradlew :shared:jvmTest`. Expected: PASS, with `4.json` generated and committed.
- [ ] **Step 5: Commit** with `feat(mobile): keep each profile's marks, queue and snapshots apart`.

---

### Task 4: Send queued events as who recorded them

**Files:**
- Modify: `core/Outbox.kt`
- Test: `commonTest/.../core/OutboxTest.kt`

**Interfaces:**
- Consumes: `SoshuhenApi.forProfile` (Task 1), and `OutboxEntity.profileKey` plus the `LocalStore` key provider (Task 3).
- `position`/`complete`/`completeVolume`/`prefs` stamp the current `profileKey` on the entity they write.
- `drain(api)` drains every profile's events in id order and sends each with `api.forProfile(event.profileKey)`. Order stays global, because the server must hear events in the order they happened.

- [ ] **Step 1: Write the failing tests.**
  - `OutboxTest.anEventIsSentAsTheProfileThatRecordedIt`:
    - Record a position under key 7, switch the key to 0, record another, then drain against a `MockEngine`.
    - The first request carries `X-Soshuhen-Profile: 7` and the second carries none.
  - `OutboxTest.anUpgradedQueueDrainsAsTheManager`: an entity inserted with the default `profile_key` (0) sends no header.
- [ ] **Step 2: Run and see them fail.** Run `./gradlew :shared:jvmTest`. Expected: FAIL.
- [ ] **Step 3: Implement it.** `store.outbox()` returns every profile's rows. Drain is not scoped to the current profile.
- [ ] **Step 4: Run the tests.** Run `./gradlew :shared:jvmTest`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(mobile): send queued reading as the profile that read it`.

---

### Task 5: Shared files survive another profile's cleanup

**Files:**
- Modify: `core/DeviceLibrary.kt`, `settings/SettingsViewModel.kt` and `core/SyncFlow.kt` (offload)
- Test: `commonTest/.../core/DeviceLibraryTest.kt`, `commonTest/.../settings/SettingsViewModelTest.kt` (or `SyncFlowTest.kt`, wherever the offload question is decided today)

**Interfaces:**
- Consumes: `LocalStore.markedByOthers` (Task 3) and `Session.profileKey` (Task 2).
- `DeviceLibrary.unmark(seriesId, deleteFiles = true)` and `deleteRead(detail)` delete no file of a series that `markedByOthers` reports. The current profile's mark is still removed.
- The offload question (delete the server's copies) is offered only when `profileKey == 0`.

- [ ] **Step 1: Write the failing tests.**
  - `DeviceLibraryTest.unmarkingKeepsFilesAnotherProfileHasMarked`:
    - Series 5 is marked under keys 0 and 7, with two device chapters.
    - Under key 7, `unmark(5, deleteFiles = true)` leaves both files in `FakeChapterFolder` and removes only key 7's mark.
  - `DeviceLibraryTest.deletingReadKeepsSharedFiles`: the same setup with `deleteRead` keeps both files.
  - `DeviceLibraryTest.filesNoOneElseMarkedAreDeleted`: only key 7 marked it, and `unmark(..., true)` deletes the files, as it does today.
  - The offload test: under key 7, the sync result offers no offload. Under key 0 it does, as today.
- [ ] **Step 2: Run and see them fail.** Run `./gradlew :shared:jvmTest`. Expected: FAIL.
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run the tests.** Run `./gradlew :shared:jvmTest`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(mobile): never delete files another profile still has marked`.

---

### Task 6: Picker, PIN pad and switching

**Files:**
- Create:
  - `profiles/StartRoute.kt` (pure)
  - `profiles/ProfilesViewModel.kt`
  - `profiles/ProfilePickerScreen.kt`
  - `profiles/PinPad.kt`
  - `ui/Avatar.kt`
  - `composeResources/drawable/avatar_01.png` … `avatar_12.png`
- Modify: `App.kt` (gate between setup and `MainShell`), `settings/SettingsScreen.kt` and `SettingsViewModel.kt` ("Switch profile"), and `ui/theme/Tokens.kt` (avatar sizes `avatarSm = 40.dp`, `avatarLg = 96.dp`, and the PIN dot size)
- Test:
  - `commonTest/.../profiles/StartRouteTest.kt`
  - `commonTest/.../profiles/ProfilesViewModelTest.kt`

**Interfaces:**
- Produces in `StartRoute.kt`:
  - `sealed interface StartRoute { data object Picker; data class Open(val key: Long) }`
  - `fun startRoute(profiles: List<Profile>?, atHome: Boolean, saved: Long?, chosenThisLaunch: Boolean): StartRoute`:
    - Already chosen this launch: `Open(saved ?: 0)`.
    - Away from home: `Open(saved ?: 0)`.
    - At home with `profiles` loaded and `size <= 1`: `Open(0)`.
    - At home, and `saved` names no profile in the list (deleted): `Picker`.
    - At home with more than one profile: `Picker`.
    - At home with `profiles` not yet loaded: `Open(saved ?: 0)`, which is replaced once they load.
- Produces in `ProfilesViewModel(session, store, local)`:
  - `state: StateFlow<ProfilesState>`, with `ProfilesState(profiles: List<Profile>, atHome: Boolean, pinFor: Profile?, pinError: Boolean, busy: Boolean)`.
  - `fun choose(profile: Profile)`: a profile without a PIN, or the manager's own key, selects it at once. A profile with a PIN opens the pad, and away from home it is not selectable.
  - `fun submitPin(pin: String)` calls `unlock`. `true` selects the profile. `false` sets `pinError` and clears the pad.
  - `fun cancelPin()`.
  - Profiles load from `api.profiles()` and are saved with `local.putProfiles`. Away from home they come from `local.profilesSnapshot()`.
- Avatar art: rasterise each SVG to a 192×192 PNG named `avatar_NN.png`, with any SVG-to-PNG tool. `Avatar(avatar: String, name: String, size: Dp)` maps `avatar-07` to `Res.drawable.avatar_07`, and an unknown key to `avatar_01`.
- Screens:
  - **Picker:** a grid of avatar and name, with a lock badge on profiles that have a PIN. Away from home, PIN profiles are dimmed and labelled "Needs the server to check the PIN".
  - **PIN pad:** six dots and a digit grid. It submits automatically at 6 digits, or on an OK key once at least 4 are entered. A wrong PIN shakes and clears. The copy is "Enter {name}'s PIN".
  - **Settings:** "Switch profile" shows the current avatar and name and opens the picker. It is shown only when the server has more than one profile.

- [ ] **Step 1: Write the failing tests.**
  - `StartRouteTest` has one test per branch above, including `aDeletedProfileGoesBackToThePicker` and `awayFromHomeOpensTheLastProfile`.
  - `ProfilesViewModelTest` uses `MockEngine` and the existing fakes:
    - `aProfileWithoutPinOpensAtOnce` checks the store's key becomes 7.
    - `aWrongPinStaysOnThePad`: the mock answers `ok:false`, so `pinError` is true, the key is unchanged and `pinFor` is still set.
    - `theRightPinOpens`.
    - `choosingTheManagerStoresZero`.
    - `offlineAPinProfileCannotBeOpened`: `atHome = false` and `choose(pinProfile)` changes nothing.
    - `profilesComeFromTheSnapshotAwayFromHome`.
- [ ] **Step 2: Run and see them fail.** Run `./gradlew :shared:jvmTest`. Expected: FAIL.
- [ ] **Step 3: Implement it.** That means the view model and `startRoute`, then the screens and avatars, then the gate in `App.kt` and the Settings entry.
- [ ] **Step 4: Run the tests and build.** Run `./gradlew :shared:jvmTest` and expect PASS. Run `./gradlew :androidApp:assembleDebug` and expect BUILD SUCCESSFUL.
- [ ] **Step 5: Check it on a device or emulator** against the branch API (run `backend/` with `uvicorn` on the LAN, or the rebuilt stack once merged):
  - With one profile, the app opens straight to the library.
  - Add a second profile with a PIN on the web, then cold-start the app. The picker shows both.
  - A wrong PIN shakes and clears. The right PIN opens her library, which holds only her series.
  - Read a page, then switch to the manager. Her position was sent with her header (check `progress_write`/`reading_position` rows on the server).
  - Turn Wi-Fi off and cold-start. The app opens her profile, and "Switch profile" shows the manager enabled and any PIN profile dimmed.
- [ ] **Step 6: Commit** with `feat(mobile): profile picker, PIN pad and switching`.

---

### Task 7: Docs

**Files:**
- Modify: `mobile/README.md` (a "Profiles" section covering the key `0` convention, migration 3→4, offline behaviour and how to regenerate the avatar PNGs), `docs/features.md` (one paragraph on the app's picker), and `docs/architecture.md` › "Endpoints the Android client uses" (`/api/profiles`, `/unlock`, and the header)

- [ ] **Step 1: Write the docs.** Every statement must match Tasks 1 to 6.
- [ ] **Step 2: Run** `./gradlew :shared:jvmTest :androidApp:assembleDebug` once more. Expected: green.
- [ ] **Step 3: Commit** with `docs(mobile): profiles in the Android app`.
