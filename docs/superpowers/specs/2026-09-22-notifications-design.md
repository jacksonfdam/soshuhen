# Notifications: an inbox, and a push for the one event worth interrupting

**Status:** design, awaiting review
**Date:** 2026-09-22

## What this is

Two halves that share one store.

An **inbox** inside the interface: a durable record of what the pipeline did that a person would
want to know about — a download that gave up, a provider token about to expire, a sync that broke.
Today those facts exist only as job rows, and the only way to learn one is to open Downloads and
read the queue.

A **browser push** for the single event that justifies interrupting someone: a new chapter is
available for a series they read. It reaches them with the tab closed.

The inbox holds everything. Push is a delivery channel over a subset of it, not a second system.

## What it is not

Not a replacement for the job queue or its log. `job` and `job_event` stay exactly as they are: they
record what ran, and this records what is worth telling. A handler writing a notification is making
an editorial claim — *a person would want to know this* — and most job activity does not qualify.

Not a general event bus. Nothing subscribes to notifications except the interface and the pusher.

## The constraint that shaped the delivery

**Web Push requires a secure context.** A service worker will not register over plain HTTP except on
`localhost`. The stack serves `http://localhost:8080`, so push works on the machine running it and
nowhere else: from a phone the address is `http://192.168.x.x`, and the browser refuses.

This was stated before the design was accepted, and accepted as it is. Push covers the desk, not the
phone. A second delivery — ntfy, Gotify, a webhook — can be added later against the same
`notification` rows without touching anything built here; the store is deliberately not
push-shaped.

## Data model

### `notification`

| column | type | why |
|---|---|---|
| `id` | bigserial | |
| `kind` | varchar(40) | `chapter_available`, `job_failed`, `token_expiring`, `sync_failed` |
| `title` | varchar(300) | one line, already written for a person |
| `body` | text | nullable; the detail |
| `series_id` | bigint null | `on delete cascade` — a removed series takes its notices with it |
| `meta` | jsonb | `{"chapters": 3, "job_id": 91}` — what the click needs |
| `created_at` | timestamptz | |
| `read_at` | timestamptz null | null is unread |

Indexes: `(read_at, created_at desc)` for the unread count and the list.

Handlers write rows. Nothing else does.

### `push_subscription`

| column | type | why |
|---|---|---|
| `id` | bigserial | |
| `endpoint` | text unique | the browser's own push URL; unique is what makes re-subscribing idempotent |
| `p256dh` | text | |
| `auth` | text | |
| `created_at` | timestamptz | |
| `last_ok_at` | timestamptz null | when a send last succeeded |

A send answering 404 or 410 deletes the row. That is the only signal a browser gives that a
subscription is dead, and keeping it means retrying a dead endpoint forever.

## What "a series I follow" means

`series.auto_download` **or** a `list_entry` with status `reading`.

`auto_download` alone was the first instinct and the data refuses it: it is on for 7 series, while 33
more are being read without it. Following is about interest, and `auto_download` is about whether
the machine may fetch without asking — two different questions that happen to overlap.

## Recognising a new chapter

`chapter_discover.upsert_chapters` already does `insert … on conflict (series_id, number) do update`.
It discards which rows were new; `returning (xmax = 0) as inserted` recovers it for free.

Two rules keep this honest, and both come from the real data:

**One notification per series per run, not per chapter.** On 2026-09-19 the pipeline discovered 3,247
chapters in a day. A notification each would be thousands of interruptions. The row reads
*"Dandadan — 3 new chapters"*, with the count in `meta`.

**A series discovering chapters for the first time notifies nothing.** The first run after a mapping
is confirmed learns the whole backlog — hundreds of rows — and that is the system finding out what
exists, not a chapter being released. The test is whether the series had any chapter row before this
run.

## Delivery

`pywebpush`, called from a `push_send` job so a slow or dead push service cannot hold up the
discovery that produced it. The fetch lane runs it; it writes no archives.

**VAPID keys are generated on first use and stored in `setting`.** The alternative — environment
variables and an `openssl` command in the documentation — makes a self-hosted install fail until
someone reads a manual, to protect a key that lives in the same database as the provider tokens
already do.

The service worker ships as `frontend/public/sw.js` so it is served from the root and its scope
covers the whole app. Subscription happens behind an explicit button in Settings, because a browser
permission prompt fired on page load is the pattern every guide tells you not to build.

## The interface

A bell in the shell with the unread count, using the badge the nav already has. It opens a panel
listing the unread first, each row linking to what it is about — a series, or Downloads for a
failure. Marking one read, and marking all read, are the only two actions.

New notifications arrive over the SSE stream that already exists at `/api/events`, as a new event
type. Nothing polls; that is a rule of this codebase and this is not the exception.

## Retention

A daily job deletes read notifications older than 30 days and any notification older than 180 days.
An inbox nobody prunes becomes a table nobody reads.

## Testing

- `upsert_chapters` returns which rows were inserted, against a real database.
- A series with no prior chapters notifies nothing; the same series on its second run notifies once.
- Forty new chapters across three series produce three notifications, not forty.
- A series that is neither `auto_download` nor `reading` produces none.
- A push answering 410 deletes the subscription; one answering 201 sets `last_ok_at`.
- The unread count excludes read rows, and marking all read empties it.

## Open question for review

Whether `token_expiring` belongs here at all. MyAnimeList tokens last an hour and are refreshed
automatically; the notification is only worth writing when a refresh has actually failed, which is
already a `sync_failed`. It is listed as a kind above and may be dropped without changing anything
else.
