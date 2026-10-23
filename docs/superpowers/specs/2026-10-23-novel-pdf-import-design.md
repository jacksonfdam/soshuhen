# Importing novel PDFs a user already owns

## Why

A user owns a complete run of a novel as PDFs and wants it in the library like anything Soshuhen
downloaded. Nothing today lets a file in: chapters are only born from `chapter_discover`, which
needs a confirmed source mapping, there is no upload route, and Komga's library is created with
`scanPdf: False`. Dropping the PDFs into the library folder does nothing.

The case that started this is *Tsuki ga Michibiku Isekai Douchuu* (series 308,
`tsukimichi-moonlit-fantasy-2`, `kind = prose`, no mapping, no chapters, not in Komga). The user
has twenty PDFs:

- **Volumes 01–18, the web novel**, a fan compilation exported from Word. Text PDFs, not scans.
  Every chapter is a top-level bookmark carrying the web novel's own running number, from the
  prologue to chapter 295 (`Chapter 213 …`). Each file also bookmarks `Cover`, usually
  `Characters`, sometimes `Map`. Volume 01 adds `Prologue 1–3`, `Prologue POV` and four
  unnumbered `POV Chapter` entries after chapters 9, 16 and 26.
- **Volumes 19–20, the light novel** in its English edition (*Tsukimichi: Moonlit Fantasy*),
  exported by Calibre. Bookmarks restart at `Chapter 1` in every volume, plus a `Side Story` in 19.

They are one story in two editions. The light novel merges and rewrites web chapters (its volume
15 tells web chapters 213–231 in eight chapters), so a light novel chapter has no web novel chapter
number, and inventing one would collide with web chapters 296 onward if those are ever imported.

This is the first of three projects, in this order:

1. **Import** (this document). Useful on its own: Komga already reads prose EPUBs.
2. A prose reader in the web interface, which today answers prose with 409 "read it in Komga".
3. A prose reader in the Android app, which today skips prose in three places.

## Goals

- From a series' own page, drag PDFs in, see how each one was read and what it will become, and
  import with one press.
- Every file written gets the library's canonical name for that series, whatever the PDF was
  called. "Normalise the names according to the work" is the user's own requirement.
- A web-novel PDF becomes one prose chapter per chapter bookmark, numbered by the number in the
  bookmark, plus a `volume` row recording the chapter range it covers.
- A light-novel PDF becomes one whole-volume EPUB and a `volume` row with no chapter range.
- The result is indistinguishable downstream from a downloaded chapter or a J-Novel Club volume:
  Komga scans it, reconciliation adopts it, and the later readers open it.

## Non-goals

- Reading prose in either reader. That is projects 2 and 3.
- Scanned PDFs, OCR, or PDFs without bookmarks. Such a file is reported as unreadable and skipped.
- Comic PDFs. The import is for prose series only.
- EPUB, DOCX or other input formats. They fit the same screen later; not now.
- Reconciling what MyAnimeList (light novel, counts chapter 2 volume 1) and MangaBaka (web novel,
  295 chapters) each count. Each list counts a different edition; this does not try to fix that.
- Creating a series. The import attaches to a series that already exists.
- A watched drop folder. The user chose a screen.

## Anti-goals

- **Inventing chapter numbers.** A light novel volume never becomes chapters 296, 297….
- **Marking anything read.** The user has read two chapters and owns the rest. Importing makes
  chapters available; it never moves progress or pushes to a list.
- **Writing before the user has seen the plan.** Nothing touches `/manga` or the database until the
  review step is confirmed.
- **Overwriting a chapter the library already has** without saying so in the review.

## Decided with the user

- **Scope and order** of the three projects, as above.
- **Light novel volumes enter as whole volumes**, read start to end, not as chapters.
- **Web novel chapters keep the bookmark's number** as `chapter.number`; volumes are recorded
  alongside, the way J-Novel Club records them.
- **Drag and drop in the interface**, on **the series page** (option A of the mockup: an "Import
  files" area on the series, not a separate screen that guesses the series).
- **The light novel's volume numbering is the default.** `volume.number` is always the light
  novel's volume number. The fan compilation follows it (its volume 15 covers web chapters 213–231,
  the same as light novel volume 15), so a web-novel PDF takes the number of the light novel volume
  it corresponds to, and a volume pushed to a list means a light novel volume, which is what
  MyAnimeList counts. Web and light novel volumes therefore share one number space on purpose.
- **Both editions of a volume live side by side.** The user owns light novel volumes 01–20 *and*
  web novel volumes 01–18, and wants both. A `volume` row carries its `edition` (`web` or `light`),
  and a series holds at most one row per number *per edition*. Web novel volumes are only a chapter
  range (their chapters are the files); light novel volumes are one file each. Either edition's
  volume N, once read, counts as volume N read.
- **A review step** listing each file, what it was read as (volume, chapter range or whole volume,
  edition) and the names it will produce, then one Import button.

## How it fits what exists

- **Numbers.** `chapter.number` is `Numeric(8,2)` and unique per series. Chapters keep the
  number from their bookmark (`Chapter 213` → 213).
- **Volumes.** The `volume` table (0023) already holds `number`, `first_part` and `last_part`
  and keeps volumes apart from chapters on purpose. A web-novel PDF fills the range from the
  chapters it produced. A light-novel PDF leaves the range null, so Komga places it after the
  chapters (`numberSort = 100000 + number`, `komga_scan.py`). `source_volume_id` is NOT NULL and
  unique per series, so an import needs a stable identifier of its own.
- **Files.** Chapters use `downloader/paths.py`'s chapter name
  (`{slug} - Ch.{NNNN[.f]}[ - title].epub`), and volumes its volume name
  (`{slug} - Vol.{NNNN} - title.epub`). That is the normalisation, and it is also what
  `komga_scan.adopt_book_ids`, `reconcile_with_komga` and `reconcile_with_disk` already recognise.
  EPUBs are written by `downloader/epub.py`, atomically, as today.
- **Who writes.** Only `worker-download` mounts `/manga` read-write. `api` must not write the
  library (CLAUDE.md). The upload lands somewhere both can reach, and the writing happens in a job
  on the download lane. `reader-cache` is the existing volume the two share.
- **Rows without a mapping.** Every chapter row so far comes from a source. Imported chapters have
  no `source_url`, and `download_batch` / `download_chapter` raise `PermanentError` on such a row.
  An imported chapter is born `downloaded`, with its `file_path` set, so nothing ever queues it.
- **Progress.** `progress_push` reads Komga's read state by `komga_book_id` and already understands
  volumes through `volume_progress`. It does not need to know a chapter was imported.

## Reading a PDF

- One top-level bookmark is one entry. An entry runs from its bookmark's page to the page before
  the next bookmark.
- **Numbered chapters**: a bookmark title starting `Chapter <n>` gives number `n`.
- **Prologues**: `Prologue <k>` becomes `0.<k>`. `Prologue POV` follows the last numbered prologue
  as the next fraction.
- **Unnumbered side chapters** (`POV Chapter`, `Side Story`, `Interlude` without a number) take the
  previous chapter's number plus `.5`. A second one after the same chapter takes `.6`, and so on.
- **Front matter** (`Cover`, `Characters`, `Map`) is not a chapter. Its pages go into the first
  chapter of that volume, and the cover image becomes that volume's cover.
- **Edition**: a file name starting `LN - ` or `WN - ` says which edition it is, and wins. Otherwise
  a PDF is a light novel volume when its chapter numbers restart at 1 while the series
  already has chapters (or other files in the same drop) numbered higher. Otherwise it is a web
  novel volume. The review shows which way each file was read, and the user can flip it before
  importing.
- **Volume number**: from the file name (`_15`, `Volume 19`), read as the light novel volume number, editable in the review.
- Chapter titles come from the bookmark text after the number.

## The review step

For each dropped file it shows the file name, its volume number, its edition, what it was read as
(chapter range plus side chapters, or "whole volume") and the names it will produce. It also flags:

- a file it could not read (no bookmarks, no text), which is left out;
- a chapter or volume the series already has, which is left out unless the user chooses to replace
  it;
- two files claiming the same volume.

*Designer's calls, not the user's:*

- **Replacing** an existing chapter or volume keeps reading progress whole: after the scan, Komga's
  read state is re-applied from the lists, which `komga_scan.mark_read_up_to_lists` already does.
  The list is the record of what was read, so a new Komga book id loses nothing.
- **A volume number the series already holds in the same edition** is shown as existing and left
  out unless replaced. The other edition of the same number is a separate volume and imports.
- **A generated side-chapter number that a real bookmark already holds** (a `.5` that exists as
  `Chapter 9.5`) is shown as a conflict for the user to settle, never renumbered silently.

Nothing is written until **Import** is pressed. Import enqueues the work, and the series page shows
progress the way downloads already do, over SSE.

## Left to the builder

- The PDF library, with a licence that fits an MIT repository (pypdf is already enough to read the
  bookmarks and page text; whether it keeps paragraphs and italics well enough is the builder's
  test to run on these files).
- How page text becomes chapter XHTML: paragraph detection, dropping running headers, footers and
  page numbers, keeping inline images.
- Where uploads are staged, how long they live, and how they are cleaned up.
- The job type name, how the import is split into jobs, and its retries.
- The import's `source_volume_id` scheme, and how an imported row is told apart from a downloaded
  one, if anything needs to tell them apart.
- Upload size limits. The largest file here is about 9.6 MB, and the drop holds twenty.
- The exact layout of the review on the series page, within the token rules in
  `frontend/tailwind.config.ts`.
