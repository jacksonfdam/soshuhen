# New Chapter Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tell the user when a source publishes new chapters, J-Novel Club volumes or J-Novel Club
parts. The news lands in a persistent bell in the header and, when a tab is open in the background,
in a desktop notification from the browser's Notification API.

**Architecture:**
- `chapter_discover` and `jnc_library_sync` detect the rows they actually inserted or grew.
- Both call one helper, `app/notifications.py::record`. It writes a `notification` row and sends
  `pg_notify('jobs', {"event": "notification.new", ...})` inside the handler's own transaction.
- The browser hears the event over the existing `/api/events` SSE stream and re-reads
  `GET /api/notifications`.
- When the tab is hidden, the browser also raises `new Notification(...)`.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, Alembic, Postgres 17, pytest-asyncio; React 19,
react-router 7, Tailwind 4, TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-16-new-chapter-notifications-design.md`

## Global Constraints

- No external resource: no Web Push, no service worker, no new npm or Python dependency.
- `kind` is one of `chapters`, `volumes`, `parts`.
- One notification per series per discovery run. For J-Novel Club parts, one per volume that grew.
- The first discovery or first sync of a series records nothing.
- A J-Novel Club pre-order is not news. It records `volumes` only once it is `owned`.
- Read notifications older than 30 days are deleted inside `record`. Unread ones are kept at any age.
- `GET /api/notifications` defaults to `limit=30` and caps it at 100.
- The desktop notification `tag` is `'soshuhen-' + id`. It is shown only when
  `document.visibilityState !== 'visible'`.
- The desktop switch lives in `localStorage` under the key `soshuhen.desktopNotifications`. Every
  read and write is wrapped in `try/catch`, and it defaults to on.
- UI copy, verbatim:
  - Panel title and header action: "Notifications", "Mark all as read".
  - Permission footer: "Enable desktop notifications", "Desktop notifications",
    "Blocked in your browser's site settings".
  - `chapters`: "1 new chapter (130)", "3 new chapters (128–130)".
  - `volumes`: "Volume 4 available", "Volumes 4–5 available".
  - `parts`: "Volume 3: part 6", "Volume 3: parts 5–6".
  - Ranges use an en dash `–`.
- Repository rules:
  - Colours and sizes come only from `frontend/tailwind.config.ts`.
  - Every new class is confirmed by `grep` in `frontend/dist/`.
  - Feature folders never import each other.
  - Only `handlers/` and API routes write.
  - `cast(:x as text) is null` for nullable parameters.
  - Comments explain why, never what.
- Commits in English, with no assistant attribution of any kind.

## Review Focus

1. **More unread than the page holds.** With 45 unread and `limit=30`, `unread_count` must say 45,
   not 30. Pinned in Task 4.
2. **Fractional chapter numbers.** 128.5 must read as "128.5", not "128.50" or "128.5000". The API
   serves numbers as JSON numbers and the panel formats them with `formatChapter`. Pinned in Tasks 4
   and 6.
3. **A J-Novel Club volume whose part range was unknown last sync.** `last_part` going from null to
   216 is not "new parts", because the old value is unknown. Pinned in Task 3.
4. **A volume skipped for `IntegrityError`.** It contributes nothing to any notification. Pinned in
   Task 3.
5. **A desktop notification clicked while the panel is open, or from another tab.** The click
   focuses the window, navigates client-side and marks the item read exactly once. Checked by hand
   in Task 6.

---

### Task 1: `notification` table, model and `record` helper

**Files:**
- Create: `backend/alembic/versions/0025_notification.py`
- Modify: `backend/app/enums.py` (add `NotificationKind` after `ChapterState`)
- Modify: `backend/app/models.py` (add `Notification` after `JobEvent`)
- Create: `backend/app/notifications.py`
- Test: `backend/tests/test_notifications.py`
- Docs: `docs/data-model.md` (new `notification` section after `job_event`)

**Interfaces:**
- Produces:
  - `NotificationKind(StrEnum)`: `CHAPTERS = "chapters"`, `VOLUMES = "volumes"`, `PARTS = "parts"`.
  - `app.notifications.EVENT = "notification.new"`.
  - `app.notifications.RETENTION = timedelta(days=30)`.
  - The helper:
    ```python
    async def record(
        session: AsyncSession,
        series_id: int,
        kind: NotificationKind,
        numbers: Sequence[Decimal],
        *,
        volume_number: Decimal | None = None,
    ) -> int | None
    ```
    It returns the new row id, or `None` when `numbers` is empty.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_notifications.py`

  Use the `clean` fixture style of `tests/test_chapter_expiry.py`, truncating
  `series, notification restart identity cascade`. Use the `heard` fixture style of
  `tests/test_source_reload.py`, listening on `app.queue.repo.NOTIFY_CHANNEL`.

  ```python
  async def test_nothing_new_records_nothing():
      assert await record(session, series_id, NotificationKind.CHAPTERS, []) is None
      # select count(*) from notification == 0

  async def test_a_run_is_one_row_with_its_range():
      nid = await record(session, series_id, NotificationKind.CHAPTERS,
                         [Decimal(130), Decimal(128), Decimal(129)])
      # row: kind 'chapters', count 3, first_number 128.00, last_number 130.00,
      #      volume_number None, read_at None

  async def test_parts_carry_their_volume():
      await record(session, series_id, NotificationKind.PARTS, [Decimal(5), Decimal(6)],
                   volume_number=Decimal(3))
      # volume_number == Decimal("3.00")

  async def test_the_event_leaves_only_on_commit(heard):
      await record(...)
      assert heard.empty()          # before commit
      await session.commit()
      payload = json.loads(await asyncio.wait_for(heard.get(), 2))
      assert payload["event"] == "notification.new"
      assert payload["notification_id"] == nid
      assert payload["series_id"] == series_id
      assert payload["kind"] == "chapters"

  async def test_old_read_rows_are_pruned_and_unread_kept():
      # Seed three rows by SQL:
      #   read 31 days ago, created 40 days ago   -> gone after the next record()
      #   read 2 days ago                         -> kept
      #   unread, created 400 days ago            -> kept
  ```

- [ ] **Step 2: Run them and see them fail**

  Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_notifications.py -q`

  Expected: an ImportError on `app.notifications`.

- [ ] **Step 3: Write migration `0025_notification`**

  - `revision = "0025_notification"`, `down_revision = "0024_list_entry_volumes"`.
  - Columns exactly as the spec's table:
    - `id` BigInteger PK.
    - `series_id` Integer, FK `series.id` with `ondelete="CASCADE"`, not null.
    - `kind` String(10), not null.
    - `count` Integer, not null.
    - `first_number` and `last_number` Numeric(8,2), not null.
    - `volume_number` Numeric(8,2), null.
    - `created_at` timestamptz, not null, `server_default=sa.text("now()")`.
    - `read_at` timestamptz, null.
  - Indexes:
    - `ix_notification_created` on `created_at desc`.
    - Partial `ix_notification_unread` on `created_at` with `postgresql_where=sa.text("read_at is null")`.
  - `downgrade` drops the table.
  - Add the matching `Notification` ORM class to `models.py`.

- [ ] **Step 4: Implement `record`** in `backend/app/notifications.py`

  - Insert the row with `count = len(numbers)`, `first_number = min`, `last_number = max`.
  - Then `delete from notification where read_at < now() - interval '30 days'`.
  - Then `pg_notify` on `repo.NOTIFY_CHANNEL` with
    `{"event": EVENT, "notification_id", "series_id", "kind", "ts"}`. Use `json.dumps`, as
    `notify_job` does.
  - The module docstring says why pruning lives here: there is no maintenance cron, and the only
    writer of this table is already running.
  - Do not commit. The handler owns the transaction.

- [ ] **Step 5: Run the tests and see them pass**

  Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_notifications.py tests/test_migration_chain.py -q`

  Expected: all pass, with a single migration head.

- [ ] **Step 6: Document the table** in `docs/data-model.md`

  Cover the columns, what one row means (one series, one run), the 30-day pruning and the cascade.

- [ ] **Step 7: Lint and commit**

  ```bash
  .venv/bin/python -m ruff check app/ tests/
  git add backend/alembic/versions/0025_notification.py backend/app/enums.py backend/app/models.py backend/app/notifications.py backend/tests/test_notifications.py docs/data-model.md
  git commit -m "feat(backend): record new chapter notifications"
  ```

---

### Task 2: `chapter_discover` announces what it inserted

**Files:**
- Modify: `backend/app/handlers/chapter_discover.py:44-68` (`upsert_chapters`) and `:208-216` (`handle`)
- Test: `backend/tests/test_chapter_notifications.py`
- Docs: `docs/jobs.md` (`chapter_discover` section)

**Interfaces:**
- Consumes: `record` and `NotificationKind.CHAPTERS` from Task 1.
- Produces:
  - `upsert_chapters(session, series_id, chapters) -> list[Decimal]`. It returns the numbers of
    the rows this call inserted, not the ones it updated. Existing callers that ignore the return
    value keep working.
  - The announcing helper:
    ```python
    async def announce_new_chapters(
        session: AsyncSession, series_id: int, *, had_chapters: bool, inserted: list[Decimal]
    ) -> int | None
    ```
    It calls `record` only when `had_chapters` is true.

- [ ] **Step 1: Write the failing tests**

  Reuse `_series` and `clean` from `tests/test_chapter_expiry.py`, with `notification` added to
  the truncate.

  ```python
  async def test_upsert_returns_only_inserted_numbers():
      first = await upsert_chapters(s, sid, [ref(1), ref(2)])
      assert first == [Decimal("1.00"), Decimal("2.00")]
      again = await upsert_chapters(s, sid, [ref(1), ref(2), ref(3)])
      assert again == [Decimal("3.00")]

  async def test_first_discovery_records_nothing():
      assert await announce_new_chapters(s, sid, had_chapters=False,
                                         inserted=[Decimal(1), Decimal(2)]) is None

  async def test_later_discovery_records_one_row_per_run():
      await announce_new_chapters(s, sid, had_chapters=True,
                                  inserted=[Decimal(128), Decimal(129), Decimal(130)])
      # one row: count 3, first 128.00, last 130.00, kind 'chapters'

  async def test_fractional_numbers_survive():
      await announce_new_chapters(s, sid, had_chapters=True,
                                  inserted=[Decimal("128.5")])
      # first_number == last_number == Decimal("128.50")
  ```

- [ ] **Step 2: Run them and see them fail**

  Run: `... -m pytest tests/test_chapter_notifications.py -q`

  Expected: an ImportError on `announce_new_chapters`.

- [ ] **Step 3: Implement**

  - Add `returning number, (xmax = 0) as inserted` to the upsert. Collect `number` where `inserted`
    is true, and return the list.
  - Comment on that line: `xmax = 0` holds only for a row this statement created, not one that
    `on conflict` updated.
  - In `handle`, before the upsert, compute
    `had_chapters = exists(select 1 from chapter where series_id = :id)`. After the upsert, call
    `announce_new_chapters`.
  - Comment on `had_chapters`: a newly mapped series would otherwise announce its whole backlog.
  - The handler already runs inside the job's session. Do not add a commit.

- [ ] **Step 4: Run the tests and see them pass**

  Run: `... -m pytest tests/test_chapter_notifications.py tests/test_chapter_expiry.py tests/test_opt_in_downloads.py -q`

  Expected: all pass.

- [ ] **Step 5: Document the change** in `docs/jobs.md`

  Under `chapter_discover`: "records one `chapters` notification for the chapters this run
  inserted, except on a series' first discovery."

- [ ] **Step 6: Lint and commit**

  ```bash
  git add backend/app/handlers/chapter_discover.py backend/tests/test_chapter_notifications.py docs/jobs.md
  git commit -m "feat(backend): announce chapters a discovery inserts"
  ```

---

### Task 3: `jnc_library_sync` announces new volumes and new parts

**Files:**
- Modify: `backend/app/handlers/jnc_library_sync.py` (`handle`, plus one new pure function)
- Test: `backend/tests/test_jnc_library_sync.py` (append)
- Docs: `docs/jobs.md` (`jnc_library_sync` section)

**Interfaces:**
- Consumes: `record`, `NotificationKind.VOLUMES` and `NotificationKind.PARTS` from Task 1.
- Produces: a pure function, unit-tested directly.
  ```python
  @dataclass(frozen=True)
  class VolumeNews:
      new_volume: bool
      new_parts: tuple[Decimal, Decimal] | None   # (first, last), inclusive

  def volume_news(
      *,
      before: tuple[str, Decimal | None] | None,   # (status, last_part) before the upsert, None if absent
      status: str,
      last_part: Decimal | None,
  ) -> VolumeNews
  ```

  Rules, from the spec:
  - `new_volume` is true when `status == "owned"` and either `before is None` or
    `before[0] == "preorder"`.
  - `new_parts` is `(before_last + 1, last_part)` when `before` is not None, `before_last` is not
    None, `last_part` is not None and `last_part > before_last`. Otherwise it is None.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_jnc_library_sync.py`)

  Add `notification` to the module's `clean` truncate.

  ```python
  def test_volume_news():
      assert volume_news(before=None, status="owned", last_part=D(216)).new_volume
      assert not volume_news(before=None, status="preorder", last_part=None).new_volume
      assert volume_news(before=("preorder", None), status="owned", last_part=D(216)).new_volume
      assert not volume_news(before=("owned", D(216)), status="owned", last_part=D(216)).new_volume
      assert volume_news(before=("owned", D(214)), status="owned",
                         last_part=D(216)).new_parts == (D(215), D(216))
      # Review Focus 3: unknown before is not news.
      assert volume_news(before=("owned", None), status="owned", last_part=D(216)).new_parts is None

  async def test_first_sync_of_a_series_records_nothing():
      # _mapped_series + _run(FakeJnc([_owned()])) -> 0 notification rows

  async def test_a_newly_owned_volume_is_announced():
      # Run once with [_owned(16)], then with [_owned(16), _owned(17)]
      # (part_ranges returns no range for 17).
      # -> one row: kind 'volumes', first 17, last 17

  async def test_new_parts_of_a_known_volume_are_announced():
      # Run once with part_ranges {16: (204, 214)}, then with {16: (204, 216)}.
      # -> one row: kind 'parts', first 215, last 216, volume_number 16

  async def test_a_volume_skipped_for_its_number_announces_nothing():
      # Review Focus 4: a second edition with the same number raises IntegrityError
      # on the second run -> no 'volumes' row for it.
  ```

  `FakeJnc.part_ranges` becomes configurable through a constructor argument whose default is
  today's `{16: (204, 216)}`, so existing tests are unchanged.

- [ ] **Step 2: Run them and see them fail**

  Run: `... -m pytest tests/test_jnc_library_sync.py -q`

  Expected: an ImportError on `volume_news`.

- [ ] **Step 3: Implement**

  - Inside the per-slug loop, before the per-volume loop, read the series' existing volumes:
    `select source_volume_id, status, last_part from volume where series_id = :s`. Build a dict.
  - The series' first sync is when that dict is empty: compute nothing for the series.
  - After each successful savepoint, apply `volume_news`:
    - Collect `new_volume` numbers per series.
    - Call `record(..., PARTS, list(range(first, last + 1)), volume_number=volume.number)` for each
      `new_parts`. Integer parts make the range exact; say so in a comment.
  - After the per-volume loop, call `record(..., VOLUMES, numbers)` for the series.
  - All of this happens before the existing `commit`.

- [ ] **Step 4: Run the tests and see them pass**

  Run: `... -m pytest tests/test_jnc_library_sync.py -q`

  Expected: all pass, the old tests included.

- [ ] **Step 5: Document the change** in `docs/jobs.md`

  Under `jnc_library_sync`: new owned volumes and grown part ranges are announced, a pre-order is
  not, and nothing is announced on a series' first sync.

- [ ] **Step 6: Lint and commit**

  ```bash
  git add backend/app/handlers/jnc_library_sync.py backend/tests/test_jnc_library_sync.py docs/jobs.md
  git commit -m "feat(backend): announce new J-Novel Club volumes and parts"
  ```

---

### Task 4: notifications API

**Files:**
- Create: `backend/app/api/routes_notifications.py`
- Modify: `backend/app/api/main.py` (add to the `from app.api import (...)` list and `include_router`, as for `routes_jobs`)
- Test: `backend/tests/test_notifications_api.py`

**Interfaces:**
- Consumes: the `notification` table from Task 1.
- Produces:
  - `GET /api/notifications?limit=30` returns `{"items": [Item], "unread_count": int}`.
  - `Item` fields: `id, series_id, series_title, cover_url, kind, count, first_number,
    last_number, volume_number, created_at, read_at`.
  - The numbers are JSON numbers (`float(Decimal)`) and the timestamps are ISO strings.
  - `series_title` is `series.canonical_title`; `cover_url` is `series.cover_url`.
  - `POST /api/notifications/{id}/read` returns `{"ok": true}`, or 404 when the id is unknown. It is
    idempotent and keeps the first `read_at`.
  - `POST /api/notifications/read-all` returns `{"marked": int}`.

- [ ] **Step 1: Write the failing tests**

  Use the `client` fixture of `tests/test_dashboard_api.py`, and truncate
  `notification, series restart identity cascade`.

  ```python
  async def test_lists_newest_first_with_series_title_and_cover(client): ...
  async def test_fractional_numbers_are_plain_numbers(client):
      # seeded 128.5 -> item["first_number"] == 128.5
  async def test_unread_count_is_not_capped_by_the_page(client):
      # Review Focus 1: 45 unread, GET ?limit=30 -> len(items) == 30, unread_count == 45
  async def test_limit_is_capped_at_100(client):    # ?limit=500 -> 422 or at most 100 items
  async def test_marking_one_read_keeps_its_first_time(client): ...
  async def test_unknown_id_is_404(client): ...
  async def test_read_all_marks_every_unread_row(client):
      # {"marked": n}; unread_count -> 0
  ```

  Declare the limit as `Query(30, ge=1, le=100)`. FastAPI then answers 422 over 100, and the cap
  test asserts 422.

- [ ] **Step 2: Run them and see them fail**

  Run: `... -m pytest tests/test_notifications_api.py -q`

  Expected: 404 on every route.

- [ ] **Step 3: Implement the routes**

  - Use `APIRouter(prefix="/api", tags=["notifications"])` and the `Session` dependency, in the
    style of `routes_jobs.py`.
  - Compute `unread_count` with its own `count(*) where read_at is null`.
  - The routes commit their own updates.

- [ ] **Step 4: Run the tests and see them pass**

  Run: `... -m pytest tests/test_notifications_api.py tests/test_api.py -q`

  Expected: all pass.

- [ ] **Step 5: Lint and commit**

  ```bash
  git add backend/app/api/routes_notifications.py backend/app/api/main.py backend/tests/test_notifications_api.py
  git commit -m "feat(api): list and mark notifications"
  ```

---

### Task 5: frontend data layer and desktop wrapper

**Files:**
- Modify: `frontend/src/lib/api.ts` (types and three calls)
- Modify: `frontend/src/lib/useEvents.ts` (`EVENT_NAMES`; add `notification_id?` and `kind?` to `JobEvent`)
- Create: `frontend/src/lib/desktopNotifications.ts`
- Create: `frontend/src/lib/useNotifications.ts`
- Docs: `docs/architecture.md` ("Live progress": `notification.new` and why it carries only an id)

**Interfaces:**
- Consumes: the Task 4 routes.
- Produces:
  - In `api.ts`:
    ```ts
    export type NotificationKind = 'chapters' | 'volumes' | 'parts'
    export interface AppNotification {
      id: number; series_id: number; series_title: string; cover_url: string | null
      kind: NotificationKind; count: number; first_number: number; last_number: number
      volume_number: number | null; created_at: string; read_at: string | null
    }
    export interface NotificationPage { items: AppNotification[]; unread_count: number }
    api.notifications(): Promise<NotificationPage>
    api.markNotificationRead(id: number): Promise<{ ok: boolean }>
    api.markAllNotificationsRead(): Promise<{ marked: number }>
    ```
    `AppNotification` avoids shadowing the DOM `Notification`.
  - In `desktopNotifications.ts`:
    `supported(): boolean`, `permission(): NotificationPermission | 'unsupported'`,
    `request(): Promise<NotificationPermission>`, `enabled(): boolean`,
    `setEnabled(on: boolean): void`, and
    `show(opts: { id: number; title: string; body: string; icon?: string; onClick: () => void }): void`.
  - In `useNotifications.ts`:
    ```ts
    export function useNotifications(onOpen: (n: AppNotification) => void): {
      page: AsyncData<NotificationPage>
      markRead: (id: number) => void
      markAllRead: () => void
    }
    ```
    `onOpen` is what a desktop click does. The bell passes a function that navigates and marks the
    item read.
  - Also in `useNotifications.ts`: `summary(n: AppNotification): string`, the copy rules from Global
    Constraints, with numbers through `formatChapter`.

- [ ] **Step 1: Add the types and calls** to `api.ts`.

- [ ] **Step 2: Add `'notification.new'` to `EVENT_NAMES`.**

  Comment it with why: the shared stream dispatches only the names listed.

- [ ] **Step 3: Write `desktopNotifications.ts`**

  - `supported()` is `typeof window !== 'undefined' && 'Notification' in window && window.isSecureContext`.
  - `show` returns early unless supported, granted and enabled. It builds
    `new Notification(title, { body, icon, tag: 'soshuhen-' + id })`, and its `onclick` runs
    `window.focus(); onClick(); notification.close()`.
  - Comment on the tag: several tabs replace one another instead of stacking duplicates.

- [ ] **Step 4: Write `useNotifications.ts`**

  - Load with `useAsyncData(api.notifications)`.
  - `useJobEvents`: on `event.event === 'notification.new'`, reload. If
    `document.visibilityState !== 'visible'`, fetch the page once and call `show` for the item whose
    `id === event.notification_id`. Use that fetch's result to `setData` as well, rather than
    fetching twice.
  - `useEventStreamStatus`: when the status changes to `'open'` from `'reconnecting'`, reload. This
    is the "hello" catch-up from the spec. It raises no desktop notifications for what was missed.
  - `markRead` and `markAllRead` update `setData` optimistically (set `read_at`, recompute
    `unread_count`), then call the API, and `reload()` on failure.

- [ ] **Step 5: Typecheck**

  Run (from `frontend/`): `npx tsc -b`

  Expected: no errors.

- [ ] **Step 6: Document the event** in `docs/architecture.md`, under "Live progress".

- [ ] **Step 7: Commit**

  ```bash
  git add frontend/src/lib/api.ts frontend/src/lib/useEvents.ts frontend/src/lib/desktopNotifications.ts frontend/src/lib/useNotifications.ts docs/architecture.md
  git commit -m "feat(web): notification data and desktop notifications"
  ```

---

### Task 6: the bell and its panel

**Files:**
- Modify: `frontend/src/ui/Icon.tsx` (add a `bell` path in the same 24×24 Material style)
- Create: `frontend/src/app/NotificationBell.tsx`
- Modify: `frontend/src/app/AppShell.tsx` (mount it in the right cluster, before "Sync all", around line 155)
- Docs: `docs/features.md` (a "Notifications" section)

**Interfaces:**
- Consumes:
  - `useNotifications` and `summary` from Task 5.
  - `supported`, `permission`, `request`, `enabled` and `setEnabled` from Task 5.
  - `IconButton`, `Badge`, `EmptyState` and `Toggle` from `ui/`.
  - `relativeTime` from `lib/format.ts`, and `useNavigate`.
- Produces: `export function NotificationBell(): JSX.Element`.

- [ ] **Step 1: Add the bell glyph**

  Use the Material "notifications" path:
  `M12 22a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4a1.5 1.5 0 0 0-3 0v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1z`

- [ ] **Step 2: Build `NotificationBell.tsx`**

  - **Button:** a `relative` wrapper holding `IconButton icon="bell" label="Notifications"`, with
    `aria-expanded`. A `Badge tone="error"` sits absolutely at the top-right only when
    `unread_count > 0`.
  - **Panel:** an absolutely positioned card below the button, in the existing surface tokens
    (`bg-surface-container`, `border-white/5`, the radius and shadow tokens already used by
    `DetailPanel` and `ConfirmDialog`).
    - It scrolls vertically past a max height taken from an existing token.
    - It closes on Esc, on a `mousedown` outside its ref, and on a route change (`useLocation`
      effect).
  - **Header:** "Notifications", and a "Mark all as read" text button, disabled when
    `unread_count === 0`.
  - **Items:** each item is a button.
    - Content: cover thumbnail (an `Icon book` placeholder when `cover_url` is null), the series
      title, `summary(n)` and `relativeTime(n.created_at)`.
    - Unread items have a primary-tinted background and a dot.
    - A click calls `markRead(n.id)` if unread, then `navigate('/series/' + n.series_id)`.
  - **Empty:** `EmptyState` with "No notifications yet".
  - **Error:** with no data, one line from `page.error`. With data and an error, keep the list.
  - **Footer:** the four permission states, exactly as in Global Constraints. After `request()`
    resolves, re-render so the footer reflects the new permission.
  - **Wiring:** pass `useNotifications` an `onOpen` that runs `navigate` and `markRead`.

- [ ] **Step 3: Mount it in `AppShell.tsx`**, in the right-hand cluster before the "Sync all" button.

  It must be visible at every breakpoint, because the header itself is.

- [ ] **Step 4: Build and confirm every new class exists**

  From `frontend/`:

  ```bash
  npm run build
  ```

  Then, for each class in `NotificationBell.tsx`, run `grep -o '<class>' dist/assets/*.css`.

  Expected: the build is clean, and every class is found. Fix any that is not (see CLAUDE.md:
  interpolated names, `font-*` vs `text-*` scales).

- [ ] **Step 5: Verify by hand at `https://soshuhen.test`**

  1. Rebuild the stack, then confirm every service is up:
     ```bash
     docker compose build api && docker compose up -d --force-recreate api worker worker-download web
     docker compose ps
     ```
  2. Open the bell. Click "Enable desktop notifications" and grant the permission.
  3. For a mapped series that has chapters:
     ```sql
     delete from chapter where series_id = X and number = (select max(number) from chapter where series_id = X)
     ```
     Then enqueue its discovery. There is no route for that; use the queue directly:
     ```bash
     docker compose exec api python -c "import asyncio; from app.db import get_sessionmaker; from app.queue import repo; from app.enums import JobType
     async def m():
         async with get_sessionmaker()() as s:
             await repo.enqueue(s, JobType.CHAPTER_DISCOVER, {'series_id': X}, series_id=X, priority=0); await s.commit()
     asyncio.run(m())"
     ```
  4. Switch to another tab. A desktop notification should read "1 new chapter (N)".
  5. Click it. The Soshuhen tab gains focus, lands on `/series/X`, and the badge drops by one.
     (Review Focus 5.)
  6. Repeat with the tab in front. Only the badge changes.
  7. Turn the toggle off and repeat in the background. There is no desktop notification, but the
     badge still counts.
  8. "Mark all as read" clears the badge.

- [ ] **Step 6: Document the feature** in `docs/features.md`

  Cover the bell, what counts as new (chapters, owned volumes, parts, not a series' first
  discovery), desktop notifications, the HTTPS or `localhost` requirement, "a tab must be open",
  and the per-browser toggle.

- [ ] **Step 7: Commit**

  ```bash
  git add frontend/src/ui/Icon.tsx frontend/src/app/NotificationBell.tsx frontend/src/app/AppShell.tsx docs/features.md
  git commit -m "feat(web): notification bell with desktop notifications"
  ```

---

### Task 7: full suite

- [ ] **Step 1: Run every backend check**

  From `backend/`:

  ```bash
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
  .venv/bin/python -m ruff check app/ tests/
  ```

  Expected: all green, against a fresh container if this runs in a worktree (see CLAUDE.md).

- [ ] **Step 2: Confirm the frontend build** from `frontend/` with `npm run build`.

  Expected: clean.
