# Profiles (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Soshuhen server hold several profiles, each with its own list accounts, list entries, reading state and history, over one shared library, without changing anything for a client that names no profile.

**Architecture:** Migration `0033` adds a `profile` table and a `profile_id` to every per-person table, backfilled to one managing profile. A FastAPI dependency resolves `X-Soshuhen-Profile` (absent means the manager); routes, `reader_service.py` and job payloads carry the resolved profile id down to every query. Komga, anime discovery and the J-Novel Club token stay with the manager.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + asyncpg, Alembic, Postgres 17, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-25-profiles-design.md`

This is plan 1 of 3. The web Profiles section and the Android picker get their own plans once this lands; both depend only on the HTTP contract in Task 2.

## Global Constraints

- Header name: `X-Soshuhen-Profile`, value the profile id. Absent: the managing profile. Unknown or non-integer id: HTTP 400, never a fallback.
- Exactly one profile has `is_manager = true`. It cannot be deleted (HTTP 409).
- PIN: `^\d{4,6}$`. Stored as `scrypt$<salt hex>$<hash hex>` via `hashlib.scrypt(n=2**14, r=8, p=1)`, 16-byte salt. `pin_hash` never leaves the server; clients get `has_pin`.
- Avatar keys: `avatar-01` … `avatar-12` (`AVATAR_KEYS` in `app/profiles.py`). The migration's manager profile is named `Me` with `avatar-01`.
- One migration: `0033_profiles`, `down_revision = "0032_job_rerun_requested"`.
- Job payloads gain `profile_id`. A payload without it (queued before the upgrade) is the manager's.
- Komga read marks, `progress_push`, `anime_list_sync`, `suggest_build`, discovery and J-Novel Club act for the manager only.
- A provider's `static_credential()` answers for the manager only.
- Nothing in code, copy or docs calls the PIN security.
- Backend rules from `CLAUDE.md`: only `handlers/` and `api/reader_service.py` write; `cast(:x as text) is null` for nullable params; comments say why, not what.
- Run tests with `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest ...` from `backend/`; `ruff check app/ tests/` clean at every commit.

## Review Focus

1. **The same title on both profiles' lists.** The daughter's AniList entry with the same `provider_media_id` as the owner's must join the owner's series, not create a second one or overwrite the owner's entry. Test in Task 4.
2. **A job queued before the upgrade.** A pending `progress_write` with no `profile_id` and the old dedupe key must run as the manager. Test in Task 5.
3. **A phone still holding a deleted profile's id.** Every request answers 400, including the reader's page routes. Test in Task 2.
4. **Finishing a chapter under a non-managing profile on a series that has a Komga book.** No `komga_read_progress` job, and her progress write uses her tokens. Test in Task 6.
5. **The owner removing a series the daughter also holds.** The series row, mapping and chapters survive and leave only the owner's library. Test in Task 8.

---

### Task 1: Migration 0033 and models

**Files:**
- Create: `backend/alembic/versions/0033_profiles.py`
- Modify: `backend/app/models.py` (add `Profile`, `ChapterBookmark`, `NotificationRead`; `profile_id` on `ProviderToken`, `ListEntry`, `ReadingPosition`, `SeriesReaderPref`, `ProgressEvent`, and the `removed_entry` model if one exists; drop `Chapter.bookmarked`, `Notification.read_at`)
- Test: `backend/tests/test_migration_profiles.py`

**Interfaces:**
- Produces tables:
  - `profile(id bigserial pk, name varchar(40) not null, avatar varchar(20) not null, pin_hash text null, is_manager boolean not null default false, position integer not null default 0, created_at timestamptz not null default now())`, partial unique index `uq_profile_manager on profile (is_manager) where is_manager`.
  - `profile_id bigint not null references profile(id) on delete cascade` on `provider_token`, `list_entry`, `reading_position`, `series_reader_pref`, `progress_event`, `removed_entry`.
  - Keys: `provider_token` PK `(profile_id, provider)`; `list_entry` unique `uq_list_entry_profile_provider_media (profile_id, provider, provider_media_id)` replacing `uq_list_entry_provider_media`; `reading_position` PK `(profile_id, series_id)`; `series_reader_pref` PK `(profile_id, series_id)`; `removed_entry` unique on `(profile_id, provider, provider_media_id)`.
  - `chapter_bookmark(profile_id, chapter_id)` PK both, both FKs `on delete cascade`.
  - `notification_read(profile_id, notification_id, read_at timestamptz not null)` PK `(profile_id, notification_id)`, both FKs `on delete cascade`.
- Backfill: insert the manager (`Me`, `avatar-01`, `is_manager = true`), set every existing row's `profile_id` to it, copy `chapter.bookmarked = true` into `chapter_bookmark` and `notification.read_at is not null` into `notification_read`, then drop both columns.
- Downgrade: restore `chapter.bookmarked` and `notification.read_at` from the manager's rows, delete every non-manager row from the per-person tables, restore the old keys, drop the new columns and tables.

- [ ] **Step 1: Write the failing tests**

`test_upgrade_attaches_existing_rows_to_the_manager`: run `alembic downgrade 0032_job_rerun_requested`, insert a series, a `list_entry`, a `provider_token`, a `reading_position`, a chapter with `bookmarked = true` and a notification with `read_at` set; run `alembic upgrade head`; assert `select count(*) from profile` is 1 and that row is `is_manager`, every inserted row's `profile_id` equals it, `chapter_bookmark` holds the chapter, `notification_read` holds the notification.

`test_two_profiles_may_hold_the_same_provider_entry`: with two profiles, inserting `list_entry` rows with equal `(provider, provider_media_id)` and different `profile_id` succeeds; a second row for the same profile raises `IntegrityError`.

`test_only_one_manager`: inserting a second `is_manager = true` profile raises `IntegrityError`.

`test_downgrade_keeps_the_managers_data`: after upgrade with a second profile holding a `list_entry`, `alembic downgrade 0032_job_rerun_requested` leaves the manager's entry and drops the other; then `upgrade head` again so later tests run on head.

Run alembic through `subprocess.run([sys.executable, "-m", "alembic", ...], check=True)`, as `conftest.schema` does. Truncate what you insert in a fixture.

- [ ] **Step 2: Run to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_migration_profiles.py -q`
Expected: FAIL (`relation "profile" does not exist`).

- [ ] **Step 3: Write the migration and update `models.py`**

- [ ] **Step 4: Run the new tests, then the whole suite**

Run: `... pytest tests/test_migration_profiles.py -q` → PASS. Then `... pytest tests -q`: expect failures only where code reads `chapter.bookmarked`, `notification.read_at` or conflicts on the old `list_entry`/`provider_token` keys. Fix those minimally by naming the manager (`(select id from profile where is_manager)`) so the suite is green; later tasks replace that with the real profile.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0033_profiles.py backend/app/models.py backend/tests/test_migration_profiles.py <files fixed in step 4>
git commit -m "feat(profiles): add profiles and attach per-person data to them"
```

---

### Task 2: Profile module, request dependency and profile API

**Files:**
- Create: `backend/app/profiles.py`, `backend/app/api/routes_profiles.py`, `backend/tests/profiles_fixture.py`
- Modify: `backend/app/api/deps.py`, `backend/app/api/main.py` (register router)
- Test: `backend/tests/test_profiles_api.py`

**Interfaces:**
- Produces in `app/profiles.py`:
  - `@dataclass(frozen=True) class Profile: id: int; is_manager: bool`
  - `AVATAR_KEYS: tuple[str, ...]` (`avatar-01` … `avatar-12`)
  - `hash_pin(pin: str) -> str`, `verify_pin(pin: str, stored: str) -> bool` (constant-time compare via `hmac.compare_digest`), `valid_pin(pin: str) -> bool`
  - `async def manager(session) -> Profile`
  - `async def by_id(session, profile_id: int) -> Profile | None`
  - `async def of_job(session, payload: dict) -> Profile`: `payload.get("profile_id")` or the manager
  - `async def all_profiles(session) -> list[Profile]`
- Produces in `app/api/deps.py`: `async def current_profile(session, x_soshuhen_profile: str | None = Header(None)) -> Profile`, and `CurrentProfile = Annotated[Profile, Depends(current_profile)]`.
- Produces HTTP (all JSON):
  - `GET /api/profiles` → `[{id, name, avatar, has_pin, is_manager, position}]` ordered by `position, id`
  - `POST /api/profiles` `{name, avatar, pin?}` → the profile, 201
  - `PATCH /api/profiles/{id}` `{name?, avatar?, pin?: str | null, position?}`; `pin: null` clears it
  - `POST /api/profiles/{id}/unlock` `{pin}` → `{ok: bool}`; a profile without a PIN answers `ok: true`
  - `DELETE /api/profiles/{id}` → 409 for the manager; the deletion itself is Task 8, so this task returns 501 for non-managers until then
- `tests/profiles_fixture.py`: `async def make_profile(session, name="Kid", *, pin=None) -> int` and a `manager_id(session) -> int` helper for every later task's tests.

- [ ] **Step 1: Write the failing tests**

- `test_list_never_exposes_the_pin_hash`: create a profile with PIN `1234`; the response has `has_pin: true` and no key containing `pin_hash`.
- `test_unlock_accepts_the_right_pin_only`: `1234` → `ok: true`; `4321` → `ok: false`.
- `test_pin_must_be_four_to_six_digits`: `123`, `1234567`, `12a4` → 422; `123456` → 201.
- `test_avatar_must_be_a_known_key`: `avatar-99` → 422.
- `test_manager_cannot_be_deleted`: 409.
- `test_unknown_profile_header_is_refused`: `GET /api/series` with `X-Soshuhen-Profile: 999999` → 400; with `abc` → 400; `GET /api/reader/chapters/{any}/pages/0` with `999999` → 400.
- `test_no_header_is_the_manager`: a route echoing `current_profile` (use `GET /api/profiles/current`, which returns `{id, is_manager}` — add it) answers the manager's id.

- [ ] **Step 2: Run to verify they fail**

Run: `... pytest tests/test_profiles_api.py -q` → FAIL (404s).

- [ ] **Step 3: Implement `app/profiles.py`, `current_profile`, `routes_profiles.py`**

`current_profile` is applied app-wide via `dependencies=[Depends(current_profile)]` on the app, so the 400 reaches routes that do not otherwise ask for a profile.

- [ ] **Step 4: Run to verify they pass, plus `tests/test_api.py`**

- [ ] **Step 5: Commit**

```bash
git add backend/app/profiles.py backend/app/api/deps.py backend/app/api/routes_profiles.py backend/app/api/main.py backend/tests/profiles_fixture.py backend/tests/test_profiles_api.py
git commit -m "feat(profiles): profile API and the request's profile"
```

---

### Task 3: Credentials per profile

**Files:**
- Modify: `backend/app/providers/tokens.py`, `backend/app/api/routes_auth.py`, `backend/app/api/routes_profiles.py`, `backend/app/api/routes_settings.py`, `backend/app/api/routes_health.py`, every caller of `access_token_for` / `keyed_providers` (`handlers/status_write.py`, `progress_write.py`, `notes_write.py`, `progress_push.py`, `list_sync.py`, `list_write.py`, `media_enrich.py`, `api/routes_discovery.py`, `worker/main.py`)
- Test: `backend/tests/test_profile_credentials.py`

**Interfaces:**
- Consumes: `Profile`, `manager`, `of_job` (Task 2).
- Produces in `tokens.py`:
  - `keyed_providers(profile: Profile) -> list[str]`: today's list for the manager, `[]` for anyone else.
  - `store_token(session, profile_id: int, provider, *, access_token, refresh_token, expires_in, account_name=None)`, conflicting on `(profile_id, provider)`.
  - `access_token_for(session, profile: Profile, provider) -> str`: `static_credential()` only when `profile.is_manager`; otherwise the stored row; `NotConnected` messages unchanged.
- Callers that are manager-only (`progress_push`, `list_write`, `media_enrich`, `routes_discovery`, `anime_list_sync`) pass `await manager(session)`. The others get their profile in Tasks 4 and 5; here pass `await of_job(session, ctx.payload)`.
- Produces HTTP:
  - `GET /api/auth/{provider}/start?profile_id=N` (optional; absent = manager): the OAuth state JSON gains `"profile_id"`; the callback stores the token on it, then redirects to `/settings?connected={provider}&profile={id}`.
  - `DELETE /api/auth/{provider}` disconnects for the request's profile.
  - `GET /api/profiles/{id}/connections` → `[{provider, connected, account_name, uses_oauth}]` for providers whose source `syncs`.
  - `PUT /api/profiles/{id}/credentials/{provider}` `{key}`: stores a key as `access_token` for a provider with `uses_oauth = false`; 400 for an OAuth provider; 400 for the manager (whose key lives in the environment).

- [ ] **Step 1: Write the failing tests**

- `test_static_key_answers_for_the_manager_only`: with `MANGABAKA_API_KEY` set (monkeypatch settings), `access_token_for(manager, MANGABAKA)` is the env key; for a second profile with no row it raises `NotConnected`; after `PUT /credentials/mangabaka {"key":"k2"}` it returns `"k2"`.
- `test_tokens_are_kept_apart`: `store_token` for both profiles on `anilist`; each `access_token_for` returns its own.
- `test_oauth_state_carries_the_profile`: `start?profile_id=<kid>` stores state whose JSON has the kid's id; a callback with a mocked `exchange_code` stores the token under the kid and leaves the manager's row untouched.
- `test_disconnect_is_per_profile`: `DELETE /api/auth/anilist` with the kid's header removes only the kid's row.

- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run these tests and the full suite**
- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/tokens.py backend/app/api/routes_auth.py backend/app/api/routes_profiles.py backend/app/api/routes_settings.py backend/app/api/routes_health.py backend/app/handlers backend/app/api/routes_discovery.py backend/app/worker/main.py backend/tests/test_profile_credentials.py
git commit -m "feat(profiles): list credentials per profile"
```

---

### Task 4: List sync per profile

**Files:**
- Modify: `backend/app/handlers/list_sync.py`, `backend/app/worker/main.py`, the route that enqueues a manual sync (grep `JobType.LIST_SYNC` in `app/api/`)
- Test: `backend/tests/test_list_sync_profiles.py`

**Interfaces:**
- Consumes: `of_job`, `access_token_for(session, profile, provider)`.
- Payload: `{"provider": ..., "profile_id": int}`; dedupe `list_sync:{profile_id}:{provider}`.
- `skip_removed(session, profile_id: int, dto) -> bool`, `upsert_entry(session, profile_id, dto, series_id)`, `upsert_entry_status(session, profile_id, dto, series_id)` conflict on `(profile_id, provider, provider_media_id)`.
- `existing_series_for_entry(session, dto)` stays **across all profiles** (any profile's entry with the same provider id names the series) — that is the join that keeps one download per title.
- `carry_local_progress(ctx, profile_id: int)` only pairs entries of the same profile; its enqueued `progress_write` carries `profile_id` and dedupe `progress_write:{profile_id}:{series_id}`.
- `worker.main.enqueue_list_sync()` enqueues one job per `(profile, provider)` where the provider `syncs` and the profile is connected (a stored token, or the manager with a static credential).

- [ ] **Step 1: Write the failing tests** (mock `get_source(provider).fetch_list`)

- `test_same_title_on_two_profiles_shares_one_series`: owner's sync and kid's sync both return AniList id `42`; one `series`, two `list_entry` rows with each profile's own `user_progress_chapter`.
- `test_a_removal_tombstone_is_per_profile`: a `removed_entry` for the owner on AniList `42` skips it for the owner and not for the kid.
- `test_cron_enqueues_per_connected_profile`: owner has an AniList token, kid has an AniList token, kid has no MAL token; `enqueue_list_sync()` creates `list_sync` jobs for `(owner, anilist)`, `(kid, anilist)`, and none for `(kid, mal)`.
- `test_local_progress_carries_within_a_profile_only`: owner's local entry at 10 and kid's AniList entry at 3 on the same series enqueue nothing.

- [ ] **Step 2–4:** run → fail, implement, run this file and the suite.
- [ ] **Step 5: Commit** `feat(profiles): sync each profile's lists into the shared library`

---

### Task 5: List writes and progress history per profile

**Files:**
- Modify: `backend/app/handlers/progress_write.py`, `status_write.py`, `notes_write.py`, `progress_events.py`, `backend/app/api/progress_queue.py`, `backend/app/api/routes_series.py` (`/progress`, `/status`, `/status` bulk, `/notes`, `/track-local`)
- Test: `backend/tests/test_list_write_profiles.py`

**Interfaces:**
- Consumes: `CurrentProfile`, `of_job`, `keyed_providers(profile)`.
- `progress_bounds(session, series_id, profile_id) -> Bounds`; `queue_progress_write(session, series_id, chapter, *, profile_id, source, read_at)`; dedupe `progress_write:{profile_id}:{series_id}`; likewise `status_write:{profile_id}:{series_id}`, `notes_write:{profile_id}:{series_id}`.
- `progress_events.furthest_read(session, series_id, profile_id)`, `progress_events.record(session, series_id, *, profile_id, before, chapter, source, at)`.
- Each handler selects `list_entry e where e.series_id = :series_id and e.profile_id = :profile_id`, joining `provider_token t on t.provider = e.provider and t.profile_id = e.profile_id`.
- `newest_requested` / `latest_requested` match on both `series_id` and `profile_id` in the payload.
- `/track-local` creates the local entry for the request's profile.

- [ ] **Step 1: Write the failing tests**

- `test_kid_progress_reaches_kid_lists_only`: both profiles hold AniList entries on one series; `POST /api/series/{id}/progress {"chapter": 5}` with the kid's header; run the job with a mocked `push_progress`; it was called once, with the kid's token; the owner's `user_progress_chapter` is unchanged; one `progress_event` with the kid's `profile_id`.
- `test_two_profiles_queue_separate_writes`: progress from both profiles on one series makes two pending jobs, not one.
- `test_a_job_from_before_the_upgrade_runs_as_the_manager`: enqueue `progress_write` with `{"series_id", "chapter"}` only and dedupe `progress_write:{series_id}`; it pushes with the owner's token.
- `test_status_write_is_per_profile`: same shape as the first test for `/status`.

- [ ] **Step 2–4:** run → fail, implement, run this file and the suite.
- [ ] **Step 5: Commit** `feat(profiles): write progress, status and notes to the requesting profile's lists`

---

### Task 6: Reader state per profile, and Komga for the manager only

**Files:**
- Modify: `backend/app/api/reader_service.py` (`save_position`, `position_in`, `resume`, `effective_prefs`, `save_prefs`, `prose_position`), `backend/app/api/routes_reader.py` (every route above plus `complete`, `complete_volume`), `backend/app/api/routes_series.py` (`/chapters` bookmark flag, `PUT .../bookmark`), `backend/app/api/reading_recency.py`
- Test: `backend/tests/test_reader_profiles.py`

**Interfaces:**
- Every listed `reader_service` function gains `profile_id: int` after `session`. `save_defaults` and prose prefs stay global (they are `setting` rows; a per-profile default is a follow-up).
- `/chapters` reports `bookmarked` from `chapter_bookmark` for the request's profile; `PUT .../bookmark` inserts/deletes that profile's row.
- `complete`: queue progress for the request's profile; enqueue `komga_read_progress` **only if** `profile.is_manager`. Response keys unchanged.
- `complete_volume`: for a non-manager return `{"progress_queued": False, "komga_queued": False}` without enqueueing.

- [ ] **Step 1: Write the failing tests**

- `test_positions_are_kept_apart`: save page 3 as the owner and page 9 as the kid on one chapter; `resume` answers each its own.
- `test_bookmarks_are_kept_apart`: the kid's bookmark does not show in the owner's `/chapters`.
- `test_kid_finishing_a_chapter_never_marks_komga`: a chapter with `komga_book_id`; `POST /complete` as the kid → `komga_queued: false`, no `komga_read_progress` job, one `progress_write` with the kid's `profile_id`. As the owner → `komga_queued: true`.
- `test_kid_finishing_a_volume_queues_nothing`.

- [ ] **Step 2–4:** run → fail, implement, run this file, `tests/test_chapter_bookmark.py` and the suite.
- [ ] **Step 5: Commit** `feat(profiles): reading position, preferences and bookmarks per profile`

---

### Task 7: The library each profile sees

**Files:**
- Create: `backend/app/api/library_scope.py`
- Modify: `backend/app/api/routes_series.py` (`LIST_SQL`, `LIST_SQL_ONE`, `list_series`, `series_detail`), `routes_updates.py`, `routes_notifications.py`, `backend/app/notifications.py`, `routes_dashboard.py`, `routes_stats.py`, `reading_frequency.py`, `routes_backup.py` (Mihon export/import)
- Test: `backend/tests/test_library_scope.py`

**Interfaces:**
- `library_scope.IN_LIBRARY`: a SQL fragment over alias `s` and params `:profile_id`, `:is_manager`:
  `exists (select 1 from list_entry le where le.series_id = s.id and le.profile_id = :profile_id) or (:is_manager and not exists (select 1 from list_entry le where le.series_id = s.id))`
- `library_scope.params(profile: Profile) -> dict[str, object]`.
- `GET /api/series?scope=all|own` (default `own`): `own` filters by `IN_LIBRARY`; `all` does not. Both join `list_entry e on e.series_id = s.id and e.profile_id = :profile_id`, so progress, status and `writable` are the requester's. Each row gains `held_by: list[int]` (profile ids with an entry). `GET /api/series/{id}` stays reachable for any id.
- Updates, notifications, dashboard, stats and reading frequency filter by `IN_LIBRARY` and read `progress_event` for the request's profile.
- Notifications: `unread` means no `notification_read` row for the request's profile; `POST .../{id}/read` and `/read-all` insert rows for it. `notifications.record`'s cleanup deletes notifications older than 30 days for which no profile whose library holds the series lacks a `notification_read` row.
- Mihon export reads the request's entries and bookmarks; import writes bookmarks to `chapter_bookmark` for the request's profile.

- [ ] **Step 1: Write the failing tests**

- `test_kid_sees_only_her_lists`: owner-only series A, shared series B, kid-only series C, unlisted imported series D. Kid's `GET /api/series` → {B, C}; owner's → {A, B, D}; owner's `?scope=all` → {A, B, C, D} with C's `held_by == [kid]`.
- `test_progress_shown_is_the_requesters`: B at 10 for the owner, 2 for the kid; each sees their own.
- `test_kid_gets_no_notification_for_an_owner_only_series`.
- `test_reading_a_notification_is_per_profile`: the owner reading it leaves it unread for the kid.
- `test_updates_screen_is_scoped`: a new chapter on A does not appear in the kid's `/api/updates`.

- [ ] **Step 2–4:** run → fail, implement, run this file, `test_dashboard_api.py`, `test_chapter_notifications.py`, `test_backup_api.py` and the suite.
- [ ] **Step 5: Commit** `feat(profiles): scope the library, updates and notifications to the profile`

---

### Task 8: Per-profile removal and deleting a profile

**Files:**
- Modify: `backend/app/series_removal.py`, `backend/app/api/routes_series.py` (`DELETE /api/series`), `backend/app/api/routes_profiles.py` (`DELETE /api/profiles/{id}`)
- Test: `backend/tests/test_removal_profiles.py`

**Interfaces:**
- `remove_series(session, profile_id: int, series_ids: Sequence[int]) -> int`: tombstones and deletes that profile's entries for the ids, then deletes only those `series` rows no `list_entry` of any profile still references. Returns how many series rows went.
- `delete_profile(session, profile_id: int) -> None` in `series_removal.py`: collect the profile's series ids, delete the profile (cascades its rows), then delete the series among those ids that no remaining entry references. Refuses the manager with `ValueError`.
- `DELETE /api/profiles/{id}` → `{"ok": true, "series_removed": n}`; 409 for the manager.

- [ ] **Step 1: Write the failing tests**

- `test_owner_removing_a_shared_series_keeps_it_for_the_kid`: series with a mapping and a chapter, entries for both; owner removes it; the series, mapping and chapter remain; the owner's entry is gone and tombstoned for the owner only.
- `test_removing_a_series_nobody_else_holds_deletes_it`.
- `test_deleting_a_profile_removes_her_series_only`: kid-only series is deleted, shared series and owner-only series remain, kid's tokens/positions/bookmarks are gone.

- [ ] **Step 2–4:** run → fail, implement, run this file, the existing series-removal tests and the suite.
- [ ] **Step 5: Commit** `feat(profiles): removal and profile deletion respect other profiles`

---

### Task 9: Manager-only background work

**Files:**
- Modify: `backend/app/worker/main.py` (`enqueue_progress_push`, `enqueue_anime_list_sync`), `backend/app/handlers/progress_push.py` (`entries_of`), `backend/app/handlers/komga_scan.py` (read marks from list progress), `backend/app/handlers/suggest_build.py`
- Test: `backend/tests/test_manager_only_jobs.py`

**Interfaces:**
- Each of these reads `list_entry` / `provider_token` with `profile_id = (await manager(session)).id`.

- [ ] **Step 1: Write the failing tests**

- `test_progress_push_moves_only_the_managers_lists`: Komga reports chapter 7 read on a shared series; the kid's entry at 2 is untouched; only the owner's push is called.
- `test_komga_scan_marks_read_from_the_managers_progress`: owner at 3, kid at 20; books up to 3 are marked read, not up to 20.
- `test_progress_push_cron_ignores_kid_only_series`.

- [ ] **Step 2–4:** run → fail, implement, run this file, `test_komga_list_progress.py` and the suite.
- [ ] **Step 5: Commit** `feat(profiles): keep Komga and discovery on the managing profile`

---

### Task 10: Documentation

**Files:**
- Modify: `docs/data-model.md` (new tables and keys, `chapter.bookmarked` and `notification.read_at` moved), `docs/configuration.md` (a "Profiles" section: what a profile owns, the header, that the PIN prevents a wrong tap and is not access control, linking to "The stack has no authentication of its own"), `docs/features.md` (profiles), `docs/architecture.md` (jobs carry `profile_id`; which jobs are manager-only), `CLAUDE.md` (one paragraph under Data model: per-person tables carry `profile_id`; `existing_series_for_entry` is deliberately cross-profile)

- [ ] **Step 1: Write the docs.** Every claim must match the code from Tasks 1–9; check each table and key name against `models.py`.
- [ ] **Step 2: Run the whole suite and ruff once more**

Run: `... pytest tests -q` and `.venv/bin/python -m ruff check app/ tests/` → both clean.

- [ ] **Step 3: Commit** `docs(profiles): document profiles and what each one owns`
