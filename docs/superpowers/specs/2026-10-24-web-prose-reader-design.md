# Reading novels in the web interface

## Why

The PDF import (PRs #265, #267; `2026-10-23-novel-pdf-import-design.md`) put a novel's books into the
library, but nothing in Soshuhen reads them. The user reads *Tsuki ga Michibiku Isekai Douchuu*
(series 308, `tsukimichi-moonlit-fantasy-2`, twenty imported light novel volumes, no mapping) as
PDFs today, and two things bother them:

- **Progress is tracked by hand.** Nothing knows where they stopped, and nothing tells the lists
  they finished a volume.
- **The page is not adjustable.** Sometimes the font is too small, sometimes they want the
  background an EPUB reader would give them.

This is project 2 of the three named in the import design. Project 3 (Android) runs in parallel in
another session; the contract between the two is below.

## Goals

- On a prose series' page, the main column lists **volumes**, with each web novel volume's
  chapters under it, and a **Read** action on each volume and chapter.
- A **prose reader** in the web interface that opens the EPUB already in the library, with an
  adjustable **font size** and **background** (light, sepia, dark).
- **Position saves itself** while reading, and reopening continues from the same place.
- **Finishing** a chapter or a light novel volume moves list progress forward through the paths that
  already exist, with no manual step.
- A series with no source but with content in the library is **`local`**, and no screen asks it for a
  source mapping any more.

## Non-goals

- Android. That session owns `mobile/`, `routes_chapters.py` and the new `routes_volumes.py`.
- Paged (book-style) reading. Continuous scroll only.
- Font family, line height, margins, text alignment. Font size and background only.
- Highlights, notes, bookmarks inside a book, search inside a book, dictionary.
- Reading prose that is not on disk. A prose chapter or volume that is not downloaded has no Read
  action; streaming from a source is the comic reader's job.
- Reconciling what MyAnimeList (light novel) and MangaBaka (web novel) count. As in the import
  design, each list counts its own edition.
- Changing the comic reader.

## Anti-goals

- **Progress moving backwards.** Rereading volume 3 after volume 10 must leave every list at 10.
- **A page the reader cannot trust.** EPUB markup goes into the interface's own DOM, so it is
  sanitised server-side to an allowlist. A script, an event handler, a remote resource or a `style`
  that escapes the reading column is a bug.
- **Asking a local series for a mapping.** Once a series is `local`, no badge, card, table cell or
  panel tells the user it needs one.
- **Breaking the Android contract** (below), in either direction.

## Decided with the user

- **Continuous scroll**, not pages.
- **Adjustments are font size and background** (light / sepia / dark), **global for every novel**,
  not per series.
- **The side Volumes panel goes away for prose.** Volumes live in the main column. (Its wrapping
  "Downloaded" badge goes with it.)
- **Both editions shown apart** when a series has both: a "Light novel" group and a "Web novel"
  group. With one edition there is no group heading.
- **A web volume expands to its chapters** (`first_part`..`last_part`); a light volume is one row.
- **Each row shows whether it was read**, and has Read when its file is on disk.
- **At the end of a chapter or volume**, the reader offers to mark it read and go to the next one.
- **`local`**: a series with no active mapping and at least one downloaded chapter or volume, of
  **any kind**, comic or prose. "Local" says only that there is no source to download from; the
  series is still tied to its work on the trackers, and progress keeps going to them.
- **A finished web novel chapter goes to the lists as it does today** (`floor(number)` to every
  entry, forward only). Volumes need no such decision: the import design already made volume numbers
  follow the light novel, and either edition's volume N read counts as volume N read.

## Contract with the Android session

Neither side breaks this.

- This session makes `POST /api/reader/chapters/{id}/complete` work for prose chapters, and adds
  `POST /api/reader/volumes/{id}/complete`, which marks a light volume read and queues the same
  progress work. Both accept the existing optional `{"read_at": <aware datetime>}` body.
- `GET /api/series/{id}` volume objects gain `"id"` and `"file_path"` (the stored path or null; the
  app names its own copy after it, as it does with `chapter.file_path`). They already carry `edition`.
- The Android app keeps prose position and typography on the device and sends only completions.
  The volume route accepts `read_at` and has no use for it beyond accepting it: volume progress is
  derived later by `progress_push` from Komga's read state.
- The Android session owns `GET /api/chapters/{id}/archive` and `GET /api/volumes/{id}/archive`.
  This session does not touch `routes_chapters.py`, `routes_volumes.py` or `mobile/`.
- `series.state` gains the value `local`. Clients that do not know it show nothing special for it,
  which is the right outcome; the Android session is told so through the shared notes folder.

## How it works

### Series state

`_state_of` in `routes_series.py` returns `local` when the series has no active mapping and has at
least one `chapter` or `volume` with `state = 'downloaded'`. `downloading` and `failed` still come
first. LIST_SQL gains a per-series count of downloaded volumes, grouped on its own like the chapter
stats so the joins cannot cross-multiply.

`local` joins `SeriesState` in `frontend/src/lib/api.ts` and `SERIES_STATES` in
`backend/app/mcp/tools.py`.

- **CoverCard**: no "Needs a source mapping" note, no warning styling. A quiet "In your library"
  note instead.
- **SeriesHeader**: no "Needs review" badge; a neutral "Local" badge.
- **SeriesTable**: a `Local` label with a neutral tone.
- **MappingPanel**: for a local series it says the series reads from files already in the library
  and keeps search and remap behind a secondary action, rather than leading with a request to map.

Because `local` covers comics too, an unmapped comic with downloaded chapters stops being asked for
a mapping. Parked `match_search` candidates on such a series stay stored and the mapping panel still
offers them behind its secondary action; they are just no longer a request.

*Builder's calls:* the review queue (`REVIEW_QUEUE_SQL`) and the dashboard's pending-mappings count
(`routes_dashboard.py`) also leave `local` series out, using the same condition, because "stop asking"
means nowhere asks. The discovery gatherer (`discovery/gather.py`) is left alone: it decides what to
search for, not what to ask the user.

### Volume ids in series detail

The volume query in `GET /api/series/{id}` selects `id`, `first_part`, `last_part` and `file_path`,
and each volume object gains `"id"`, `"file_path"`, `"first_part"`, `"last_part"` (numbers or null) and
`"readable"` (file on disk under the library root). Chapters gain `"readable"` the same way, so the
interface never offers Read on a file the api cannot open.

### Reading an EPUB (pure module)

A new `backend/app/reader/epub_text.py`, pure like the rest of `reader/`: a path in, values out.

- Reads `META-INF/container.xml`, the OPF it names, the spine, and the table of contents (EPUB 3
  `nav`, falling back to EPUB 2 NCX) for section titles.
- `sections(path)`: the spine as an ordered list of `{index, title, href}`. Non-linear items and the
  nav document are left out.
- `section_html(path, index)`: the section's `<body>` content, sanitised to an allowlist of tags
  (paragraphs, headings, emphasis, lists, block quotes, `br`, `hr`, `img`, `figure`, `figcaption`,
  `sup`, `sub`, tables, `div`, `span`, `section`) with every attribute dropped except `img`'s `src`
  and `alt`. Image `src` is resolved relative to the section and rewritten to the api's resource
  route. Links keep their text and lose their target. Unknown tags unwrap to their text; `script`,
  `style`, `iframe`, `object`, `embed`, `svg` and `math` are removed with their content.
- `resource(path, href)`: an image's bytes and media type, only for manifest items that are images,
  so the route cannot be used to read arbitrary members.

It uses `selectolax`, already a dependency. Tested against EPUBs the tests build themselves (the
writer in `downloader/epub.py` and a hand-built multi-section EPUB 2 and EPUB 3). The user's own
books are never fixtures.

### Reader routes (`routes_reader.py`, `reader_service.py`)

A book is either a prose chapter (`chapter.file_path`, one EPUB) or a light volume
(`volume.file_path`, one EPUB). Both go through the same service functions with a `kind` of
`chapter` or `volume`. The existing `archive.inside` check applies to every path.

- `GET /api/reader/prose/{kind}/{id}`: the manifest. `{kind, id, series: {id, title}, title,
  number, edition, sections: [{index, title}], previous, next, position, prefs}`. `previous` /
  `next` are the neighbouring readable chapter by number, or the neighbouring readable volume of
  the same edition by number. `position` is `{section, fraction}` when the series' saved position
  points at this book, else null.
- `GET /api/reader/prose/{kind}/{id}/sections/{index}`: `{index, title, html}`.
- `GET /api/reader/prose/{kind}/{id}/resources/{href:path}`: image bytes, `IMMUTABLE` cache header.
- `GET /api/reader/prose/prefs`, `PUT /api/reader/prose/prefs`: `{font_size, theme}`. Global,
  stored in `setting` through `settings_store` as `reader_prose_font_size` (integer step) and
  `reader_prose_theme` (`light`, `sepia`, `dark`).
- `GET /api/reader/chapters/{id}` and its pages keep answering 409 for prose, with a detail that
  names the prose routes instead of Komga. `reader_service.chapter()` loses the prose refusal; the
  comic-only routes check the kind themselves.

**Errors:** a book whose file is missing or outside the library is 404 with a reason; a `kind` that
does not match the row (a web volume, a comic chapter) is 409; a broken EPUB is 422.

### Position

`reading_position` stays one row per series, so "where am I in this series" keeps one answer. A
migration (`0029`) makes `chapter_id` nullable, adds a nullable `volume_id` (FK `volume.id`, cascade)
and a nullable `fraction` (`real`, 0..1), with a check that exactly one of `chapter_id` and
`volume_id` is set. For prose, `page` is the spine section index and `fraction` how far through that
section the reader has scrolled.

`PUT /api/reader/series/{id}/position` accepts either `chapter_id` or `volume_id` (exactly one),
`page`, and an optional `fraction`. Existing callers sending `chapter_id` and `page` behave exactly as
before. `reading_recency.py` keeps working: a row with a volume and no chapter is still a row with an
`updated_at`.

*Builder's call:* `GET /api/reader/series/{id}/resume` keeps its shape, `{chapter_id, page}`, because
the Android app and the web `ResumePage` both decode it. Its query already joins `chapter`, so a saved
volume position is ignored there and it falls through to its existing fallback (404 for a series with
no chapters). Prose gets its own `GET /api/reader/prose/series/{id}/resume`, answering
`{kind, id, section, fraction}` from the saved position, or the first unread light volume, or the first
readable chapter past list progress. The web `ResumePage` asks the prose route for a prose series.

The web reader saves on scroll, debounced, and on leaving.

### Finishing

- **A prose chapter** (`POST /api/reader/chapters/{id}/complete`): the same route as comics, with
  the prose refusal removed. Lists get `floor(number)` through `queue_progress_write` and the
  forward-only guard; Komga gets `KOMGA_READ_PROGRESS` when the chapter has a book id. Finishing the
  last chapter of a web volume is how that volume becomes read, through `furthest_volume`'s
  parts-read rule on the next `progress_push`.
- **A light volume** (`POST /api/reader/volumes/{id}/complete`): 409 for a web volume (it is read by
  its chapters) and 404 for an unknown one. With a `komga_book_id`, it queues `KOMGA_READ_PROGRESS`
  for that book carrying the series id, and that handler, once Komga has the book marked read,
  queues `PROGRESS_PUSH` for the series (deduplicated on the series). `progress_push` then derives
  the furthest volume from Komga with `volume_progress.furthest_volume` and pushes it only forward
  (`pushable_volume`). Chained rather than queued side by side, because two jobs leased together
  could push before Komga has the book marked. Without a Komga book id nothing is queued, and the
  response says so: `{progress_queued: false, komga_queued: false}`.

For series 308: all twenty volumes have a Komga book id; MyAnimeList stands at volume 1, MangaBaka
at volume 0. Finishing volume 2 pushes volume 2 to both.

### The series page (prose)

For `series.kind === 'prose'`, the "Chapters" tab becomes **"Contents"** and renders a new
`ProseContents` component in place of `ChapterTable`, and `VolumesPanel` is not rendered. Comic
series are unchanged.

- Groups by edition when both exist (light novel first), otherwise one flat list.
- A light volume row: `Vol. N`, title, read mark, state, **Read**.
- A web volume row: `Vol. N`, the chapter range, read mark, expandable to its chapter rows (number,
  title, read mark, **Read**). Expanded by default for the volume holding the next unread chapter.
- Chapters in no volume's range (the case before any web volume exists, or prose downloaded from a
  source) are listed after the volumes as "Other chapters", with the existing bookmark and Komga
  link behaviour.
- **Read marks** come from the lists, the same rule as the chapter table: a chapter is read when its
  number is at or below `series.progress`; a light volume when its number is at or below the highest
  `user_progress_volume` across entries; a web volume when its last part is read.
- Read links go to `/read/prose/volume/:id` and `/read/prose/chapter/:id`.

### The reader screen

A new route outside the shell, beside the comic reader, built from `ui/` primitives and the reader
feature's existing sheet (`ReaderSheet`). A new `features/prose-reader/` folder; it imports nothing
from `features/reader/`, so anything both need moves to `ui/` or `lib/`.

- A top bar (back to the series, book title, section title, settings) that hides on scroll down and
  returns on scroll up or tap.
- A single reading column of comfortable width, all sections rendered in order, images lazy.
- A thin progress indicator for the whole book.
- Settings sheet: font size (stepper, a small fixed range) and background (light, sepia, dark). Applies
  immediately and saves globally.
- A table of contents sheet from `sections`.
- At the end: "Mark as read" (calls complete) and "Next volume/chapter" when there is one. Reaching
  the end with Next marks it read too.
- Opening resumes at `position` when given.

Themes and type sizes are tokens in `frontend/tailwind.config.ts` (three reading surfaces and their
text colours, a reading type scale), never literals, and are verified in `frontend/dist/` after a
build. The sanitised HTML is styled by descendant selectors under one reader class defined in
`src/styles/index.css` from those tokens.

## Left to the builder

- The exact allowlist details and how a section with no body text (a cover page) is shown.
- The font-size range and its steps.
- How the frontend tracks section and fraction while scrolling.
- Debounce intervals.
- Whether the manifest's `sections` excludes cover-only sections.
- Copy, within the existing voice of the interface.
- Test structure, following the repository's existing tests for `reader/`, the reader routes and
  `routes_series`.

## Done

On series 308, in the web interface: the series page lists twenty volumes with Read; opening one
renders its text and illustrations; font size and background change and stay changed; leaving and
reopening returns to the same place; finishing marks it read and the next `progress_push` moves the
lists forward; the library card says nothing about a mapping. CI passes, and the PR is merged.
