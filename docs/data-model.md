# Data model

Source of truth: `backend/app/models.py` and `backend/alembic/versions/`. Twelve tables. The
enumerations live in `backend/app/enums.py` and are stored as strings, not as Postgres enum types,
so adding a member needs no migration.

## The central idea

**A list entry is not a series.** `list_entry` is one row per provider — the same manga on
MyAnimeList and on AniList is two rows. `series` is the canonical work those rows point at.

That separation is what makes one mapping, one folder and one download serve however many lists a
title appears on. Almost every subtlety in `list_sync` exists to decide, correctly, which `series` a
`list_entry` belongs to.

## Reading and downloading

### `series`
The canonical work.

`id`, `canonical_title`, `slug` (unique; the folder name), `komga_series_id`, `needs_review`,
`auto_download`, `review_ignored_at`, `meta` (jsonb), `created_at`

- **`slug` is the folder name** and is reserved uniquely at creation — colliding titles get a numeric
  suffix.
- **`auto_download` is opt-in and defaults false.** Only a followed series has its missing chapters
  queued by discovery. Confirming a mapping does not imply fetching a backlog; before this existed,
  forty-five confirmations queued tens of thousands of chapters.
- **The state a screen shows is derived, not stored.** No active mapping reads `needs_review`, unless
  a chapter or volume of the series is already `downloaded`: then it is `local`, and nothing asks it
  for a mapping (`app/api/library_content.py`). Ongoing downloads and failures win over both.
- **`meta.aliases`** holds normalised titles, widened as each provider contributes spellings.
- **`meta.cross_refs`** holds identifiers with their provenance. See
  [`providers.md`](providers.md#identity-and-hearsay).
- **`kind`** is `comic`, `prose` or null, with a check constraint. Null means unknown and behaves as
  `comic`, which is what every series did before the column existed. Migration `0019` backfilled it
  from the entries' `raw`.
- **How it is set.** `list_sync` recomputes it from all of the
  series' entries after each entry is upserted, unless it is locked; a series with both comic and prose entries resolves to
  `comic`. The user sets it with `POST /api/series/{id}/kind`, which is how a `local` series or a
  provider that states nothing gets one.
- **`meta.kind_locked`** is set by that route and marks a kind chosen by hand. Sync never overwrites a
  locked kind.

### `list_entry`
One row per provider per work. Unique on `(provider, provider_media_id)`.

`id`, `provider`, `provider_media_id`, `series_id`, `title_romaji`, `title_english`, `synonyms`,
`status`, `user_progress_chapter`, `total_chapters`, `user_progress_volume`, `total_volumes`,
`cover_url`, `raw` (jsonb), `updated_at`

`user_progress_volume` and `total_volumes` are the list's own volume counts, filled by list sync.
Both are nullable: null means the list never said. MyAnimeList reports an unknown total as `0`, which
is stored as null so it can never cap volume progress at zero.

`raw` keeps the provider's own payload. Metadata for `ComicInfo.xml` is read out of it at use time
rather than denormalised into columns — a column is another thing to keep in sync, and these are
display-only.

### `source_mapping`
The confirmed link from a series to a source URL. `active` is false for superseded mappings rather
than deleting history. `discovered_at` is set by the first `chapter_discover` run against the
mapping. Until it is set, nothing the mapping lists is announced as new.

### `site_catalogue`
Every source site the pipeline knows how to reach, and how to reach it.

`key` (primary key), `name`, `template`, `base_url`, `lang`, `nsfw`, `overrides` (jsonb),
`rate_limit` (jsonb), `version`, `hand_ported`

Generated output. `app/catalogue/repo.py::replace_catalogue` is the only thing that writes it: it
upserts every row a regeneration produced and deletes the keys that run left out. Two exceptions are
deliberate. Rows with `template = 'native'` are never deleted — MangaDex and comick are hand-written
Python classes, and the generator parses an extension repository that mentions neither. And an empty
regeneration is refused rather than applied, because the source registry is built from this table
and an accepted empty run would disable searching and downloading for the whole library at once.

`hand_ported` is false for a site whose extension carries behaviour the generator cannot derive. It
ships in the catalogue but disabled, with the reason on its settings row.

### `source_pref`
The user's own decision about a site, kept in a separate table on purpose.

`key` (primary key), `enabled`, `priority`, `rate_limit_override` (jsonb), `disabled_reason`

A regenerated catalogue must never silently re-enable a site someone turned off, or forget one they
turned on, so nothing that writes the catalogue touches this table. A preference whose site vanished
upstream is kept and shown as orphaned rather than deleted. There is no foreign key between the two
tables for the same reason: one would cascade the catalogue's delete straight onto the preference.

`source_mapping.source_site` likewise stays a plain string against the catalogue key, with no
foreign key. A confirmed mapping outlives a regeneration, and if its site is gone the download fails
naming the site — more use than the mapping quietly disappearing.

The registry every source lookup goes through is these two tables joined: loaded once at boot in
both the API and the worker, so enabling a site in settings is the same act as registering it.

### `series_candidate`
Search results awaiting confirmation. Replaced wholesale on each `match_search`.

### `volume`
A volume the user owns: one owned or pre-ordered on J-Novel Club, or one imported from the user's
own PDFs. Unique on `(series_id, number, edition)` and on `(series_id, source_volume_id)`.

`id`, `series_id`, `number`, `edition` (`web`, `light`), `source_volume_id`, `title`, `status` (`owned`, `preorder`),
`last_updated`, `downloaded_updated`, `first_part`, `last_part`, `state`, `file_path`,
`komga_book_id`, `discovered_at`

**One number, two editions.** A light novel rewrites and merges the web novel's chapters, so the
same volume number can be two different books. `number` is always the light novel's volume number.
A `light` row owns a `Vol.` file; a `web` row owns no file and is only the range `first_part` to
`last_part` of imported chapters. J-Novel Club rows are `light`. Imported rows have
`source_volume_id = 'import:<sha256 of the PDF>'`.

**Kept apart from `chapter` on purpose.** Everything that counts chapters or turns a Komga book into
a chapter number would otherwise need a filter, and a forgotten one would count volume 16 as
chapter 16.

`last_updated` is J-Novel Club's own revision date; `downloaded_updated` is the revision of the file
on disk. When the first is newer, the volume downloads again and replaces the file. `last_part` sets
where Komga sorts the volume: just after the last part it collects. Download links are never stored
- they carry their own authorisation and are read fresh from the library each time.

### `chapter`
What exists and what is held locally. Unique on `(series_id, number)`.

A chapter imported from a PDF has no `source_url` and is born `downloaded` with its `file_path`, so
nothing ever queues it for download.

`id`, `series_id`, `number` (`Numeric`), `title`, `source_url`, `state`, `file_path`,
`komga_book_id`, `discovered_at`, `available_until`, `bookmarked`

`bookmarked` is the one mark a chapter keeps that no list knows: read is derived from list progress
and never stored here.

`discovered_at` is also what "new" means. `chapter_discover` stamps the chapters a mapping's first
run inserts and that mapping's `discovered_at` in one transaction, so the two are equal for exactly
the back catalogue. The new chapters screen and the release rhythm (`app/rhythm.py`) both count
only chapters whose `discovered_at` matches no mapping of their series.

`available_until` is when the source stops serving the chapter to the signed-in account; null, which
is every chapter of every source but J-Novel Club's pre-publication parts, means never. Discovery
writes it on every run, so a date the source moves is followed.

**`state` is the record of what is missing**, reconciled against Komga rather than the filesystem, so
moving files by hand does not cause a redownload.

`known` → `queued` → `downloading` → `downloaded`, with `failed` and `skipped` as ends. `skipped`
means the source will not serve it in the requested language; it does not return to retry.

`streaming` sits beside `known`: someone is reading the chapter before it was downloaded, and its
pages are arriving in the reader cache. `download_batch` leaves it alone, because the cache becomes
its archive. A chapter left half read for a week returns to `known`.

`number` is `Numeric`, not an integer — half chapters are real and `12.5` must survive.

## Reading

### `reading_position`
`series_id` (key), `chapter_id`, `page`, `updated_at`. One row per series.

Where reading stands inside a chapter, kept by this installation only. Apart from
`list_entry.user_progress_chapter` on purpose: that is a list's view of progress, every sync
overwrites it, and no list holds a page number. Pages are zero-based.

### `series_reader_pref`
`series_id` (key), `mode`, `scale`, `background`.

Only for a series that differs from the default. With no row, the `reader_default_*` keys in
`setting` apply.

### `chapter_page_list`
`chapter_id` (key), `pages` (JSONB of `{url, headers}`), `fetched_at`.

A streamed chapter's page list, stored so a restart of `api` does not ask the source again. It can
go stale — a CDN stops serving the addresses it named — and a page that 404s asks for the list once
more.

## The queue

### `job`
`id`, `type`, `payload` (jsonb), `state`, `priority`, `attempts`, `max_attempts`, `lease_until`,
`run_after`, `last_error`, `dedupe_key`, `series_id`, `created_at`, `started_at`, `finished_at`

Indexes that matter: `(state, priority, created_at)` for the lease, `(state, lease_until)` for
reclaiming, and a **partial unique index on `(type, dedupe_key)` restricted to `pending` and
`leased`** — which is what lets a finished job not block an identical later one.

`priority` ascends: 0 before 100. See [`jobs.md`](jobs.md).

### `job_event`
Append-only progress. `job_id`, `ts`, `level`, `message`, `pct`. This is the operational log the
interface shows; container stdout is for when a container will not start.

### `notification`
What one discovery run found new for one series. A run that found three chapters writes one row,
not three. The columns:

- `kind`: `chapters`, `volumes` or `parts`. A `parts` row is a J-Novel Club volume that was
  already known and has grown.
- `count`, `first_number` and `last_number`: how many items, and their range.
- `volume_number`: for `parts` only, the volume the parts belong to.
- `created_at`, and `read_at`, which is null until the user reads it.

The series' title and cover are read through `series_id` rather than copied in, so a renamed
series reads correctly in old notifications. The rows go with their series through the cascade.

Rows are written only by `chapter_discover` and `jnc_library_sync`, through
`app/notifications.py`. Neither writes one on the first discovery of a mapping or the first sync
of a series, which would announce a whole backlog as new. Read rows older than 30 days are deleted whenever a new row is written.
Unread rows stay until they are read.

## Accounts and configuration

### `provider_token`
One row per provider, keyed by `provider`. `access_token`, `refresh_token`, `expires_at`,
`account_name`.

Only OAuth providers appear here. A provider authenticating with a configured key has nothing stored
— `static_credential()` answers before this table is consulted.

### `setting`
Key/value strings for what the interface may change: concurrency, batch size, cron expressions.

One credential lives here: `jnc_token` and `jnc_token_expires_at`, the J-Novel Club token saved by the
Settings sign-in. They are never part of `GET /api/settings`, which sends what it lists to the
browser, and no password is ever stored; every other credential stays in the environment.

## Discovery

### `anime_entry`
The anime mirror. Unique on `(provider, provider_media_id)`.

`related_manga` holds the relation edges naming which manga an anime adapts. `manga_dismissed_at`
makes a dismissal stick so the same title never returns as a suggestion.

### `suggestion`
A manga proposed from an anime. `alt_ids`, `rank_score`, `state`, `series_id` once approved, and
`meta` carrying the reason it exists — which anime, how far the adaptation got, how much manga
remains.

The reason is the point. A suggestion without it is a title the user has to go and research, which
is the work the feature exists to remove.

## History

### `progress_event`
`series_id`, `chapter`, `delta`, `source`, `created_at`.

Written by `progress_push`, by the manual increment path and by the reader finishing a chapter;
`source` says which (`komga`, `manual`, `reader`). It exists because
`user_progress_chapter` is a current value with no history, so chapters-per-day cannot be computed
from it.

**It fills forward only.** The velocity chart is empty the day it ships and becomes useful over the
following weeks, and the screen must say so rather than draw a flat line that reads as a month of
reading nothing.

## Migrations

Alembic, in `backend/alembic/versions/`, chained linearly. The `api` container runs
`alembic upgrade head` on start; the test suite migrates from a session fixture in
`tests/conftest.py`.

**Two branches must not both add a migration from the same parent.** That produces two heads and an
upgrade that refuses to run.

**A worktree needs its own database.** Two branches sharing one means whichever migrated last decides
the schema, and a schema ahead of the branch under test makes the suite lie about that branch. Start
a second container on another port and pass `POSTGRES_PORT`.

A shared development database stamped by a branch migration produces
`Can't locate revision identified by ...` on a branch that does not contain it. The database is
wrong, not the branch.
