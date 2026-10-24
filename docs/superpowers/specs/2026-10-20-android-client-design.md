# Android client

Date: 2026-10-20
Status: approved design, awaiting implementation plan

## Intent

The user reads at home and on the way to work. At home the web interface at `/library` does what
they want: pick a series, see how far they have read and which chapter is next, read it, and have
that progress reach their lists. On the train there is no server, so there is no reading.

The Android client is that same flow on a phone and a tablet, with one addition: the series the user
marks are copied to the device, so they can be read with no network at all, and whatever was read
away from home reaches the server the next time the device is back on the home network.

It is a reader and a mirror of the server's library. It is not a downloader.

## Goals

- The web library's flow on Android, responsive across phone and tablet: library grid, series
  detail with read/unread state, a reader with the web reader's modes.
- Series the user marks in the app are imported to a folder the user picks (internal storage or SD
  card). Everything already downloaded on the server for a marked series is copied, and new chapters
  are copied in the background whenever the device is on the home network.
- Reading works fully offline from the imported archives.
- Progress made in the app, online or offline, reaches the server and, through it, the lists.
- The app finds the server on the local network by itself, and the user can type its address
  instead.
- An app icon, a splash screen, and one kind of notification: new chapters imported.

## Non-goals

- **The app never fetches anything from a source site or a list provider.** Downloading stays the
  server's job (`download_batch`, `download_chapter`). The app only copies archives the server has
  already written to `/manga`. It does not stream chapters the server has not downloaded.
- No prose (EPUB) support for now. Prose series do not appear as importable, and the reader handles
  CBZ only. *(Superseded on 2026-10-24: `2026-10-24-android-prose-reader-design.md` adds novels.)*
- No server administration: no mapping review, no download requests, no settings beyond the app's
  own. The web interface keeps those.
- No access from outside the home network (no tunnel, no relay, no cloud).
- No iOS build now. The code is structured so one can be added later (see Stack).
- No automatic deletion of anything on the device.

## Anti-goals

These would make the app a failure even if it technically worked:

- Anything leaving the device for anywhere but the Soshuhen server on the home network, covers
  included. An app that quietly hits source sites or CDNs defeats the reason the server exists.
- Offline reading that silently moves progress **backwards** on the server or the lists when the
  device reconnects.
- Deleting a chapter the user did not ask to delete, including when they unmark a series.
- A tablet layout that is the phone layout stretched.

## Decisions taken with the user

| Question | Decision |
|---|---|
| Platform | Kotlin Multiplatform with Compose Multiplatform, latest stable versions. Android is the only target now; iOS is a possible later target, not a goal. |
| Base layout | The web library (option A): one screen with a "Continue reading" row on top, the list-status tabs, then the cover grid. Not Mihon's split into Library / Updates / History. |
| What gets imported | Only the series the user marks in the app. |
| New chapters | Copied by themselves in the background when the device is on the home network. |
| Deleting | Imported chapters stay until the user deletes them. The app never deletes on its own. |
| Prose | Comics (CBZ) only for now. |
| Reader controls | The web reader's four modes. Volume keys turn the page in paged modes and scroll in the long strip. |
| Notifications | Only "new chapters imported". |
| Icon | Option C: three manga panels with a green arrow (server to device), palette from the web tokens. |
| Covers | Served by the Soshuhen server (server change 3). Nothing leaves the home network, covers included. |
| Devices | Samsung phone and Samsung tablet. **minSdk 29 (Android 10).** |
| Installation | Built locally (Android Studio or `./gradlew installRelease`) and installed over USB or ADB. No store, no CI release. |
| Server address | The phone always reaches the server by its LAN IP over plain HTTP on port 8080. `https://soshuhen.test` exists only on the user's computer (a local HTTPS proxy) and does not resolve on the phone. |

## Constraints found in the codebase

Facts the design rests on, read from the repository on 2026-10-20:

- **No authentication.** The API has no login, token or key (`backend/app/api/deps.py`). Any device on
  the LAN can call it. The app adds none and needs none.
- **Only port 8080 is published.** `web` (Caddy) serves the SPA and proxies `/api/*` to `api:8000`;
  `api` has no `ports:` mapping (`docker-compose.yml`, `frontend/Caddyfile`). The app talks to
  `http://<ip>:8080/api/...`.
- **No whole-archive endpoint.** The reader serves one page at a time
  (`GET /api/reader/chapters/{id}/pages/{index}`). `/manga` is mounted read-only into `api`.
- **`chapter.file_path`** is set when a download finishes and exposed by `GET /api/series/{id}`.
  No size, hash or page count is stored.
- **Nothing advertises the server.** `GET /api/health` returns `{"status":"ok"}` only.
- **Progress endpoints:**
  - `PUT /api/reader/series/{id}/position {chapter_id, page}` upserts one row per series with no
    guard of any kind.
  - `POST /api/reader/chapters/{id}/complete` floors the number, applies `forward_only`, queues
    `progress_write` (one job per series, raised rather than duplicated) and `komga_read_progress`.
    A refusal returns `progress_queued: false`, not an error.
- **Reader preferences** are stored per series on the server: `mode ∈ {paged_ltr, paged_rtl,
  long_strip, double}`, `scale ∈ {fit_width, fit_height, fit_screen}`, `background ∈ {black, gray,
  white}` (`GET/PUT /api/reader/series/{id}/prefs`, `PUT /api/reader/defaults`).
- **Covers** are `series.meta.cover_url`, an external URL from the list provider's CDN. The server does
  not host them.
- **Plain HTTP.** Android blocks cleartext traffic by default from API 28. The app must allow it.
  A `domain-config` cannot match IP ranges, so the setting is app-wide.

## Server changes

Four, all small. Only the fourth changes what the database stores. They belong in the same branch as the app so
both move together.

### 1. Identity endpoint

`GET /api/identity` returns:

```json
{ "app": "soshuhen", "version": "0.1.0", "instance_id": "8c0e…", "name": "Soshuhen" }
```

- `instance_id` is a UUID generated once and kept in `setting` (via `settings_store`), so it is
  stable across restarts and IP changes. This is what lets the app recognise *its* server after DHCP
  hands the machine a new address, and tell it apart from a second installation.
- `app == "soshuhen"` is what the LAN scan looks for. `/api/health` alone would match any service
  that happens to answer `ok`.

### 2. Archive endpoint

`GET /api/chapters/{id}/archive` streams the chapter's CBZ from `file_path`.

- 404 when the chapter has no `file_path` or the file is missing. 409 for prose (EPUB). *(Since
  2026-10-24 a prose chapter's EPUB is served instead; see the prose reader design.)*
- The path is resolved and checked to sit inside `library_path`, as the reader's archive path
  already does.
- `Content-Length` set and `Range` honoured, so an interrupted copy over a weak Wi-Fi resumes rather
  than restarting. Starlette's `FileResponse` provides both.
- An `ETag` (size and mtime is enough) so the app can tell that a chapter was rebuilt on the server
  and re-import it.

### 3. Cover endpoint

`GET /api/series/{id}/cover` returns the series' cover image.

- On the first request the server fetches `meta.cover_url` once, stores the bytes on disk keyed by a
  hash of the URL, and serves them from there afterwards. A changed `cover_url` is a new key, so a
  new cover replaces the old one without any invalidation logic.
- The cache lives on a volume `api` can write. `reader-cache` already is one, under a `covers/`
  subfolder; `/manga` is not, and `api` never writes it. **(Builder's call.)**
- `ETag` and `Cache-Control` so the app refetches only when the cover changed.
- 404 when the series has no `cover_url` or the fetch failed. The failure is not cached forever, so
  a later request can try again.

The web interface can move to this endpoint later. That is not part of this work.

### 4. Position writes that carry their time

Offline reading replays positions later, and the position endpoint has no guard. A position the app
recorded on the train at 08:10 must not overwrite one the web recorded at 20:00 when the phone
reconnects at 21:00.

`PUT /api/reader/series/{id}/position` gains an optional `read_at` (ISO 8601, UTC). When present, the
upsert only applies if `read_at` is later than the stored `updated_at`, and the stored `updated_at`
becomes `read_at`. When absent, behaviour is unchanged, so the web reader is unaffected. The response
says whether it applied.

`POST /api/reader/chapters/{id}/complete` gains the same optional `read_at`. `forward_only` already
makes a late, older completion harmless to the lists; `read_at` is for honesty elsewhere. It is
passed through to `progress_event.created_at`, which feeds `reading_frequency` and the `last_read_at`
that orders "Continue reading". Without it a week of train reading would be recorded as one evening.
**(Builder's call.)**

In both endpoints a `read_at` later than the server's clock is clamped to the server's `now()`, so a
phone whose clock runs fast cannot win every replay. **(Builder's call.)**

## The app

### Stack

Kotlin Multiplatform, Compose Multiplatform, Material 3 with the adaptive layouts
(navigation suite, list-detail). Shared code in `commonMain`; Android-only code (storage access,
WorkManager, notifications, network scan, volume keys) behind interfaces in `androidMain`, so an iOS
target later means writing the platform side, not restructuring.

Exact library versions are pinned in a version catalogue and must be the latest stable at the time
the work starts, verified from each project's release page or Maven metadata, not from memory. A
verified table as of 2026-10-20 is in the appendix.

The code lives in `mobile/` in this repository. **(Builder's call, recorded here.)** One branch can
then carry the server endpoints and the client that uses them, and the existing CI can build both.

### First run

1. **Find the server.** The app reads the device's Wi-Fi address and prefix, then probes every host
   in that subnet on port 8080 for `GET /api/identity` with a short timeout and bounded concurrency.
   Every answer with `app == "soshuhen"` is listed with its name, address and version. For a typical
   `/24` this finishes in a few seconds.
2. **Or type it.** A field accepts `192.168.1.20`, `192.168.1.20:8080` or a full `http://` URL. The app
   checks `/api/identity` before accepting it.
3. **Pick the folder.** The Storage Access Framework folder picker (`ACTION_OPEN_DOCUMENT_TREE`),
   which offers both internal storage and the SD card. The app keeps the persisted URI permission.
4. **Allow notifications** (`POST_NOTIFICATIONS`, Android 13+). Declining is allowed; imports still
   happen.

The app stores the server's `instance_id` and last known address.

### Being "at home"

The app is at home when the stored address answers `/api/identity` with the stored `instance_id`. It
does not use the Wi-Fi network name. When the stored address does not answer and the device is on
Wi-Fi, the app rescans the subnet for the same `instance_id` and updates the address if it finds it.
No rescan happens on mobile data.

### Library

The web library, adapted:

- **"Continue reading"** row at the top: series ordered by `last_read_at`, with the next chapter and
  a progress bar.
- **Status tabs** from the list status, plus one tab the web does not have: **"On device"**, the
  marked series only.
- **Cover grid.** Each cover shows a green ⬇ badge when the series is marked and its archives are on
  the device, and an unread count. The count is the web's arithmetic, taken from `GET /api/series`
  alone: `max(total_chapters, known) - progress` (`frontend/src/features/library/useLibrary.ts`,
  `CoverCard.tsx`). No per-series request is needed to draw the grid.
- Search by title.
- Away from home the library shows the last synced snapshot. Unmarked series still appear but are
  shown as unavailable; tapping one explains why.

The bottom bar is **Library · Updates · Settings**. *Updates* lists recently imported chapters, newest
first, and is where the notification lands.

### Series detail

Cover, title, "read up to chapter N · M on the server", a **Continue chapter X** button, the
mark/unmark toggle, and the chapter list. Each chapter shows read/unread and one of *on device*,
*on server* (downloaded there, not yet copied) or *not downloaded*. A chapter on the device can be
deleted from here, singly or as "delete read chapters". Unmarking asks whether to delete what is on
the device; the default keeps it.

Only chapters whose server `state` is `downloaded` and that have a `file_path` are importable.

### Reader

Same modes and preferences as the web reader, read from and written to the server's per-series
preferences, falling back to the server defaults:

- paged left-to-right, paged right-to-left, long strip, double page (offered on wide screens);
- fit width, fit height, fit screen; black, gray or white background.

Pages are read straight from the CBZ on the device, sorted the way `backend/app/reader/archive.py`
sorts them (natural order), so page *n* in the app is page *n* on the server and positions mean the
same thing in both.

Controls: tap the middle to show the chrome, tap the edges to turn (direction follows the mode),
pinch to zoom, a page slider, previous/next chapter. **Volume keys** turn the page in paged modes and
scroll by a screen in the long strip; Settings has a switch to invert them and one to turn them off.
Keys are consumed only while the reader is in front.

Reaching the last page counts as finishing the chapter, exactly as the web reader does.

A chapter that is on the server but not on the device can be read at home through the existing page
endpoints, the same as the web. Away from home only device chapters open.

### Progress and the offline queue

Every reading event is written first to a local queue, then sent:

- `position` (series, chapter, page, `read_at`) as the reader moves, coalesced to the latest per
  series;
- `complete` (chapter) when a chapter ends;
- `prefs` (series, mode, scale, background) when changed, coalesced per series.

At home the queue drains immediately. Away, it waits and drains in order when the app is next at
home, either in the background sync or when the app opens. Positions and completions carry `read_at`
(server change 4); completions also rely on `forward_only`. A failed send stays in the queue and is retried; a 4xx that
can never succeed (for example a chapter deleted on the server) is dropped and logged.

The app also updates its local view at once: finishing chapter 139 offline shows "read up to 139" on
the device even before the server hears about it.

### Background import

A periodic WorkManager job (every hour or so, with a network-connected constraint, unmetered
preferred) plus a run when the app opens:

1. Check "at home". If not, stop.
2. Drain the progress queue.
3. Refresh the library snapshot (`GET /api/series`) and, for each marked series,
   `GET /api/series/{id}` for its chapters.
4. For each importable chapter not on the device, or whose `ETag` changed, download
   `GET /api/chapters/{id}/archive` to a temporary file in the chosen folder, check it opens as a zip,
   then rename it into place. A partial file is resumed with `Range` on the next run.
5. Post one notification per series with new chapters ("Frieren: 3 new chapters").

A large first import (a marked series with hundreds of chapters) runs as a foreground worker with a
progress notification, since Android may otherwise stop it. That is the only other notification the
app shows, and only while it is copying. Android 14+ requires the `dataSync` foreground-service type
for this, and Android 15 limits that type to about six hours a day, so the import works in batches
that each finish well inside the limit and the next periodic run picks up the remainder.

**Import failures** (device full, SD card removed, folder permission revoked, server answered with
an error) do not raise a notification: the user asked for one kind only. They show as a banner at
the top of Library and Updates, naming the cause and the fix ("SD card not found: reinsert it or
pick another folder in Settings"), until the next run succeeds. A run that fails for one of these
reasons stops rather than retrying chapter after chapter. **(Builder's call.)**

### Storage layout

Inside the picked folder:

```
<picked folder>/Soshuhen/<series slug>/<the server's file name>.cbz
```

using the file name from `file_path`, so the folder reads the same as `/manga` and a file manager
or another reader (Mihon's local source, for instance) can open it. The app's own index of what is on
the device (series, chapter id, file URI, `ETag`, size, imported at) is in its local database, not in
the folder. Losing the index is recoverable by re-matching file names against the server's chapter
list.

### Covers

Covers come from the server's cover endpoint (server change 3), never from `cover_url` directly, and
are cached on the device so the library looks right offline. **(Decided by the user: nothing leaves
the home network.)** A series whose cover the server could not fetch shows a placeholder built from
its title.

### Notifications

One channel, "New chapters", for chapters imported in the background, grouped per series. Tapping
opens the series. A second, low-importance channel exists only for the progress of a long import.

### Icon and splash

Option C from the mockups: three manga panels in the web palette (`#a078ff`, `#d0bcff`, `#6d3bd7`)
on the background colour `#10141a`, with a green (`#4edea3`) downward arrow. An adaptive icon
(foreground and background layers, plus a monochrome layer for themed icons) and the Android 12+
splash via `core-splashscreen`, the icon centred on `#10141a`. The source SVG lives in the repository
next to the app.

### Theme

Dark, using the web's token values (`frontend/tailwind.config.ts`) carried into a Material 3 colour
scheme. The values are copied into one Kotlin theme file, the app's equivalent of the Tailwind
config. No colour literal anywhere else.

### Android 10 to 17 on Samsung

minSdk 29, targetSdk and compileSdk 37. What that range means for this app:

- **Notifications.** `POST_NOTIFICATIONS` is asked for only on Android 13+. Below that, notifications
  are allowed by default.
- **Splash.** `core-splashscreen` gives the Android 12 splash API on 10 and 11 as well, so one
  implementation covers the whole range.
- **Foreground import.** `foregroundServiceType="dataSync"` is declared in the manifest (the
  attribute exists from API 29). Android 14+ requires it, and the six-hour daily limit applies from
  Android 15 (see Background import).
- **Storage.** The folder is always chosen through the Storage Access Framework, which works the same
  for internal storage and an SD card from Android 10 up. No `MANAGE_EXTERNAL_STORAGE`, no legacy
  storage flag.
- **Samsung battery management.** One UI puts apps it considers unused to sleep, and a sleeping app's
  WorkManager jobs stop running. That would break "new chapters arrive by themselves". Settings shows
  whether the app is exempt from battery optimisation and opens the system screen to set it to
  *Unrestricted*. The first-run flow offers this once, after the folder. **(Builder's call.)**

### Responsiveness

Window size classes decide layout, not device type:

- **Compact** (phone portrait): bottom bar, three-column grid, detail as its own screen.
- **Medium/expanded** (tablet, phone landscape): navigation rail, wider grid, list-detail with the
  series detail beside the grid. The reader offers double-page mode.

## Left to the builder

- Database and settings libraries (Room KMP or SQLDelight; DataStore), dependency injection, HTTP
  client, image loading, navigation library: whatever is current and multiplatform.
- Scan concurrency, timeouts, and how to read the subnet on Android.
- Sync interval and retry backoff, within "hourly-ish, at home only".
- Exact chrome and gesture details of the reader, within the web reader's behaviour.
- Test strategy for the app. Server changes follow the repository's existing pytest suite against a
  real Postgres.
- How CI builds the Android module. CI only checks that it compiles and that its tests pass; it
  produces no installable artefact and holds no signing key.

## Building and installing

The user builds on their own machine. A release build is signed with a keystore that lives outside
the repository (path and passwords in `~/.gradle/gradle.properties` or `mobile/keystore.properties`,
gitignored). A missing keystore falls back to the debug signature, so a fresh clone still builds.
The keystore must stay the same from one build to the next, or Android refuses to install over the
existing app. Uninstalling to get past that loses the app's database and its unsent progress queue;
the imported archives survive in the picked folder and are re-matched (see Storage layout). `mobile/README.md`
says this and gives the one-time `keytool` command. **(Builder's call.)**

## Appendix: library versions

Latest stable releases as of 2026-10-20, taken from Maven Central and Google Maven metadata and from
the projects' GitHub release pages. Recheck before the work starts.

| Library | Version | Note |
|---|---|---|
| Kotlin (and Compose Compiler plugin) | 2.4.21 | The Compose Compiler plugin must match Kotlin. |
| KSP | 2.3.12 | Numbered separately from Kotlin since 2.3.0. |
| Compose Multiplatform | 1.12.2 | Supports Android API 21+. |
| CMP Material 3 + `material3-adaptive-navigation-suite` | 1.12.0-alpha03 | See below. |
| CMP `material3.adaptive` (layout, navigation / list-detail) | 1.3.0 | Stable. |
| `org.jetbrains.androidx.navigation:navigation-compose` | 2.10.0-rc01 | See below. Navigation 3 (1.2.0-rc01) is the alternative. |
| `org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose` | 2.11.0 | |
| Android Gradle Plugin | 9.4.1 | Needs Gradle ≥ 9.6.0 and JDK 17. |
| Gradle wrapper | 9.7.0 | The highest version both AGP 9.4 and Kotlin 2.4.21 accept. 9.8.2 is newer but untested with Kotlin. |
| Ktor client | 3.6.0 | |
| kotlinx-coroutines / serialization / datetime | 1.11.0 / 1.12.0 / 0.8.0 | |
| Room (`androidx.room`) / Room 3 (`androidx.room3`) | 2.8.5 / 3.0.3 | Builder picks. Room 3 is a new package. |
| `androidx.sqlite:sqlite-bundled` | 2.7.1 | |
| SQLDelight (alternative to Room) | 2.4.1 | |
| DataStore | 1.2.1 | |
| WorkManager | 2.12.0 | |
| Coil 3 | 3.6.3 | |
| Koin | 4.2.2 | |
| `core-splashscreen` | 1.2.0 | |
| `documentfile` | 1.1.0 | |
| Okio (`FileSystem.openZip`) | 3.18.2 | KMP zip reading. |
| compileSdk / targetSdk | 37 | Google Play requires target ≥ 36 from 2026-08-31. |

Two places where "latest" and "stable" disagree. Both are **builder's calls**:

- **CMP Material 3 and navigation have had no stable release that matches CMP 1.12.** JetBrains pairs
  each CMP release with a pre-release of each (material3 1.12.0-alpha03, navigation 2.10.0-rc01), and
  that pairing is what its release notes test. The last stable ones (material3 1.9.0, navigation
  2.9.2) predate CMP 1.12 and are untested with it. Use the pairing from the CMP release notes.
- **AGP 9.4.1 is newer than the AGP range Kotlin 2.4.21 has been tested with** (up to 9.3.1). Start
  with 9.4.1 and Gradle 9.7.0. If the multiplatform build fails because of the pairing, drop to AGP
  9.3.3 and record why.
