# Profiles

Date: 2026-11-25. Extends `2026-10-20-android-client-design.md`.

## Intent

One Soshuhen server serves one household, not one person. The owner reads 16+ manga; their
14-year-old daughter reads her own. Each person wants their own library, their own list accounts
and their own reading progress, while the server keeps one copy of every file.

The Android app opens on a profile picker, in the style of Netflix or Crunchyroll: an avatar and
a name per profile, with an optional PIN of up to six digits. Picking a profile shows that
person's library and nothing else.

**The threat model is a wrong tap, not a determined user.** The PIN stops the daughter opening
her parent's profile by accident. It is not access control: the API stays open, as
`docs/configuration.md` ("The stack has no authentication of its own") already describes, and
she is not expected to call it directly. Nothing in this design should be presented as
security.

**The age limit comes from the lists, not from ratings.** A profile's library holds only the
series on that profile's own lists. The daughter's lists hold what she chose, so the parent's
16+ titles never reach her screen, and no series needs an age rating. Soshuhen stores none, and
this design adds none.

## Goals

- A `profile` table on the server: name, avatar, optional PIN, and whether the profile manages
  the server.
- Per profile: list accounts (MyAnimeList, AniList, MangaBaka, the local list), list entries,
  reading position, reader preferences, bookmarks, progress history, and which notifications
  have been read.
- Shared by all profiles: series, mappings, chapters, volumes, files, the queue, settings and the
  source catalogue. A series on two profiles' lists is one `series` row, mapped and downloaded
  once.
- The Android app: a profile picker on launch, a PIN pad for profiles that have one, a way to
  switch profiles, and every request sent as the chosen profile.
- The web interface: unchanged screens acting as the managing profile, plus a Profiles section in
  Settings to create, edit and delete profiles and to connect each profile's list accounts.
- An upgrade that turns today's installation into a single managing profile with nothing lost
  and nothing changed for the owner until a second profile is added.

## Non-goals

- Authentication, sessions, or enforcing anything server-side by profile. The API trusts the
  profile the client names.
- Age ratings, content filters, or hiding mature titles from a shared library.
- A profile picker in the web interface. The web is the owner's management console.
- Komga per profile. Komga stays one account, tied to the managing profile.
- Search, title requests, the local list and anime-based suggestions for non-managing profiles in
  this version. A non-managing profile's library comes from her remote lists only.
- Custom uploaded avatar images (a follow-up; v1 ships a fixed set).
- Brute-force protection on the PIN.

## Anti-goals

- **One profile's reading moving another profile's lists.** Every list write (progress, status,
  notes) goes to the tokens of the profile that made it. A daughter's chapter must never advance
  the parent's MyAnimeList.
- **The daughter seeing a series that only the parent's lists hold**, in the library, the updates
  screen, notifications or the reader's resume.
- **A series downloaded twice** because two profiles hold it.
- **The owner's data moving or disappearing on upgrade.**
- **Calling the PIN security** in the interface or the docs.

## Constraints

- Backend rules from `CLAUDE.md` hold: only `handlers/` and `api/reader_service.py` write;
  provider and source edges stay pure; ask providers for capabilities, never iterate the enum.
- Migration `0033`, chained after `0032_job_rerun_requested`. One migration, so a branch cannot
  land half the scoping.
- The Android app keeps its offline guarantee: progress read offline is queued in the outbox and
  sent later, now as the profile that read it.
- Komga's read marks (`progress_push`, and `komga_scan` marking books read up to list progress)
  flow between Komga and the managing profile only.

## Approaches

**A. Profiles inside the one server (chosen).** A `profile` table, a `profile_id` column on the
per-person tables, and the app naming its profile on every request. One database, one queue,
one download per series. Costs a wide backend change: every query on the per-person tables is
scoped, and the per-person handlers run once per profile.

**B. One server per person (rejected).** A second Soshuhen stack for the daughter, with the app's
existing server switch acting as the profile picker. Almost no backend change, but two databases
and two queues: a series both read is mapped and downloaded twice, or both stacks share `/manga`
and fight over the same files, and her mappings are managed from a second interface.

**C. A shared list with a filter (rejected).** Keeping one set of list accounts and filtering
what each profile sees. Fails the request outright: the daughter's profile must sync her own
accounts.

The owner chose A.

## Design

### Server: the `profile` table

`id`, `name`, `avatar` (key into the bundled avatar set), `pin_hash` (nullable),
`is_manager` (boolean), `created_at`, `position` (order on the picker).

- Exactly one managing profile. The migration creates it from today's installation; deleting it
  is refused. *(Call: one manager keeps "who confirms mappings" unambiguous; promoting another
  profile can come later.)*
- PIN: 4 to 6 digits, stored as a salted hash (`hashlib.scrypt`, stdlib). `GET /api/profiles`
  returns `has_pin`, never the hash. `POST /api/profiles/{id}/unlock` with the digits answers
  yes or no. *(Call: 4-digit minimum, since a 1-digit PIN does not stop a wrong tap. Hash even
  though the threat model does not demand it, because it costs nothing and a plaintext PIN in a
  backup is a habit worth not starting.)*

### Server: how a request names its profile

The header `X-Soshuhen-Profile: <id>`. A request without it is the managing profile, so the web
interface, scripts and the MCP server keep working unchanged. An id that does not exist is a
400, never a silent fallback, so a deleted profile left selected on a phone fails loudly.

A FastAPI dependency in `api/deps.py` resolves it once per request; routes and
`reader_service.py` take the resolved profile id rather than reading the header themselves.

### Server: what becomes per profile

| Table | Change |
|---|---|
| `provider_token` | Key becomes `(profile_id, provider)` |
| `list_entry` | `profile_id`; unique becomes `(profile_id, provider, provider_media_id)` |
| `reading_position` | Key becomes `(profile_id, series_id)` |
| `series_reader_pref` | Key becomes `(profile_id, series_id)` |
| `progress_event` | `profile_id` |
| `chapter.bookmarked` | Moves to a new `chapter_bookmark (profile_id, chapter_id)` table |
| `notification.read_at` | Moves to a new `notification_read (profile_id, notification_id, read_at)` table |

Notifications themselves stay per series, as now. A profile sees a notification when the series
is in its library.

`anime_entry`, `suggestion` and `setting` stay as they are and belong to the managing profile.
The J-Novel Club token in `setting` is the manager's.

**A profile's library** is the set of series with at least one `list_entry` for that profile.
The managing profile also sees every series that no profile's list holds (imported PDFs, J-Novel
Club volumes), so the owner's phone library looks as it does today minus series that only the
daughter's lists hold. *(Call: the alternative, the manager seeing everything, puts the
daughter's titles in the owner's phone library.)*

**The web is a management console and sees every series.** `GET /api/series` takes
`scope=all`, which the web interface always sends; without it the answer is the requesting
profile's library, which is what the app gets. Review queue, mappings, jobs, downloads, bulk
status and the series page all work on any series. *(Call, from the builder check: the web
library is where removal, bulk status and download ranges live, so hiding the daughter's series
there would leave them unmanageable.)*

**Joining series across profiles.** `list_sync` already joins entries whose normalised titles
overlap into one series. That matching runs across all profiles' entries, so the daughter's
AniList entry for a title the owner also reads joins the existing series and its mapping.

### Server: credentials for a second profile

- **MyAnimeList and AniList** use the existing OAuth flow, started from the web Settings'
  Profiles section for a chosen profile. The OAuth `state` row records the profile id alongside
  the verifier; the callback stores the token on that profile. The registered redirect URL does
  not change. The daughter signs in to her own account in that browser tab.
- **MangaBaka** today reads its key from the environment (`static_credential()`). That key stays
  the managing profile's. Another profile's MangaBaka key is entered in its Profiles section and
  stored in `provider_token` as that profile's access token. *(Call: a provider with a static
  credential answers from it only for the managing profile.)*
- `DELETE /api/auth/{provider}` disconnects the provider for the profile the request names.

### Server: jobs

- `list_sync`, `progress_write`, `status_write`, `notes_write` and `progress_events` carry
  `profile_id` in their payload, and their dedupe keys include it. The cron scheduler enqueues
  `list_sync` once per profile that has a syncing provider connected, asking the providers for
  capabilities as today.
- `progress_push` and the read marks `komga_scan` applies run for the managing profile only.
- The reader finishing a chapter writes progress to the lists of the profile that read it, and
  marks the book read in Komga **only** when that profile is the manager.
- Finishing a volume (`POST /api/reader/volumes/{id}/complete`) reaches lists today only through
  Komga (`komga_read_progress`, then `progress_push`). For a non-managing profile it records the
  reading position and enqueues nothing. *(Call, from the builder check: volumes come from
  J-Novel Club and PDF imports, both the owner's, so a daughter finishing a volume is an edge
  case; a direct volume-to-list write is a follow-up, not v1.)*
- `match_search`, `chapter_discover`, downloads, `komga_scan` itself, `media_enrich` and
  `suggest_build` are shared and unchanged, apart from `suggest_build` reading the manager's
  entries only.

### Server: removing a series, and deleting a profile

Today `app/series_removal.py` is the web library's Remove action: it deletes the `series` row
(cascading mappings, chapters and candidates), every `list_entry` of the series, and writes
tombstones to `removed_entry` keyed by `(provider, provider_media_id)`, which `list_sync`
honours forever after. With profiles that would let one person's removal erase another's series
and block it from ever syncing back. *(Call, from the builder check:)*

- **Removal is per profile.** `removed_entry` gains `profile_id`, and the key becomes
  `(profile_id, provider, provider_media_id)`. Removing a series deletes the requesting
  profile's entries and writes that profile's tombstones only.
- **The series row and its files go only when no profile holds it any more.** If another
  profile still has an entry, the series, its mapping and its files stay, and it leaves the
  remover's library only.
- **The owner removing from the web** acts as the managing profile, so a series the daughter
  also reads stays for her.
- **Deleting a profile** removes its tokens, entries, tombstones, reading positions,
  preferences, bookmarks, notification reads and progress history, then applies the rule above
  to each series it held: a series no remaining profile holds is removed as today.
- The manager's library still includes series no profile's list holds (imported PDFs, J-Novel
  Club volumes); a series is not kept merely because an entry was removed.

### Server: backup

`routes_backup.py` exports and restores profiles and every new `profile_id` column. A backup
from before this version restores into the managing profile.

### Android app

- **Picker.** On cold start, when the server reports more than one profile, the app shows the
  picker: avatar grid, names, a lock badge on profiles with a PIN. With one profile it goes
  straight in, so a single-person install looks unchanged. A "Switch profile" entry in Settings
  returns to the picker.
- **PIN pad.** Six slots, entry checked with `/unlock`. A wrong PIN shakes and clears. No
  lockout.
- **Requests.** The API client adds `X-Soshuhen-Profile` to every call.
- **Device data.** The device database's per-person rows (`marked`, `outbox`, `snapshot` and the
  reading state the reader keeps) gain a profile id, so two people sharing a tablet keep separate
  marks and queued progress. Downloaded files on the device are shared by path: a chapter both
  profiles marked is stored once. Outbox entries are sent with the profile they were recorded
  under, even if the app has since switched.
- **Deleting device files.** `DeviceLibrary.unmark(deleteFiles = true)` and `deleteRead` delete
  a file only when no other profile on the device has it marked. *(Call, from the builder check:
  otherwise the parent clearing their own reads deletes the daughter's unread offline copies.)*
- **Offload.** The offload question deletes server files every profile depends on, so the app
  offers it on the managing profile only.

### Web interface

- No picker; every request goes without the header and acts as the managing profile.
- Settings gains a **Profiles** section: list, create, rename, choose avatar, set or clear PIN,
  reorder, delete (with a confirmation naming what is removed), and per-profile list account
  connections.

### Avatars

A fixed set of original avatar illustrations, bundled in both the Android app and the web
frontend and addressed by a stable key (`avatar` on the profile). No artwork from existing
manga, anime or streaming services. Colours and sizes come from the token files
(`frontend/tailwind.config.ts`, `Tokens.kt`).

## Testing

- Backend: for each per-person table, a test with two profiles proving that a read under one
  never returns the other's rows and a write under one never touches the other's. The anti-goals
  each get a test: the daughter's reader progress queues a write with her tokens only and marks
  nothing in Komga; the parent's list-only series is absent from her library, updates and
  notifications.
- Migration: an upgrade from a populated `0032` database leaves every existing row attached to
  the managing profile, and the existing suite passes unchanged without the header.
- Android: shared tests for the picker's one-profile skip, header injection, and outbox entries
  sent under their recorded profile after a switch.

## Left to the builder

- The number and look of the avatars, and how the art is produced, within "original".
- Endpoint shapes for profile management beyond those named above.
- How the web Profiles section lays out the per-profile connect buttons.
- The order the work lands in, as long as migration `0033` is a single migration.
