# A reader inside Soshuhen

Soshuhen ships no reader today, on the grounds that Komga is one (`docs/features.md`, "Reading").
That leaves reading and downloading in two applications: a chapter is read in Komga or Mihon, and
the decision to fetch the next ones is made somewhere else. This adds a reader to the web interface
so that a series can be read, tracked and fetched from one place, on a tablet and on a desktop.

Komga and Mihon stay. They remain valid readers, and progress has to converge across all three.

## Decisions taken

| Question | Decision |
|---|---|
| Which chapters can be read | Any chapter, including ones not yet downloaded. Pages of an undownloaded chapter are streamed from the source. |
| What happens to a streamed chapter | The pages fetched for reading become the download. The source is asked for each page once; the CBZ is assembled from the cache. |
| Where progress goes | Page position is kept in Soshuhen, for resuming on any device. Finishing a chapter writes to the lists (MyAnimeList, AniList, local), forward-only, and to Komga's read progress when the book is indexed. |
| Who fetches pages | The `api` process, on demand, through a cache (approach 1 below). |

### Approaches considered

1. **`api` fetches on demand, through a cache.** Chosen. Lowest latency: the first page shows as soon
   as the source answers, and the download pipeline barely changes.
2. **A reader lane in the worker.** Opening a chapter enqueues a fetch job on a new `worker-reader`
   service, and `pg_notify` plus SSE announce each page. It keeps `api` off source sites, at the cost
   of a new service and a queue round trip per page.
3. **The browser fetches from the source.** Rejected. CORS, referer checks and descrambling break on
   most sites, and the pages would never pass through the server to become an archive.

## Scope

**In the first version**

- Modes: paged left-to-right, paged right-to-left, long strip, double page.
- Scale: fit width, fit height, fit screen.
- Background: black, gray, white.
- Mode and scale per series, falling back to a global default.
- Navigation: keyboard, click or tap zones left and right, page slider, chapter panel, previous and
  next chapter.
- Preloading of the next pages and of the start of the next chapter.

**Deferred**

- Custom tap zones (L-shaped, Kindle-ish) and inverted zones.
- Crop borders, splitting or rotating wide pages, zoom start position.
- Filters: grayscale, dim, custom colour filter, flash on page change.
- Rotation locks. The browser and the operating system already handle orientation.

## Data model

One migration adds three tables, one chapter state and one progress event source.

**`reading_position`** — one row per series.

| Column | Type | Notes |
|---|---|---|
| `series_id` | int, PK, FK `series` | |
| `chapter_id` | int, FK `chapter` | |
| `page` | int | Zero-based. |
| `updated_at` | timestamptz | |

This is kept apart from `list_entry.user_progress_chapter`. That column is a list's view of
progress, overwritten by every sync. A page position is local to this installation and no list
holds it.

**`series_reader_pref`** — one row per series that differs from the default.

| Column | Type | Notes |
|---|---|---|
| `series_id` | int, PK, FK `series` | |
| `mode` | text | `paged_ltr`, `paged_rtl`, `long_strip`, `double` |
| `scale` | text | `fit_width`, `fit_height`, `fit_screen` |
| `background` | text | `black`, `gray`, `white` |

With no row, the global default applies. The default lives in the `setting` table under
`reader_default_mode`, `reader_default_scale` and `reader_default_background`.

**`chapter_page_list`** — cached page list of a chapter being streamed.

| Column | Type | Notes |
|---|---|---|
| `chapter_id` | int, PK, FK `chapter` | |
| `pages` | jsonb | Serialised `PageRef` list. |
| `fetched_at` | timestamptz | |

The list is kept in the database rather than in memory so it survives a restart of `api`. It can
expire: a source may stop serving pages named in a list that resolved minutes earlier. The existing
`PageListStale` handling applies, and a stale list is fetched again once.

**`progress_event.source`** gains `reader`, next to `komga` and `manual`. It is what lets
`komga_scan` find chapters read in Soshuhen before Komga had indexed them.

**`chapter.state`** gains `streaming`. A chapter in that state has pages arriving in the reader
cache, and `download_batch` skips it so the source is not asked for the same chapter twice.

## API

A new router, `app/api/routes_reader.py`, under `/api/reader`.

| Method and path | Purpose |
|---|---|
| `GET /chapters/{id}` | Manifest: `page_count`, origin (`archive` or `stream`), previous and next chapter ids, saved position, effective preferences. |
| `GET /chapters/{id}/pages/{n}` | One page image. |
| `PUT /series/{id}/position` | Saves `{chapter_id, page}`. The reader calls it debounced. |
| `POST /chapters/{id}/complete` | Marks a chapter finished. |
| `GET /series/{id}/prefs`, `PUT /series/{id}/prefs` | Per-series preferences. |
| `PUT /defaults` | The global default, from the settings panel's "use for every series". |
| `GET /series/{id}/resume` | Where *Continue reading* opens: the saved position, else the first chapter past the furthest one read. |

### Serving a page

- **Downloaded chapter.** The page is read as a member of the CBZ at `chapter.file_path`. `api`
  already mounts the library read-only at `/manga`, which is all this needs.
- **Undownloaded chapter.**
  - If the page is in the reader cache, serve it.
  - Otherwise, take the page list from `chapter_page_list`, or ask the source for it with
    `list_pages` and store it.
  - Fetch the page with the existing `fetcher`, apply `descramble`, write it to the cache and serve
    it.
  - The first fetch moves the chapter from `known` to `streaming`.

Responses carry `Cache-Control: public, max-age=31536000, immutable`. A page of a chapter never
changes once fetched.

### Finishing a chapter

`POST /chapters/{id}/complete` enqueues:

- `progress_write`, to every list entry of the series. It uses the forward-only guard and the
  chapter ceiling of the manual progress path, so completing chapter 10 while a list says 15 does
  nothing.
- `komga_read_progress`, when the chapter has a `komga_book_id`. It is a new job in the fetch lane
  that calls `set_read_progress` with `completed: true`. A chapter not yet indexed by Komga gets there through `komga_scan`. After it adopts book
ids, it marks read in Komga every book at or below the series' furthest list progress. That covers
chapters read here while they were still streaming, and chapters read in Mihon too. `progress_write`
records the reader as the event source (`progress_event.source = reader`) for the stats.

## From the cache to the library

The reader cache is a new named volume, `reader-cache`.

| Service | Mount |
|---|---|
| `api` | `/reader-cache`, read-write, running as `PUID:PGID` |
| `worker-download` | `/reader-cache`, read-write |

`api` runs as the same user as `worker-download`, because the worker deletes what `api` wrote once
it has become an archive. The image creates `/reader-cache` world-writable, so a fresh named volume
inherits that mode.

Layout: `/reader-cache/{chapter_id}/{n}.{ext}`.

When the last missing page of a chapter lands in the cache, `api` enqueues
`download_chapter{chapter_id, from_cache: true}`. A unique partial index on pending jobs of that
shape makes the enqueue idempotent, so concurrent requests for the last page enqueue exactly one.

With `from_cache`, `download_chapter`:

1. Skips `list_pages` and `fetch_pages`.
2. Reads the pages in order from `/reader-cache/{chapter_id}/`.
3. Builds `ComicInfo.xml` and the CBZ exactly as it does today.
4. Marks the chapter `downloaded`.
5. Deletes the cache directory.

If a page is missing from the cache when the job runs, the handler falls back to the network path
for the missing pages only.

`worker-download` stays the only process that writes the library. `api` writes the cache, never
`/manga`, which keeps the library mounted read-only everywhere except the download lane.

**Abandoned chapters.** A chapter opened and left half read keeps its cache. `worker-download`'s
existing reclaim loop, the only worker that mounts the cache, deletes cache directories untouched for
seven days and returns their chapters from `streaming` to `known`. There is no new cron entry or job
type.

## A reader slot per site

`app/downloader/limits.py` keeps one `asyncio.Semaphore` per site, in memory, and only the download
lane uses it. A download batch holds its slot for every chapter in the batch, so a reader queueing
for the same slots would wait minutes for a page.

The reader gets one slot of its own per site instead, in-process in `api` (`reader_semaphore`). A
site sees at most `per_source_concurrency + 1`: a person reading on top of the backlog, not a second
backlog. Page lists and pages the reader fetches are human-paced, with a preload of three pages.

## Errors

| Situation | Response | What the reader shows |
|---|---|---|
| The source will not serve one page | `502` with a reason | A page-sized placeholder with "page unavailable — try again". The rest of the chapter keeps working. |
| `ChapterUnavailable` | `410` with a reason | The chapter cannot be read, with the reason, and a link to the series. |
| No mapping for the series | `409` | "This series has no confirmed source yet", with a link to review. |
| Page number out of range | `404` | Not reachable from the interface. |

## Interface

### Route

`/read/:chapterId?page=N` sits outside `AppShell`. The reader is full screen, without the header or
the bottom navigation, and its back action returns to `series/:id`.

Changes elsewhere:

- `ChapterTable` replaces its external Komga link with **Read**, available in every chapter state.
  "Open in Komga" stays as a secondary action when `komga_public_url` is set.
- `ContinueReading`, on home and on the library screen, opens the reader at the saved position.

### Structure

`frontend/src/features/reader/`:

| Unit | Responsibility |
|---|---|
| `ReaderPage` | Loads the manifest through `useAsyncData`, owns the current page, saves the position debounced. |
| `PagedView` | Paged left-to-right, right-to-left and double. |
| `StripView` | Long strip. Every page is rendered with native lazy loading; the current page is the one an `IntersectionObserver` reports most visible. |
| `ReaderChrome` | Picks the tablet or desktop chrome by breakpoint. |
| `SettingsPanel`, `ChapterPanel`, `PageSlider` | The panels and the slider. |
| `lib/` (inside the feature) | Preloading and keyboard handling, used only by the reader. |

A primitive another screen could use, such as a segmented control or a slider, goes in `ui/`.

### Layout by breakpoint

The split follows `AppShell`, which already treats everything below `xl` as the tablet layout.

**Below `xl` — tablet and phone, after Mihon**

- A tap in the centre shows or hides the chrome.
- Top bar: back, series title, chapter title, menu.
- Bottom: page slider between previous- and next-chapter buttons, and a settings button.
- Settings open as a bottom sheet with two tabs, Mode and General.
- Taps on the left and right edges turn the page.

**`xl` and above — desktop, after MangaDex**

- The chrome stays quiet and on screen.
- A pill at the top reads "Ch. 64 / 65", with arrows.
- A vertical icon bar on the right: home, series, chapters, settings, fit, fullscreen.
- Chapters and settings open as modal panels; settings have two tabs, Layout and Image.
- Keyboard:
  - `←` and `→` turn the page and follow the reading direction.
  - Space and Shift+Space turn the page or scroll the strip.
  - `[` and `]` change chapter.
  - `f` toggles fullscreen.

### Behaviour

- **End of a chapter.** A transition screen reads "End of Ch. 23 → Ch. 24". Reaching it calls
  `/complete` once for that chapter. Continuing opens the next one.
- **Preloading.** Three pages ahead. When three pages remain, the first three pages of the next
  chapter are preloaded too.
- **Failed page.** A placeholder the size of the page, with a retry.
- **Streaming chapter.** A note says the chapter is streamed from the source and will be saved to
  the library once every page has loaded. No count: a job progress tick carries no chapter id, so a
  number there would be invented.
  stream.

### Rules that apply

- Colours, sizes and spacing come from `frontend/tailwind.config.ts` only. The three backgrounds
  become tokens.
- Every new class is checked with `grep` over `frontend/dist/` after a build.
- No number on screen that the API does not serve. `page_count` comes from the manifest, and the
  "12/40" indicator from the job's progress.

## Testing

**Backend**, against a real Postgres like the rest of the suite.

- **Archive page.** A fixture CBZ; requesting page N returns that member's bytes with the right
  content type.
- **Streamed page.** A fake `Source`:
  - The first request fetches and writes the cache; the second is served from the cache with no
    source call.
  - `PageListStale` fetches the list again once.
  - `ChapterUnavailable` becomes a `410`.
- **Completion of the cache.** Concurrent requests for the last page enqueue exactly one
  `download_chapter{from_cache}`.
- **Assembly from the cache.** With a fake source that fails if called, `download_chapter{from_cache}`
  builds a CBZ with `ComicInfo.xml`, marks the chapter `downloaded` and deletes the cache.
- **Partial cache.** A missing page is fetched from the network; the others are not.
- **Batches.** `download_batch` skips a chapter in `streaming`.
- **Completion.** `/complete` is forward-only against the lists, and enqueues the Komga write only
  when `komga_book_id` is set.
- **Reader slot.** The reader's semaphore is one slot per site, separate from the downloads' slots.
- **Cleanup.** A cache directory older than seven days is deleted and its chapter returns to `known`.

**Frontend.** There is no component test suite today, and this does not add one.

- `tsc -b` and the build pass.
- New classes are found in `dist/`.
- A manual pass in the browser at phone, tablet and desktop widths covers the four modes, the
  keyboard, preloading, a failed page and the end-of-chapter transition.

## Documentation

| File | Change |
|---|---|
| `docs/features.md` | "Reading" stops saying there is no reader. It describes the reader, its modes, and that Komga and Mihon remain valid. |
| `docs/configuration.md` | "Reading on your phone" stops claiming progress syncs both ways. It states the real flow: reader to lists and Komga; Komga to lists through `progress_push`. |
| `docs/data-model.md` | The three tables, the `streaming` state and the `reader` event source. |
| `docs/architecture.md` | `api` now reaches source sites. Documents the `reader-cache` volume, the reader slot per site, and why `worker-download` stays the only writer of the library. |
| `docs/jobs.md` | `download_chapter{from_cache}`, the cache cleanup, `komga_read_progress`. |
| `CLAUDE.md` | The lane notes and the rebuild instructions mention the new volume. |
