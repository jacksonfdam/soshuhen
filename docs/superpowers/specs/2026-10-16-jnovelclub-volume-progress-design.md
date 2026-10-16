# Volume progress to the reading lists

Date: 2026-10-16
Status: approved design, awaiting implementation plan
Branch: `feat/jnovelclub-volume-progress`, based on `feat/jnovelclub-volumes` (PR #255), which
stacks on #254 and #251.

## Goal

When a volume is read in Komga, the user's reading lists record it. "Read" means either the
volume book was finished, or every part of an owned volume was finished. Each list's volumes-read
count moves forward to that volume, and its chapters-read count moves forward to the volume's
last part. Only forward, never past the list's own totals.

This is piece 3 of 3:
- **Piece 1, parts:** PR #254.
- **Piece 2, owned volumes:** PR #255.

## Decisions taken with the user

| Question | Decision |
|---|---|
| What counts as reading a volume | Finishing its volume book in Komga, **or** finishing every part of a volume the user owns (part ranges known from the `volume` table). Parts of volumes the user does not own do not move volume progress. |
| What a finished volume writes | Volumes read = the volume number; chapters read = the volume's last part number (decided in piece 1). |
| Which lists | The same entries chapter progress already reaches: every writable entry, MangaBaka included. Nothing is written back to J-Novel Club. |
| Ceiling | Volumes read is capped at the list's own volume total when the provider gives one. The chapter cap from piece 1 still applies to chapters. |
| Approach | **Extend the existing progress write** (approach A): one request per entry carrying both fields; new `list_entry` columns for the guard and the cap. |

## Provider contracts

Checked 2026-10-16 against each provider's own documentation or schema. No authenticated calls were made.

| Provider | Read | Write | Same request as chapters? | Source |
|---|---|---|---|---|
| MyAnimeList v2 | `list_status.num_volumes_read` (integer, "0 or the number of read volumes"); media `num_volumes` (integer, "If unknown, it is 0") | form field `num_volumes_read` (integer) on `/manga/{id}/my_list_status` | yes: the endpoint "updates only values specified by the parameter" | myanimelist.net/apiconfig/references/api/v2 (embedded OpenAPI) |
| AniList | `MediaList.progressVolumes: Int`; `Media.volumes: Int` | `SaveMediaListEntry(progressVolumes: Int)`, "Min: 0" | yes: independent optional arguments | live introspection of graphql.anilist.co |
| MangaBaka | `progress_volume` in `GET /v1/my/library` | `progress_volume: number \| null`, 0–10000, on the library upsert next to `progress_chapter` | yes: the batch "patches (only the provided fields)" | mangabaka.org/api.json |

**Not documented anywhere:** what each provider does with a volume count above the series'
total. MyAnimeList's reference also disagrees with itself on PATCH versus PUT; the repo's existing
PATCH works for chapters and is kept.

**Today:**
- MyAnimeList and AniList already fetch the volume fields, and MangaBaka returns them, but every parser drops them. Volume data survives only in `list_entry.raw`.
- Every `push_progress` sends chapters only.

## 1. Data model and the provider contract

### Migration `0024_list_entry_volumes`

On `list_entry`:
- `user_progress_volume integer null`: volumes read, as the list records it.
- `total_volumes integer null`: the list's volume count. MyAnimeList's `0` ("unknown") is stored as null.

No backfill: the next list sync fills both. Null means unknown: the forward-only guard reads it as
0, and the cap reads it as "no cap".

### `ListEntryDTO`

It gains `progress_volume: int = 0` and `total_volumes: int | None = None`, filled by each parser:

| Provider | `progress_volume` | `total_volumes` |
|---|---|---|
| MyAnimeList | `list_status.num_volumes_read` | `node.num_volumes`; 0 becomes None |
| AniList | `progressVolumes` | `media.volumes`; both are already in `LIST_QUERY` |
| MangaBaka | `progress_volume` | None (its library schema has no volume total) |

`list_sync.upsert_entry` writes `user_progress_volume` and `total_volumes` like the chapter
columns. `upsert_entry_status` (the Discovery path) leaves them alone, the same as it leaves chapter
progress alone.

### `push_progress(access_token, media_id, chapter, volume: int | None = None)`

It stays one request. `volume=None` sends exactly today's request, so every existing caller, including
`progress_write` (the +1 button and the reader), is unchanged.

| Provider | With a volume |
|---|---|
| MyAnimeList | `num_volumes_read` in the same PATCH form |
| AniList | a mutation variant carrying `$progressVolumes: Int`, used only when a volume is given. The argument is never sent null, because `SaveMediaListEntry` writes what it is handed and a null would clear the user's count. |
| MangaBaka | `progress_volume` in the same upsert body |
| `local` | stores it in `user_progress_volume`; there is no remote list |

The base class's abstract signature changes to match.

## 2. Working out volumes read (`progress_push`)

`progress_push` already lists the series' Komga books and maps chapter book ids to chapter numbers.
It gains:

- `volume_books(session, series_id) -> dict[str, VolumeRow]`: Komga book id to a volume row, for rows with a `komga_book_id`. A `VolumeRow` carries `number`, `first_part` and `last_part`.
- A pure function, `furthest_volume(books, volume_books, volumes, chapter_books) -> tuple[int | None, Decimal | None]`, returning the furthest volume read and its last part:
  1. **Finished books:** the highest volume number whose Komga book is completed.
  2. **Finished parts:** the highest owned volume with a known range (`first_part`, `last_part`) whose every chapter row numbered in that range has a Komga book, and whose every such book is completed. A part never downloaded keeps the volume unfinished.
  3. The furthest volume is the higher of the two. Its last part is the `last_part` of the volume chosen, or None when unknown.
  4. Volume numbers are stored as `numeric`, but every provider takes a whole count, so the furthest volume is sent as `int(number)`. A half volume (2.5) counts as the whole volume below it (2).
- `read_chapter` becomes the higher of the furthest finished chapter (today's `highest_completed`) and that last part.

Per list entry, inside the existing loop:

| Field | Rule |
|---|---|
| chapter | `pushable_chapter(read_chapter, kind, total_chapters)`, piece 1's rule and cap, unchanged |
| volume | `pushable_volume(read_volume, total_volumes)`: capped at the total when known, then kept only if it beats `user_progress_volume` (null counts as 0) |

- If either moves forward, there is one `push_progress` call.
- When only the volume moves, no chapter is sent at all: the stored chapter is only as fresh as the last sync, and resending it could pull back a list read further elsewhere. `push_progress` takes `chapter=None` for this.
- A synced list whose `user_progress_volume` is still null (no sync since migration 0024) gets no volume: null there means unknown, not zero.
- When neither moves, nothing is sent.
- After a successful call, both columns are updated, and the log line names both: "mal: progress set to chapter 216, volume 16".
- A comic series has no volume rows, so `read_volume` is None and every call is exactly today's.
- The reading-frequency events (`progress_events`) stay chapter-only.

## 3. The other direction, screens and failures

### Komga catches up with the lists

`komga_scan.mark_read_up_to_lists` marks chapter books read up to the lists' furthest chapter. It
also marks volume books read when their `volume.number` is at or below the highest
`user_progress_volume` across the series' entries. Only books not yet completed are marked, so it
only ever moves forward.

### API and screen

- `GET /api/series/{id}` entries gain `user_progress_volume`.
- The `SyncTargets` panel on the series page shows "Ch. 216 · Vol. 16" when the entry has a volume count, and just the chapter otherwise.
- Nothing new is editable: volume progress moves only from reading in Komga.

### Failures

- **A provider rejects the volume.** If a `push_progress` carrying a volume fails with HTTP 400 or 422, it is retried once without the volume. The log says "`<provider>` refused volume N, sent chapter only", and only `user_progress_chapter` is updated. Chapter progress never stalls on a volume problem the cap did not prevent. For AniList, a GraphQL error response counts as the refusal, mapped the way the provider already surfaces errors.
- **Expired tokens and missing entries** behave as chapter pushes do today.
- **No finished volume:** no volume is sent.

### Not in scope

- Volume writes from the +1 button or the image reader.
- A backfill: the next `progress_push` after a scan computes volumes from Komga's read state.
- Volume reading in the reading-frequency chart.
- Writing anything to J-Novel Club.

## 4. Testing

**Pure:**

| Subject | Cases |
|---|---|
| Parsers, against the existing fixtures (extended with volume fields where they lack them) | MyAnimeList `num_volumes_read` and `num_volumes`, with 0 → None; AniList `progressVolumes` and `volumes`; MangaBaka `progress_volume` |
| `push_progress` bodies, via `httpx.MockTransport` | without a volume, the exact current request (pinned); with a volume, MyAnimeList's form has `num_volumes_read`, AniList's variables have `progressVolumes` (and no `progressVolumes` key when absent), MangaBaka's body has `progress_volume` |
| `furthest_volume` | finished volume book; fully finished part range; one part unread; one part never downloaded; no range known; no volumes (comic) |
| `pushable_volume` | capped; uncapped when the total is None; None when not forward |

**Against Postgres:**

| Subject | Cases |
|---|---|
| Migration 0024 | both nullable columns |
| `list_sync` | stores `user_progress_volume` and `total_volumes`; `upsert_entry_status` does not touch them |
| `progress_push`, with fake providers recording calls | a finished volume book sends chapter = last part and volume = number, once per entry; a list already at or past the volume gets no volume; a volume-only move sends the current chapter; a 400 on a volume write is retried without the volume, logged, and only the chapter column updated; a comic series makes the same calls as today |
| `komga_scan` | volume books up to the lists' volume count are marked read; others untouched |
| API | `user_progress_volume` in series detail entries |

**Frontend:** `npm run build`, and every new class grepped in `frontend/dist/`.

**Live** (with the user's go-ahead):
- Run a list sync and check that `total_volumes` and `user_progress_volume` are filled for the light-novel entries. This is a read only.
- A real volume push needs an owned volume finished in Komga. It stays unverified until the account owns one.
