# Reading novels in the Android app

Date: 2026-10-24
Status: design, awaiting the user's approval

## Why

The user reads novels too, and in the Android app they do not even appear. The app was built
comics-first on purpose (`2026-10-20-android-client-design.md`, non-goal "No prose (EPUB) support
for now"), and prose is excluded in three places today:

- `LibraryRules.comics()` drops prose series from the library.
- `ImportRunner` skips a prose series when it copies (`if (detail.series.kind == "prose") continue`).
- `GET /api/chapters/{id}/archive` refuses prose through `reader_service.chapter()` and answers only
  `application/vnd.comicbook+zip`.

The PDF import (`2026-10-23-novel-pdf-import-design.md`) is what made this urgent: series 308
(`tsukimichi-moonlit-fantasy-2`) now holds twenty light novel volumes, each one EPUB, and the user
wants to read them on the train like any manga.

This is project 3 of the three that design names. Project 2, the web interface's prose reader, runs
in parallel in another session (`web-prose-reader`); the contract between the two is below.

## Goals

- Prose series appear in the app's library, can be marked, and their files are copied to the device
  like comics: in the background at home, resumed with Range/If-Range when cut off.
- The series screen of a prose series lists what can be read: light novel volumes as whole books,
  web novel chapters grouped under their volumes. When a series has both editions the user switches
  between them.
- An EPUB reader that renders the text and its images, works fully offline, and remembers where the
  user stopped.
- The reader offers the same four directions as the manga reader, chosen per series: paged left to
  right, paged right to left, double page (wide screens only), and continuous scroll.
- The user adjusts the font size, the font, and the background colour.
- Finishing a chapter or a light novel volume reports it to the server, through the same offline
  queue comics use.

## Non-goals

- Reading position for prose does not travel between the app and the web. It stays on the device.
  Only completions reach the server.
- Typography settings do not travel either; they are the device's.
- No annotations, highlights, bookmarks inside a book, dictionary, text-to-speech or search.
- No faithful rendering of publisher CSS. The reader shows text structure (headings, paragraphs,
  emphasis, images, breaks) in the app's own typography. An EPUB laid out with tables or floats reads
  as plain flowing text, which is acceptable for novels.
- No EPUB 2 NCX or EPUB 3 nav-based table of contents in this round. The user moves with the slider
  and, for web novels, the chapter list.
- No change to how comics are read or copied.

## Anti-goals

- **Anything leaving the device except to the Soshuhen server.** An EPUB can reference remote images,
  fonts or stylesheets. The reader never fetches them.
- **A position lost when the font size or the screen changes.** A page number is not a position.
- **Moving progress backwards** on the server or a list when a completion is replayed late. The
  server's `forward_only` and `read_at` already guard this; the app must keep sending `read_at`.
- **Deleting anything the user did not ask to delete**, exactly as for comics.
- Editing the web session's files beyond a one-line registration.

## Decided with the user

- **Directions** are the manga reader's four, chosen the same way (user: "quero poder escolher a
  direção assim como nos mangás").
- **Font size, font and background colour** are adjustable.
- The rest of the scope, the server contract and "done" come from the session that started this
  one, and the user said to go ahead from there.

## What exists, and what it means here

- **Series 308** on the user's server: twenty `volume` rows, `edition = light`, numbers 1–20, each
  with a `file_path` (`/manga/tsukimichi-moonlit-fantasy-2/tsukimichi-moonlit-fantasy-2 - Vol.0001.epub`)
  and a Komga book; no `chapter` rows.
- **What those EPUBs look like**, from `downloader/epub.py`: one `OEBPS/chapter.xhtml` holding the
  whole book (volume 1 is 370 KB of XHTML: `section`, `h2`, `p`, `img`, about 2,700 paragraphs, 11
  headings, 8 images), a `nav.xhtml`, a `content.opf` with a one-item spine, images under
  `OEBPS/images/`. A downloaded web chapter is the same shape with one chapter in it. J-Novel Club
  volumes are publisher EPUBs with many spine items and their own CSS. The reader has to handle the
  general case (container → OPF → spine), but must be fast on one very long spine item.
- **`GET /api/series/{id}`** lists `volumes` with `number`, `edition`, `title`, `state`,
  `komga_book_id`, but on `main` no `id` and no `file_path` yet (see Contract).
- **The app's device index** is keyed by chapter id (`device_chapter`, `import_part`), and its
  `ArchiveCheck` counts image pages, which an EPUB has none of.
- **The manga reader** (`reader/`) is one `ReaderViewModel` over a `PageSource` of images, with
  `ReaderChrome`, `TapZones` and `ReaderKeys` for controls. Server prefs (`mode`, `scale`,
  `background`) are per series.
- **Fonts bundled in the app**: Plus Jakarta Sans and JetBrains Mono. No serif.

## Contract with the web session

Agreed by the session that started both. Neither side breaks it.

This side owns:

- `GET /api/chapters/{id}/archive` serves a prose chapter's EPUB as `application/epub+zip`. Comics are
  unchanged (`application/vnd.comicbook+zip`).
- `GET /api/volumes/{id}/archive` (new, `backend/app/api/routes_volumes.py`) serves a volume's
  `file_path` EPUB with the same Range and ETag behaviour `FileResponse` gives the chapter route. 404
  when the volume has no file or the file is missing or outside the library.
- The router is registered in `app/api/main.py` with a one-line change.

The web session owns `reader_service.py`, `routes_reader.py`, `routes_series.py` and `frontend/`,
and provides:

- `"id"` on each volume in `GET /api/series/{id}`;
- `POST /api/reader/chapters/{id}/complete` working for prose;
- `POST /api/reader/volumes/{id}/complete` for light volumes.

Confirmed by the web session on 2026-10-24, beyond the above:

- each volume in `GET /api/series/{id}` also carries `file_path` (or null), `first_part`,
  `last_part` and `readable` (the file is on disk inside the library). The app names its copy after
  `file_path`, as it does for chapters, and copies a volume only when `readable` is true;
- `POST /api/reader/volumes/{id}/complete` takes the same optional `{"read_at": …}` body as the
  chapter route and answers `{"progress_queued", "komga_queued"}`; 404 for an unknown volume, 409 for
  a `web` volume (those are read through their chapters). Both are permanent refusals the outbox
  drops. It marks the volume read in Komga; the lists' `user_progress_volume` then moves through
  `progress_push`, which derives volume progress from Komga's read state. `read_at` only dates the
  event. So the app's locally raised volume progress is a forecast the next library refresh confirms
  or corrects, exactly as chapter progress is today;
- `series.state` gains `"local"` (no mapping, but a downloaded chapter or volume). The app must not
  show "Needs a source mapping" for it.

Because the chapter archive route must not go through `reader_service.chapter()` (which refuses
prose and is the web session's), the archive routes read the few columns they need with their own
query and reuse `app.reader.archive.inside` for the library check.

If this work is ready before the web session's PR merges, it is coded against the contract and
rebased on `main` once theirs lands, before merging.

## The app

### Library

`comics()` goes. Prose series show in the grid, the tabs, search and "Continue reading" like any
other. The unread arithmetic is unchanged. A small "Novel" label on the cover tells them apart
**(builder's call)**.

### Series screen

For a prose series the list below the header is built from `volumes` and `chapters`:

- **Light novel**: one row per `light` volume, "Volume N" plus its title, with the same three
  availability states as a chapter (on device, on server, not downloaded) and read/unread.
- **Web novel**: the series' chapters, grouped under a heading per `web` volume (its chapter range);
  chapters outside every range go under a final "Other chapters" heading.
- When the series has both editions, a two-way switch at the top of the list picks which one shows.
  It defaults to the edition with a file nearest the user's progress, and otherwise to light
  **(builder's call)**. A series with one edition shows no switch.
- "Continue" opens the first unread item of the edition shown.
- Delete-from-device works on volumes as it does on chapters.

A light volume is read when its number is at or below the list's volume progress (or the device's own
record of it, raised locally on completion like chapter progress). Web chapters use chapter progress,
as comics do.

### Copying

`ImportRunner` copies prose series too:

- chapters with `state = downloaded` and a `file_path`, from the chapter archive route, as today;
- light volumes with `state = downloaded` and a file, from the volume archive route.

Both go through the same resume logic (`.part` file, recorded ETag, If-Range, 416 handling,
adoption of an identical file already in the folder). The work item stops assuming it is a chapter:
it carries what to fetch, what to name it, and where to index it.

On the device a volume is indexed in its own table (`device_volume`, keyed by volume id), and its
`.part` ETag lives beside chapter parts without the two id spaces colliding. This is a Room schema
bump (2 → 3), as an auto-migration if Room can express it, otherwise a written one.

The check before a copy takes its place depends on the file: a CBZ still needs at least one page; an
EPUB needs a `META-INF/container.xml` whose rootfile is an OPF with at least one spine item that
exists in the zip. File names are the server's, under the same `Soshuhen/<slug>/` folder.

Notifications and the Updates screen count volumes as well as chapters ("Tsukimichi: 2 new
volumes").

### Opening a book

- **On the device**: the EPUB is unpacked once into the app's cache, keyed by item and
  `etag:size` like `PageExtractor`'s pages, and read from there.
- **On the server, at home**: the app fetches the whole EPUB from the archive route into the cache
  and opens it the same way. Nothing is written to the picked folder; that remains the import's job.
- Away from home only device items open, as with comics.

### The book model

A parser in `commonMain` turns an unpacked EPUB into an ordered list of **blocks**: headings,
paragraphs (with bold, italic and line breaks kept as styled spans), images (a path in the cache) and
section breaks. Anything else is reduced to its text. Remote URLs are dropped at this point, which is
what guarantees the reader cannot fetch anything.

A **position** is `(spine index, block index, character offset)`. It survives any change of font,
size, orientation or direction. Progress through a book, for the slider and for the "x%" label, is
the share of characters before the position.

### Rendering

Native Compose, not a WebView **(builder's call)**. Reasons: the reader stays in `commonMain` with the
manga reader and reuses its chrome, tap zones and volume keys; pagination and positions are plain
Kotlin that the JVM tests can cover; the guarantee that nothing is fetched comes from the model
rather than from intercepting a browser; and the books the user has are exactly the simple structure
this handles well.

- **Paged** (left to right, right to left): a paginator lays blocks out with `TextMeasurer` into
  pages that fit the viewport and the margins, splitting a paragraph between lines. Pages are built
  around the current position and outward, not for the whole book at once: a 370 KB volume must open
  without a visible wait. Turning follows the direction: in right-to-left a tap on the left edge goes
  forward.
- **Double page**: two of those pages side by side, offered only where the manga reader offers double
  page.
- **Continuous scroll**: a lazy column of blocks; the position is the first visible block and its
  offset.
- Images are fitted to the page width (and to the page height in paged modes), never larger than
  their own size.

Controls are the manga reader's: tap the middle for the chrome, tap the edges or swipe to turn,
volume keys turn the page (or scroll a screen in continuous mode) with the existing invert and off
switches, a slider by percentage, previous and next item.

### Reading settings

- **Direction** per series, with the manga reader's four values. Stored on the device for prose
  **(builder's call)**: the server's prefs belong to the web session's reader, and sharing them would
  make each reader depend on the other's reading of the same field.
- **Font size** in steps, **font** (serif, sans, and the app's Plus Jakarta Sans, the first two being
  the system's own so nothing is bundled), **background** (black, gray, white as the manga reader,
  plus sepia), each with matching text colour from the theme tokens. These are one setting for every
  novel on the device, not per series **(builder's call)**.
- Line spacing and margins are fixed, comfortable defaults from the tokens **(builder's call)**.

### Position and progress

- The position is saved on the device per item (chapter or volume), debounced as the manga reader's
  is, and the book reopens where it was left.
- **Finishing** is reaching the last page (paged) or the end of the last block (scroll), once per
  open, as with comics.
- A finished web chapter queues `complete` for the chapter, exactly as comics.
- A finished light volume queues a new `volume_complete` event, sent to
  `POST /api/reader/volumes/{id}/complete` with `read_at`, and raises the device's own volume
  progress at once.
- Both drain at home with the existing outbox, in order with everything else. A 4xx that can never
  succeed is dropped as today.

## Server work in this branch

Two routes and their tests, against the repository's pytest suite and a real Postgres:

- the chapter archive serves prose as `application/epub+zip`, comics as before;
- the volume archive serves a volume's file with Range and ETag, 404 for no file, a missing file or a
  path outside the library.

## Left to the builder

- The XML/HTML parsing library for EPUB (it must be multiplatform, tolerant of malformed XHTML, and
  its latest stable version checked from its release page), or a small hand-written reader if that is
  simpler for the subset needed.
- The paginator's algorithm and caching, within "opens without a visible wait".
- Exact layout and copy of the edition switch and the "Novel" label, within the theme tokens.
- How the work item in `ImportRunner` is generalised, and the exact Room migration.
- Font size steps and the default size.

## Done

On the user's phone, series 308 shows in the library; a volume copies, opens and reads offline; the
user changes direction, font, size and background and keeps their place; finishing the volume reaches
the server; the PR is merged with every CI check green, including `mobile`.
