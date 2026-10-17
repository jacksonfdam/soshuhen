# New chapter notifications

Date: 2026-10-16
Status: approved design, awaiting implementation plan

## Goal

When a source publishes something new for a series the user follows, the user hears about it
without opening the library to check. Two channels carry the news:

- a **notification area**: a bell in the top bar with an unread count and a dropdown panel, kept in
  the database so nothing is lost while no browser is open;
- **desktop notifications** through the browser's own
  [Notification API](https://developer.mozilla.org/en-US/docs/Web/API/Notification), with no push
  service, no third-party library and no other external resource.

## Decisions taken with the user

| Question | Decision |
|---|---|
| What counts as "new" | Discovered at the source: a chapter `chapter_discover` had never seen, whether or not it is ever downloaded. Not "ready to read". |
| J-Novel Club | Included: newly available volumes **and** new parts of a volume already known. |
| Granularity | One notification per series per discovery run, e.g. "Frieren: 3 new chapters (128–130)". |
| Notification area | Bell in the header with an unread badge and a dropdown panel. No `/notifications` route. |
| Approach | **A:** the handlers detect inserted rows and write a `notification` table in the same transaction, then announce it on the existing SSE stream. Rejected: a Postgres trigger (B: per-row, cannot aggregate a run, hides the rule from the tests) and deriving from `discovered_at` with no table (C: no per-item read state, cannot separate runs, mixes in the first import). |
| Retention | Read notifications older than 30 days are deleted. Unread ones stay until read. |

## Constraints

- **Secure context.** The Notification API exists only on HTTPS or `localhost`. The installation is
  served at `https://soshuhen.test` by the user's local HTTPS proxy, so it is available. Where it is
  not (`'Notification' in window && window.isSecureContext` is false), the bell still works and the
  desktop controls are hidden. That is a degradation, not an error.
- **A tab must be open.** Without Web Push, which needs the browser vendor's push service, a desktop
  notification can only be raised by an open Soshuhen tab, foreground or background. With no tab
  open, the notification waits in the bell.
- **Nothing polls.** New notifications reach the browser over the existing `pg_notify('jobs')` →
  `/api/events` SSE path (`docs/architecture.md`, "Live progress").
- **Only `handlers/` writes.** Detection lives in the two handlers that insert the rows, through
  one shared helper.

## Backend

### Table `notification` (migration `0025_notification`)

| Column | Type | Notes |
|---|---|---|
| `id` | bigint, PK | |
| `series_id` | int, FK → `series.id`, `ondelete cascade`, not null | |
| `kind` | varchar(10), not null | `chapters`, `volumes` or `parts` |
| `count` | int, not null | how many items this run found |
| `first_number` | numeric(8,2), not null | lowest new number in the run |
| `last_number` | numeric(8,2), not null | highest new number in the run |
| `volume_number` | numeric(8,2), null | `parts` only: the volume the parts belong to |
| `created_at` | timestamptz, not null, default `now()` | |
| `read_at` | timestamptz, null | null means unread |

Index `ix_notification_unread` on `created_at` where `read_at is null`, and one on `created_at desc`
for the panel. The series title and cover are not copied in: they come from `series` at read time,
so a renamed series reads correctly in old notifications.

`kind` gets a `NotificationKind` StrEnum in `app/enums.py`, next to the other states.

### `app/notifications.py`

One helper both handlers call:

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

- Returns `None` and writes nothing when `numbers` is empty.
- Inserts one row with `count = len(numbers)`, `first_number = min`, `last_number = max`.
- Deletes read notifications older than 30 days in the same statement batch. There is no
  maintenance cron to hang this on, and a handler that is already writing the table is the
  cheapest place to keep it bounded.
- Calls `pg_notify('jobs', ...)` with
  `{"event": "notification.new", "notification_id", "series_id", "kind", "ts"}`. The payload is a
  nudge, not the content: the browser re-reads the list from the API. `pg_notify` is
  transactional, so the event leaves only if the run commits.

`record` takes no decision about whether a run deserves a notification. The handlers decide, which
keeps the first-discovery rule next to the code that knows what "first" means.

### `chapter_discover`

- `upsert_chapters` gains `returning number, (xmax = 0) as inserted` and returns the numbers of the
  rows it inserted. `xmax = 0` is true only for a row this statement created, not one it updated
  through `on conflict`.
- Before the upsert, `handle` counts the series' existing chapters. **If it was 0, this is the
  series' first discovery: nothing is recorded.** A newly mapped series would otherwise announce
  its entire backlog as new.
- Otherwise `record(session, series_id, NotificationKind.CHAPTERS, inserted)`.

### `jnc_library_sync`

Before the per-series loop, read the series' existing volumes as
`source_volume_id → (status, last_part)`. Then, for each upserted volume:

- **New volume.** The volume was absent before and its status is `owned`, or it was `preorder` and
  is now `owned`. Its number joins that series' `volumes` list. A pre-order is not yet available,
  so it is not news until it is owned.
- **New parts.** The volume existed before, its old `last_part` was not null, and the new
  `last_part` is greater. Those parts become a `parts` notification for that volume, with
  `first_number = old last_part + 1`, `last_number = new last_part` and `volume_number` set, with
  `count = last_number - first_number + 1`. J-Novel Club numbers parts with whole numbers, so the
  range is exact.
- **First sync of a series.** If the series had no volumes before this run, nothing is recorded.

That makes at most one `volumes` notification per series per run, plus one `parts` notification per
volume that grew. In practice that is one per series, since J-Novel Club releases parts into the
newest volume.

The savepoint per volume stays. The notifications are recorded after the loop, before the existing
`commit`, so a volume skipped for an `IntegrityError` contributes nothing.

### API, `app/api/routes_notifications.py`

| Route | Returns / does |
|---|---|
| `GET /api/notifications?limit=30` | `{items: [...], unread_count}`, newest first. Each item: `id, series_id, series_title, cover_url, kind, count, first_number, last_number, volume_number, created_at, read_at`. `limit` is capped at 100. |
| `POST /api/notifications/{id}/read` | Sets `read_at = now()` if null. 404 for an unknown id. |
| `POST /api/notifications/read-all` | Sets `read_at = now()` on every unread row. Returns the count. |

The read routes write through the API, as the reader's routes already do through
`api/reader_service.py`. That is a user's action, not pipeline work, so it does not belong in a
handler.

## Frontend

### `lib/desktopNotifications.ts`

A thin wrapper over the Notification API, with no React in it:

- `supported()`: `'Notification' in window && window.isSecureContext`.
- `permission()`: `Notification.permission`.
- `request()`: `Notification.requestPermission()`. Called only from a click, because browsers
  ignore or penalise a request with no user gesture.
- `enabled()` / `setEnabled(bool)`: a per-browser switch in `localStorage`, read and written inside
  `try/catch`, default on. It mutes without revoking the system permission.
- `show({id, title, body, icon, onClick})`: `new Notification(title, {body, icon, tag:
  'soshuhen-' + id})`. Its `onclick` calls `window.focus()`, then `onClick`, then `close()`. The
  `tag` makes several open tabs replace one another's notification instead of stacking duplicates.

### `lib/useNotifications.ts`

- Loads `GET /api/notifications` through `useAsyncData`.
- Subscribes with `useJobEvents`. `notification.new` is added to `EVENT_NAMES` in `lib/useEvents.ts`,
  without which the shared `EventSource` never dispatches it.
- On `notification.new`: refreshes the list. If `supported() && permission() === 'granted' &&
  enabled()` **and the tab is not visible** (`document.visibilityState !== 'visible'`), it shows
  the desktop notification for the item named by `notification_id` once the refreshed list
  contains it. A user looking at the page has the badge already.
- On the stream's `hello` after a reconnect: refreshes the list, so the count does not fall behind.
  Notifications that arrived while the stream was down appear in the bell only. They are not raised
  on the desktop after the fact.
- Exposes `items`, `unreadCount`, `markRead(id)` and `markAllRead()`, updating local state
  optimistically and reloading on failure.

### `app/NotificationBell.tsx`

Mounted in the right-hand cluster of the `AppShell` header, beside the "Sync all" button. It lives
in `app/`, not in a feature folder, because it belongs to the shell. Feature folders keep not
importing each other.

- `IconButton` with a new `bell` glyph in `ui/Icon.tsx`, plus a `Badge` showing `unreadCount`. The
  badge is omitted at 0, not shown as "0".
- **Panel:** opens below the button. It closes on Esc, on a click outside and after a navigation.
  - Header: the title "Notifications" and "Mark all as read" (disabled when nothing is unread).
  - List: each item shows the cover, the series title, the summary and a relative time from
    `lib/format.ts`. Unread items are visually distinct. A click navigates to `/series/:id` and
    marks the item read.
  - Summaries:
    - `chapters`: "1 new chapter (130)", or "3 new chapters (128–130)".
    - `volumes`: "Volume 4 available", or "Volumes 4–5 available".
    - `parts`: "Volume 3: part 6", or "Volume 3: parts 5–6".
  - Empty list: `EmptyState`.
  - Footer, by permission state:
    - `default`: a button, "Enable desktop notifications", which calls `request()`.
    - `granted`: a `Toggle`, "Desktop notifications", bound to `enabled()`.
    - `denied`: the text "Blocked in your browser's site settings".
    - unsupported: no footer.
- The desktop notification's `onClick` uses the router's `navigate`, so it stays a client-side
  transition.

Repository rules that apply: every size and colour comes from `tailwind.config.ts`; every new class
is checked in `frontend/dist/` after a build; nothing renders a number the API did not serve.

## Edge cases

- **Atomicity.** `record` runs in the transaction of the upsert that found the rows. A run that
  fails afterwards rolls back the chapters and the notification together, and its retry inserts and
  announces them again. There is never a chapter without its notification, or the reverse.
- **Renumbering sources.** LoLoBun and Novelight number chapters by list position
  (`docs/architecture.md`). An insertion mid-list produces one new number at the end, and the
  notification counts one chapter. That count is right, though the number may name a different
  chapter than the one actually released. This is documented, not handled.
- **A source back after an outage.** It is still one notification per series, with a wider range.
- **A deleted series.** Its notifications go with it, through the cascade.
- **Several tabs.** The shared `tag` gives one desktop notification. The badge updates in every tab.
- **Permission revoked while a tab is open.** `permission()` is read at the moment of showing, never
  cached.

## Testing

Backend, against the throwaway Postgres:

- `upsert_chapters` returns only the inserted numbers; a second identical call returns none.
- The first discovery of a series records nothing.
- A later discovery with three new chapters records one `chapters` row with
  `count = 3, first = 128, last = 130`, and emits `notification.new`.
- JNC: a new owned volume records `volumes`; a pre-order records nothing; a pre-order turning owned
  records `volumes`; a growing `last_part` records `parts` with the right range and
  `volume_number`; the first sync of a series records nothing.
- `record` deletes read rows older than 30 days and keeps unread ones of any age.
- Routes: listing with title and cover, `unread_count`, read, read-all, 404 on an unknown id.

Frontend:

- `npm run build`, then `grep` in `frontend/dist/` for each new class.
- By hand at `https://soshuhen.test`:
  1. Grant the permission from the panel.
  2. Remove a chapter row of a mapped series, and enqueue its `chapter_discover`.
  3. Switch to another tab and see the desktop notification. Click it, and land on the series with
     the item read.
  4. Repeat with the tab in front and see only the badge.

## Documentation

- `docs/features.md`: a section on notifications, covering the bell, desktop notifications, the
  HTTPS requirement and "a tab must be open".
- `docs/data-model.md`: the `notification` table.
- `docs/architecture.md`: `notification.new` in the live progress flow.
- `docs/jobs.md`: what `chapter_discover` and `jnc_library_sync` now record.

## Out of scope

- Web Push and service workers. Both need an external push service.
- Per-series muting, and notifications for downloads, failures or list sync.
- A `/notifications` history page.
