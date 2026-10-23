# Architecture

## Processes

Nine services in `docker-compose.yml`. Seven start with `docker compose up -d`; the last two are
gated behind Compose profiles and start only when asked for by name.

| Service | What it is |
|---|---|
| `postgres` | The only datastore. Domain, queue and history |
| `api` | FastAPI. REST and the SSE stream. Runs migrations on start. Fetches pages from source sites for the reader |
| `worker` | The fetch lane: every job type but the two downloads, plus the cron that feeds them. The only process running the scheduler |
| `worker-download` | The download lane: `download_batch`, `download_chapter`, `volume_download` and `import_files`. The only process that writes archives, and the one that empties the reader cache |
| `web` | Caddy, serving the built interface and proxying `/api` |
| `komga` | The library server, and one reader of several |
| `bootstrap` | One-shot: claims Komga if needed, creates the library, exits |
| `comick` | A second chapter source, built from source. Profile `comick` |
| `flaresolverr` | Headless Chrome, for sites behind a Cloudflare challenge. Profile `flaresolverr` |

Both optional services are expensive to start — one compiles a third-party program, the other is
several hundred megabytes of browser — which is why neither is paid for by someone sourcing
chapters from MangaDex alone:

```bash
docker compose --profile comick --profile flaresolverr up -d
```

**`api`, `worker` and `bootstrap` are the same program with different entrypoints**, and declare the
same `image: soshuhen:local`. Build one and recreate the others, or they run stale code — the
symptom is a job failing with `no handler registered`, which reads as a code bug and is a build bug.

```bash
docker compose build api && docker compose up -d --force-recreate api worker
```

They are separate processes so that restarting the API does not kill a download in flight, and so
the worker can scale independently.

## The reader and the library

The reader reads a chapter from its archive when it is in the library, and otherwise streams it:
`api` asks the source for the page list and the page, writes the page to the `reader-cache` volume
and serves it. When the cache holds every page, `api` queues `download_chapter` with `from_cache`,
and `worker-download` builds the archive from the cache.

So `api` writes the cache and never `/manga`, which stays read-only everywhere but the download
lane. `api` runs as `PUID:PGID` like the download lane, because the lane deletes what `api` wrote.

The reader has one slot of its own per site, in `api`'s process. A download batch holds its slot for
every chapter in it, and a reader queueing behind that would wait minutes for a page; a site sees
at most `per_source_concurrency + 1`.

## Endpoints the Android client uses

The Android client reads on the home network and offline, and talks to nothing but this server.
Four routes exist for it (design: `docs/superpowers/specs/2026-10-20-android-client-design.md`):

- `GET /api/identity` names the app and a stable `instance_id`. `/api/health` answers `ok` like any
  service, so a LAN scan matches on `app`, and the id is how the client finds the same server again
  after DHCP moves it.
- `GET /api/chapters/{id}/archive` serves a chapter's whole CBZ, with `Range` and an `ETag`, so a
  copy cut off by weak Wi-Fi resumes and a rebuilt archive is copied again.
- `GET /api/series/{id}/cover` serves the cover from `reader-cache/covers/`, fetched from the list
  provider once, so nothing on the phone reaches the internet. A failed fetch stores nothing and the
  next request tries again.
- `PUT /api/reader/series/{id}/position` and `POST /api/reader/chapters/{id}/complete` accept an
  optional `read_at`. Reading done offline is replayed later, and without it a morning's position
  would overwrite an evening's and a week of reading would be dated by one replay. A position with
  `read_at` applies only if it is newer than the stored one; the time is clamped to the server's
  `now()` so a fast phone clock cannot win every replay. Requests without it behave as before.

## Module boundaries

```
backend/app/
  providers/   list providers: MyAnimeList, AniList, MangaBaka
  sources/     chapter sources, and the registry built from the site catalogue
  downloader/  page fetching, CBZ writing, ComicInfo
  komga/       the library server client and bootstrap
  reader/      archive pages, the page cache, page lists as JSON
  queue/       enqueue, lease, complete, fail, notify
  handlers/    one per job type; stitches the above together
  api/         routes and SSE
```

**The edges — `providers/`, `sources/`, `downloader/`, `komga/`, `reader/` — are pure.** They take
arguments, return values, and never touch the database. Only `handlers/` writes.

That boundary is what makes the source layer testable at all. A source answers three questions —
which manga match a title, which chapters exist, which pages a chapter has — and the downloader
fetches those pages, verifies each one is really an image, and writes the archive. Both are Python
end to end; there is no external binary in the path.

A source may also state a fourth thing, and only a scrambling site ever does: `Source.descramble`
turns the bytes of one page into the bytes a reader can open. It is concrete and identity by
default, so no other source carries a no-op override, and `fetch_pages` applies it **after**
`_verify_image`, never before — reassembling first would turn an HTML error page into something
that passes for an image. The hook keeps the import direction intact: `sources/` states what to do
to the bytes, `downloader/` does it.

That is not style. It is what lets those four be tested against recorded fixtures with no network and
no Postgres, which is most of the suite. A database call inside a provider breaks that and will be
rejected in review.

**The API is a thin layer.** Business rules live in handlers, not in routes. A route validates,
enqueues or reads, and returns.

## Two deliberate stops

Both exist so nothing leaves over the network without a decision.

1. **`match_search` parks candidates and waits.** A wrong automatic match downloads the wrong manga
   for every future chapter. One click per series, remembered forever, is the cheaper trade.
2. **Downloading waits for an explicit range or for `series.auto_download`.** Confirming a mapping
   says what a series *is*, not that its backlog should be fetched.

Discover follows the same principle: a suggestion is approved by a person, and an unmatched anime
is searched only when asked.

**Do not remove a stop to make something more automatic.** They are the product, not friction in it.

## Comics and prose

`series.kind` routes a series to one kind of source. `match_search` asks the registry only for
sources of the series' kind, and the mapping route rejects with 422 a source of the other kind, so a
novel cannot be mapped to an image site or the reverse. A null kind behaves as `comic`.

The download handlers read the kind once and branch once, at the archive write. A comic goes through
`list_pages`, the reader cache and `write_cbz`. A prose chapter goes through
`ProseSource.fetch_chapter`, fetches its images through the same rate-limited fetcher, and goes to
`write_epub`. Batching, leasing, retries and the `ChapterUnavailable` to `PermanentError` mapping sit
outside the branch and are shared. Prose does not use the reader cache, so the image reader answers
409 for a prose chapter; Komga's own reader is where a novel is read.

**Importing PDFs** follows the same split. `api` never writes `/manga`, so the preview route keeps
the upload in `reader-cache/imports/<token>/`, the one volume `api` and `worker-download` share, and
answers with a plan built by `app/importer/`. Confirming queues `import_files` on the download lane,
which rebuilds the plan from the same staged files through the same function before it writes.
What the user reviewed is therefore what lands, and a retry after a crash skips what is already in
the library. `app/importer/` is pure at its edges like `downloader/`: it takes bytes and returns
values, and its tests build their PDFs rather than reading anyone's books. A drop left unconfirmed is
swept the next time anyone drops, after 24 hours.

Known risk: LoLoBun and Novelight number chapters by list position, so a chapter the site inserts
mid-list shifts every later number, and `upsert_chapters` would rebind existing rows to new URLs. A
follow-up should detect a URL change on a downloaded row.

## Live progress

A handler inserts into `job_event` and calls `pg_notify('jobs', ...)`. The API holds one dedicated
asyncpg connection with `LISTEN` on that channel and pushes to the browser over SSE. Nothing polls,
anywhere. A screen that polls is doing it wrong.

New chapters travel on the same channel. When `chapter_discover` or `jnc_library_sync` writes a
`notification` row, it sends `notification.new` in the same transaction, so the event leaves only
if the run commits. The payload names the row and nothing more. The browser re-reads
`/api/notifications`, so the API stays the one answer to what a notification says. Marking a
notification read sends `notification.read` the same way, so the badge in every other open tab
follows. A tab that is
not in front also raises a desktop notification through the browser's own Notification API. That
needs no push service, which is also why it happens only while a tab is open.

The source registry travels the same way in the other direction. Every process builds its own in
memory at boot. When Settings enables or disables a site, or saves a setting a source is built from
(the MangaFire cookie), the API calls `pg_notify('sources_changed')` in the same transaction and
rebuilds its own; each worker holds a `LISTEN` on that channel and rebuilds on every notification,
and once more whenever the listening connection is (re)established, which covers a change committed
while it was not listening. Without it, a site enabled in Settings was searched and downloaded by
nothing until the containers restarted.

## Concurrency

The worker runs N asyncio tasks, N from the `download_concurrency` setting, default 3.

Above that sits **a semaphore per source site** (`downloader/limits.py`). Parallelism across sites is
free; parallelism against one site earns a rate limit or an IP block. Any new code that reaches a
source must take that semaphore.

## The interface

`frontend/src/` is a token layer, presentational primitives in `ui/`, one folder per screen in
`features/`, and shared non-visual code in `lib/`.

`GET /api/discover` is the one read model assembled from several sources rather than served from
one: suggestions, the mapping review queue and unmatched anime, ordered by how close each is to
done. It reads only. Adding, confirming and searching stay on the endpoints they already had —
they create series, reach real MyAnimeList and AniList accounts and enqueue downloads, and
rewriting the outward-facing half alongside the visible half would have bought nothing.

Four rules, each of which cost time when broken:

- **`tailwind.config.ts` is the only place a colour, size, radius or spacing value lives.** No hex,
  px or rem literal belongs in a component.
- **A Tailwind class is only real if the built CSS contains it.** A class can look right, typecheck,
  build clean and generate nothing — a name built by string interpolation is never seen by the
  scanner; `font-label-md` does not exist where the scale lives under `fontSize`, so `text-label-md`
  already carries size and weight; under Tailwind 3, `bg-secondary/12` needed `/[0.12]` because the
  modifier took scale steps (Tailwind 4 accepts any integer). All three fail identically and
  silently. Verification is `grep` over `frontend/dist/` after
  a build: **the source is what lies, the build output is what tells the truth.**
- **Feature folders never import from each other.** Anything two screens need goes in `ui/` or
  `lib/`. A small duplicated helper is cheaper than a cross-feature edge.
- **No screen renders a number the API cannot serve.** An invented figure that fills a gap in a
  mockup is worse than the gap.

A screen's own data goes through `lib/useAsyncData.ts`, which decides how a request that has not
landed, one that failed, and a refresh that failed over loaded data each look. Built one screen at a
time, they did not agree.

## Testing

| Layer | How |
|---|---|
| The four pure edges | Recorded fixtures, no network |
| `queue` | A real Postgres. Concurrent leasing, lease expiry, backoff |
| Handlers | Fakes for the edges |
| API | A real database, through `ASGITransport` |

The queue is tested against a real database because concurrent leasing, lease expiry and backoff are
exactly what a mock gets wrong.

**The suite migrates the database itself**, from a session fixture in `tests/conftest.py`. That lives
there rather than in the modules that need it: a module truncating a table without owning that
fixture passes on any database migrated by an earlier run and fails on a fresh one — invisible
locally, and failing every time in CI.

CI runs the same checks on every push and pull request, against a Postgres that is fresh each time,
plus a job that fails any pull request carrying tool attribution.

## Failure handling

Retry at 1, 5 and 25 minutes, three attempts, then `failed` with its error visible in the interface.

**`PermanentError` skips the ladder.** Use it when retrying cannot help. A network timeout is
transient; a chapter the source does not publish is not, and retrying it forever is how a queue
fills with work that will never succeed.

Errors reach the user. `last_error` and the job log are shown on the Downloads screen, so a failure
is something to read rather than something to go looking for in container output.
