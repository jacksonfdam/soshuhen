# Features

## How it works

```
your lists  ──>  one canonical series  ──>  you confirm the source  ──>  chapters
(MAL, AniList, MangaBaka)                                                   │
                                                     CBZ + metadata  <──────┘
                                                            │
                                     Soshuhen's reader, Komga  ──>  any reader
```

Everything runs as background jobs. Nothing blocks the interface, and every step reports what it
is doing while it does it.

### One series, however many lists

The same manga on MyAnimeList and on AniList is one thing, not two. Soshuhen merges them into a
single series, so it maps once, downloads once, and keeps one folder — no matter how many lists
that title appears on.

### Nothing downloads without you

Two deliberate stops:

**Confirming the source.** A new entry waits on the Discover screen. Soshuhen searches the source
site and shows what it found, with covers, years and chapter counts, and you pick the right one.
An automatic guess that got this wrong would download the wrong manga for every future chapter,
so it asks once and then remembers.

**Choosing what to fetch.** Confirming a mapping says what a series *is*, not that its whole
backlog should be downloaded. You choose a chapter range, or mark the series as followed so new
chapters arrive as the source publishes them. Everything else stays catalogued, visible, and
costs you nothing.

### Downloads that behave

Chapters are fetched in batches, which keeps source sites from rate-limiting you — a batch costs
one index read instead of one per chapter.

Failures retry on a widening schedule and then stop and say why, in plain text, on the Downloads
screen. A chapter the source does not publish in your language is marked and set aside rather
than retried forever. A worker that dies mid-download hands its work back instead of losing it.

Some sites do not serve a page as a picture of the page. They cut it into tiles and shuffle them,
and only their own reader puts it back. Soshuhen reassembles those before the archive is written,
so what lands on disk is the page — not a mosaic that opens fine in Komga and cannot be read. The
check that the site sent an image at all still runs first, on the bytes as they arrived, because a
reassembled error page would otherwise start looking like a picture.

### Files a reader understands

Each chapter is written as a CBZ with a `ComicInfo.xml` inside carrying series, chapter number,
title, author, artist, genres, year and summary, pulled from your list providers.

Files land as `Series Name - Ch.0012 - Chapter Title.cbz`, zero-padded so they sort correctly,
and are written atomically — Komga never sees a half-finished download.

Already own some chapters? Drop them into the library folder. Soshuhen sees them, counts them as
present, and will not download them again.

### Importing a novel you own as PDFs

A prose series' page has an **Import files** tab. Drop the PDFs on it, or click to choose them.
Soshuhen reads each file and shows what it found before anything is written: the volume, whether it
is the web novel or the light novel, the chapters it holds, and the names the files will get in the
library. Change a volume number or an edition there if it guessed wrong, tick **Replace** on
anything the library already has, then press **Import**.

- **A web novel volume** becomes one chapter per chapter bookmark, numbered as the web novel numbers
  them across the whole work. Prologues sit before chapter 1 (0.1, 0.2…), and an unnumbered POV or
  side chapter sits just after the chapter it follows (9.5, 9.6…). The cover, character pages and
  maps go into the first chapter of the volume.
- **A light novel volume** stays whole: one book per volume, read start to end. Its chapters restart
  at 1 every volume, so they never become chapter numbers.
- **Both editions of one volume** can sit side by side. Volume numbers always follow the light
  novel, which is what MyAnimeList counts.
- A file whose name starts `LN - ` or `WN - ` is taken at its word. Otherwise a book whose chapters
  restart at 1 after the series already has later chapters reads as the light novel.

The PDFs need bookmarks and real text. A scanned book, or a PDF without bookmarks, is shown as
unreadable and left out. Importing never marks a chapter read; your lists stay where they were.

### Progress that follows you

Finish a chapter in your reader and Soshuhen writes that progress back to your lists.

It only ever moves progress forward. If a list already records a higher chapter than your reader
does, the list wins — reading somewhere else never gets undone.

### Told when something new is out

The bell in the header counts what discovery has found since you last looked. Open it to see one
line per series, such as "Frieren: 3 new chapters (128–130)". Click a line to go to the series and
mark it read, or use "Mark all as read".

What counts as new:
- A chapter a source lists for the first time, whether or not you download it.
- A J-Novel Club volume you now own. A pre-order counts from the day it is released, not before.
- New parts of a J-Novel Club volume you already have.

A series you have just mapped does not announce its whole backlog: its first discovery is
silent. The same holds when you move a series to another source, whose first listing may hold
chapters the old one never had. Read notifications are cleared after 30 days.

With a Soshuhen tab open but not in front, the same news also arrives as a desktop notification
from your browser. Turn it on with "Enable desktop notifications" at the bottom of the panel. The
switch that then appears mutes notifications in that browser without revoking the permission.

Desktop notifications use the browser's own notification support, with no push service and nothing
outside your installation. That has two consequences:
- They need the interface served over HTTPS or from `localhost`. Over plain HTTP on a LAN address
  the browser does not offer them, and the switch does not appear.
- They arrive only while a tab is open. With none open, the news waits in the bell.

## Light novels

A light novel on MyAnimeList or AniList is recognised as one and kept apart from manga. It is
searched on the prose sources, LoLoBun, Novelight and EmpireNovel, never on image sites, and you
confirm the match on Discover like any other series.

Each chapter downloads as an EPUB, not a CBZ, with the series, chapter number, title and cover
embedded, and lands in the same Komga library. Soshuhen reads it in its own novel reader (see
[Reading novels](#reading-novels)), and Komga still reads it too. Finishing a chapter in either
moves your lists forward the same way it does for manga.

LoLoBun locks most of its chapters to its own app. Those cannot be fetched and show as skipped,
rather than retrying. EmpireNovel sits behind a Cloudflare challenge and needs the `flaresolverr`
compose profile; until it is running the source stays disabled.

If a series is filed under the wrong kind, or no list says what it is, the **Format** control on the
series page switches it between Comic and Light novel. A kind set there is kept, and sync does not
change it back.

### J-Novel Club

J-Novel Club publishes many licensed light novels in weekly parts before each volume is finished.
With a Premium membership, Soshuhen downloads those parts, one EPUB per part. J-Novel Club numbers
parts across the whole series, and those numbers are the chapter numbers here.

Sign in either with `JNC_LOGIN` and `JNC_PASSWORD` in `.env`, which renews itself, or from the
J-Novel Club card in Settings. The card keeps only the sign-in token, for up to 14 days, never your
password; when it lapses the card asks you to sign in again, and downloads wait rather than fail.

A Premium member can read a part only until around the 15th of the month after its volume is
published. A series with undownloaded parts expiring within a week shows how many and when, on its
page and in the library, and the daily discovery job logs a warning. Downloading still waits for
you, as everywhere else.

J-Novel Club's terms keep Premium content to personal, non-commercial use, and each part asks not
to be turned into an EPUB. This is for reading your own membership's parts on your own Komga.

Parts often number past the chapter count MyAnimeList or AniList hold for a novel. When they do,
progress sent to your lists stops at the list's own total.

Volumes you own on J-Novel Club download by themselves, as J-Novel Club's own EPUB, for every series
mapped to J-Novel Club: buying a volume is the decision to have it. Each lands in the same Komga
series as the parts, right after the parts it collects, and J-Novel Club's file is never modified -
Soshuhen sets its number and position through Komga instead. When J-Novel Club revises a volume, the
new edition replaces the old file. Pre-orders wait until they are out. Volumes of series you have
not mapped are named in the library sync's log rather than added, since series only come from your
lists. The library is read every six hours, after a sign-in, and when you press **Sync library
now** on the J-Novel Club card; the series page lists each owned volume with where it stands.

Reading a volume in Komga - finishing its book, or finishing every part of a volume you own - moves
volumes read on MyAnimeList, AniList and MangaBaka to that volume, and chapters read to the volume's
last part. Like chapters, it only ever moves forward, and it stops at the list's own volume count.
A list that refuses the volume count still gets the chapter. Volumes a list already counts as read
are marked read in Komga too. Nothing is written back to J-Novel Club.

## The screens

### Home

The whole pipeline in one view: how many series you are actively reading, what the download queue
is doing, how many mappings are waiting on you, and how many suggestions are ready. Underneath,
the series you are part way through — each with a one-click way to record another chapter read —
alongside the newest suggestions, what the queue has just finished, and how much room is left on
the disk holding your library.

![The Home screen](images/home.webp)

### Statistics

What the library looks like as a whole, over the last 7, 30, 90 or 365 days. Totals for series
tracked, how many reached Komga, and chapters known against downloaded against read. Then the shape
of it: how your titles split across the five list states, your ten commonest genres, and which
decades they were published in.

Two panels come with a caveat printed on them rather than buried in a caption. Reading velocity is
drawn only from the day chapter events started being recorded, so a flat stretch before that is an
absence of history rather than a month of reading nothing. Time spent is an estimate and says so —
nothing in the pipeline observes how long you read, so it is chapters multiplied by a figure you set
in Settings.

A series on both MyAnimeList and AniList is counted once. It is one thing on the shelf, and counting
it twice would inflate every distribution on the screen.

![The Statistics screen](images/statistics.webp)

### Library

Every series Soshuhen knows about, with covers, which lists it came from, how many chapters you
have against how many exist, and its current state. Filter by state or by format, search by title,
sort by title, by what was updated most recently or by how far along you are, choose a page size,
choose a range to download, or follow a series.

Covers or a table, whichever reads better — the toggle sits with the rest of the controls. Above
both, the series you are furthest into sit in their own strip, so the thing you came to read is not
something you have to find first.

Every one of those controls is in the address, so a filtered, sorted page can be bookmarked and
comes back the way you left it after opening a series and pressing Back.

![The Library screen](images/library.webp)

### A series

Opening a series gives you its cover, native title, author credit, its global score and where that
places it, its synopsis and genres, the characters and related works its providers know about, and
the chapters Soshuhen has found against the ones you hold. From here you record progress — type the
chapter or step it — pick a range to download, follow the series, choose from the sources the search
found or paste a URL, and keep private notes that go nowhere near your lists.

A series no list holds yet has nowhere for a chapter to land, and says so. **Track it here** gives it
a local entry: the reading is recorded in Soshuhen and goes no further. If one of your lists later
turns out to hold the same series, the next sync carries the chapter you recorded across to it.

Three panels are worth knowing about before you need them:

**Source mapping** names the site this series is currently read from, and keeps the other candidates
the search turned up underneath it, each with how well it matched. If the mapping is wrong, the right
one is usually already on that list; re-running the search asks the sites again.

Moving a mapped series to another source shows what the move does before it is made: how far the
new source goes against what is held here, how many chapters it adds, how many that failed here it
will try again, and how many it does not list. It warns when the new source stops before where your
reading got to. Progress and list entries are untouched by a move, since they count chapters by
number. After the move, chapters already in the library stay as they are, and chapters the new
source does not list are set aside as skipped rather than fetched from the site you left.

**On a light novel, Contents** replaces the chapter list. It lists volumes, with the light novel and
the web novel apart when you have both. A light novel volume is one book with its own **Read**; a web
novel volume opens to the chapters it covers, each with its own. A volume or chapter shows as read
once your lists say so. One whose file is not in the library says that instead of offering to read.

A series with no source but with files already in the library — a novel imported from your own
PDFs, say — is **Local**. Nothing asks it for a source mapping, and it stays off the review queue;
**Find a source** on its mapping panel is there if you ever want to download more of it.

**The chapter list** shows newest first or oldest first, and narrows to the unread, the
downloaded or the bookmarked. The star on a row bookmarks a chapter to come back to. Read is never
marked here — it follows how far your lists say you got — so a bookmark is the only mark a chapter
keeps.

**Sync targets** shows, list by list, exactly what MyAnimeList, AniList and MangaBaka each record
right now — status, chapter and when it last moved. Three lists that disagree is a thing you can see
rather than a thing you deduce.

**Reading frequency** charts this series alone, and is honest about being young: it counts reading
events from the day they started being recorded and fills forward, so a series read for years can
still show nothing. The panel says so on itself rather than leaving you to infer it.

Where a provider serves nothing, the screen shows nothing. Per-chapter page counts are absent for
that reason: no source states them, and an invented figure would be worse than the gap.

The one schedule shown is observed, not stated: once a series has had a few chapters arrive after
you started following it, its header says how often they come — Daily, Weekly, Every 10 days —
from the middle gap between the last ten. It never appears for a series whose chapters all came in
its first discovery.

### Checking only when a chapter is due

Off by default, under Settings → Automation. With it on, the scheduled discovery leaves a series
alone until the day before its next chapter is expected by that rhythm, and asks every run from
then until the day after. A series running late is asked once per rhythm, and one ten releases
late is treated as on a break and asked every four weeks. A series with no rhythm yet is asked
every run, as before. Only the schedule follows it; any other discovery asks the source.

![A series](images/series.webp)

### Discover

Everything waiting on a decision, in one place: manga suggested from the anime you have watched,
the anime no relation could connect to a manga, and the series waiting for you to confirm a
source. These were three screens, and they were three stages of one question — is there a manga
here you want, and which one is it?

A card says which of the three it is — a recommendation, a series missing a source, an anime with
no manga found — in the same words as the filter chips, so the badge tells you which chip would
keep it. The order is by distance to done, so the ones a single click finishes come first and the
ones needing a manual search sit behind them. The header gives both numbers, because "171 you can
answer now" is a figure you can act on and "698 waiting" on its own is not.

Search by title, filter to any of the three kinds, sort by title or by when an item arrived, and
choose 20, 50 or 100 to a page. The page number and every other control live in the address. Two
of the three kinds have a date to sort by; an unmatched anime does not, because nothing records
when it first appeared, so those sort to the end rather than being given a date that means
nothing.

Opening one asks only for what it owes, and only for the step it can actually take. A suggestion
takes a status and optionally starts downloading; the source is not asked for, because confirming
one is decided automatically when the match is exact and goes to the review path otherwise. An
unmatched anime is searched by title when you ask — never before — and you pick the manga first
and the status second. A series waiting on a source shows the candidates the search found, and if
it found none you paste a URL on the series screen. Dismissing an item stops it being suggested
again, whichever of the three it came from.

`/discovery`, `/unmatched` and `/review` redirect here.

![The Discover screen](images/discover.webp)

### New chapters

Every chapter found at a source after its series was already being followed, grouped by the day it
turned up and then by series, for the last week, month or three months. A chapter opens straight
in the reader. A series' back catalogue never appears here: the chapters a first discovery lists,
including the first discovery after a change of source, are history rather than news.

The bell says that something arrived and forgets what it said a month after you read it; this
screen lists the chapters themselves for as long as they are in the period. Open it from **By day**
in the bell.

### Search sources

Type a title and every enabled source is asked for it at once, the results ranked by how well each
matches. A result the library already maps says so and opens that series; anything else opens on
the site. A source that did not answer in time is named above the results, so a missing title is
not mistaken for one nobody carries. Nothing is added, mapped or downloaded from here.

It searches when you press Enter, not as you type, because every search is a request to every site.
The last few searches sit under the field, in this browser only.

Reach it from the magnifier in the header, or from anywhere with **Ctrl+K** (⌘K on a Mac): the
palette jumps to any screen, opens a series by a word of its title, and offers a source search for
whatever you typed.

### Downloads

What is running right now, with live progress. What failed, with the actual error and a retry
button. What is waiting. Click any job to read its full log — no need to go looking through
container output.

### Settings

Connect your lists and see when each token expires. Tune the pipeline: how many downloads run at
once, how hard a single source may be hit, batch size, and the schedules.

![The Settings screen](images/settings.webp)

**Sources** is a list of every site Soshuhen knows how to read — several hundred of them, generated
from the Tachiyomi extension repository. Search it by name or key, or narrow it to one language.
Nothing is searched until you switch it on, and a site that is on is a site Discover will offer
candidates from.

A row that cannot be switched on says why, and the three reasons mean different things:

| What it says | What it means |
|---|---|
| *not hand-ported* | The site's upstream definition carries behaviour the generator will not guess at. It is listed so you know it exists, not because it can run. |
| *no implementation for the `<x>` template* | The site's family has not been ported to Python yet. Porting one template brings every site in that family with it. |
| *no implementation for this site* | A site written by hand rather than generated, whose code is not in this build. |

Two sources need something from you beyond a switch. A site behind Cloudflare needs FlareSolverr
running, and MangaFire additionally raises a challenge only a person can clear — see
[configuration](configuration.md).

![The source list in Settings, narrowed to one language](images/settings-sources.webp)

### Mihon backup

Under Settings → Backup. **Export** downloads a `.tachibk` file that Mihon restores: every series
with a confirmed source, under that source, with its chapters marked read up to where your lists
say, your bookmarks, and its MyAnimeList, AniList and MangaBaka links. Mihon finds each title under
an installed extension of the same name; one whose extension uses a different id shows as a missing
source, and Mihon's own migration moves it.

**Read a backup** goes the other way, and shows before it changes anything. Each title in it is
matched to a series here by the tracker it is linked to in Mihon, or else by its title. A matched
series that has no source yet takes the one Mihon read it from, when Soshuhen has that site
enabled; one that already has a source keeps it. **Import** applies that, and copies bookmarks onto
the chapters already listed here. A title no list of yours holds is reported and left out: series
come from your lists, not from a backup.

Taking the source from a backup skips the review a search would park it in. That is deliberate: the
backup records a choice you already made, and the list is shown before anything is applied.

## What it reads and writes

| Service | Role |
|---|---|
| MyAnimeList | Reads your manga and anime lists; writes status and progress back |
| AniList | Reads your manga and anime lists; writes status and progress back |
| MangaBaka | Reads your library; writes status and progress back |
| MangaDex | Searches for series and fetches chapters |
| Comick | An optional second source, self-hosted, if you run one |
| Any enabled source site | Searched for candidates, and fetched from once a mapping is confirmed |
| Komga | Stores and serves the library; reports what you have read |

## Reading

Soshuhen has a reader of its own, so the place that fetches chapters is also a place to read
them. Open any chapter from a series page, or **Continue** from Home to land where you stopped.

- **Any chapter, downloaded or not.** A chapter already in the library is read from its archive. One
  that is not is streamed from its source, and the pages you read become the download: once every
  page has loaded, the chapter is saved to the library without asking the source again.
- **Four modes.** Paged right to left, paged left to right, double page (the cover alone, then
  spreads) and long strip. Scale and background are yours to pick too.
- **Remembered per series.** A webtoon stays a long strip and a manga stays right to left. "Use
  for every series" makes the current choice the default.
- **Your place is kept.** The page you are on is saved as you read, on any device that opens the
  same Soshuhen.
- **Tablet and desktop.** Below desktop width the controls hide until you tap the middle of the
  page, with a page slider and a settings sheet at the bottom. On a desktop they stay on screen as a
  chapter pill and a tool bar, with the keyboard: arrows turn pages and follow the reading
  direction, space scrolls, `[` and `]` change chapter, `f` goes fullscreen.
- **A long strip shows how far you are.** A thin rail along the top edge fills as you go down
  the chapter, and covers none of the page.
- **The strip is as wide as you want it.** Hold Ctrl and turn the wheel (or pinch on a trackpad)
  to widen or narrow the column; Ctrl+0 puts it back to what the scale says. The width belongs to
  this browser, not to the series, because the right one depends on the screen.

Finishing a chapter moves your lists forward, never back, and marks the book read in Komga when
Komga has it.

### Reading novels

A light novel opens in a reader made for text rather than pages: the book's own words in one
column, scrolled like an e-reader, with its illustrations in place.

- **Text size and background are yours.** Seven text sizes, and a light, sepia or dark page. The
  choice holds for every novel, on every device that opens the same Soshuhen.
- **Your place is kept.** Where you stopped is saved as you scroll and comes back when you open the
  book again, or when you press **Continue**.
- **Contents** jumps to a chapter of a volume when the book has a table of contents.
- **At the end**, mark the volume or chapter read, or go straight on to the next one, which marks
  this one read on the way. A light novel volume reaches your lists as a volume read; a web novel
  chapter as a chapter. Either only ever moves them forward.

Komga and any Komga-compatible app on iOS or Android remain readers of the same library. Progress
meets in your lists: what you read in Komga reaches them through `progress_push`, what you read
elsewhere reaches them through that app's own tracker, and Komga is brought up to the lists each time
it indexes the series.

## Android app

An Android app for phone and tablet lives in `mobile/`. It talks only to your Soshuhen server on the
home network, and never to a source site or a list provider: covers come from the server too.

- **Finding the server.** On first run it scans the Wi-Fi it is on for a Soshuhen server and lists
  what answers. If none does, type its address (`192.168.1.20` or `192.168.1.20:8080`). The phone
  reaches the server by its LAN IP, not by a name like `soshuhen.test`, which only your computer
  knows. If the server's address changes later, the app finds it again by itself.
- **The library.** The same layout as the web: Continue reading, the list-status tabs, and the
  cover grid with unread counts. Pull down to refresh. If the server stops answering, what was
  loaded stays on screen with a notice.
- **A series.** How far you have read, how many chapters the server holds, and every chapter with
  read or unread and whether it is downloaded. On a tablet the series opens beside the grid.

- **Setting up the phone.** After the server, the app asks where chapters should be kept and opens
  the system folder picker; the library does not open until a folder is picked. It then asks once
  whether it may tell you about new chapters, and once whether it may run in the background without
  battery limits (Samsung and others put apps you have not opened lately to sleep, and a sleeping
  app copies nothing). "Not now" and "Skip" are not asked again; both stay in Settings.
- **Keeping a series on the device.** Turn on **Keep on this device** on a series and the app copies
  every chapter the server has downloaded into `<your folder>/Soshuhen/<series>/`, as the same CBZ
  files the server holds, readable by any comic app. It copies about once an hour while the phone is
  on your home Wi-Fi, and right away when you pull to refresh. A long copy shows its progress in a
  notification; when it is done, one notification says which series got new chapters, and the
  **Updates** tab lists them.
- **Reading.** The reader has the web's four modes (paged left to right or right to left, vertical
  strip, and double page on a wide screen) and its settings, and reads from the device when the
  chapter is there and from the server otherwise. The volume buttons turn pages; that and inverting
  them are switches in Settings.
- **Offline.** Away from home the library shows what it last saw, covers included, with "Offline.
  Showing the last sync." Every chapter on the device opens as usual, at the page where you
  stopped, and a series' **Continue** leads there too.
- **Progress goes home.** Chapters you finish, and where you stopped, are kept on the phone and sent
  to the server the next time it is reachable, so your lists move forward as if you had read at
  home. Re-reading an earlier chapter never moves a list backwards.
- **Settings.** The server, the folder with **Change folder** (chapters already copied stay where
  they are; new ones go to the new folder), whether background copies are unrestricted with a way
  to the battery settings, whether notifications are on with a way to Android's notification
  settings, and the volume buttons. **Change server** to a different Soshuhen
  installation starts the device over: which series are kept, which chapters were copied and any
  reading not yet sent are forgotten, since they name the old server's series. The files stay in
  the folder; a chapter the new server holds byte for byte is taken up again without a copy.

Nothing is ever deleted unless you ask. Turning **Keep on this device** off asks whether to keep the
files or delete them, and keeps them unless you choose **Delete**; **Delete read chapters** and a
chapter's own **Delete** remove only what they say. The app never prunes the folder, never removes a
file it did not copy, and never touches the server's library.

Building and installing: `mobile/README.md`.
