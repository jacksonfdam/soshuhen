# Offloading chapters to the phone, and a storage indicator

Date: 2026-11-16. Extends `2026-10-20-android-client-design.md`.

## Intent

The server's disk fills up with archives the user already holds on the phone. The user wants the
Android app to confirm that everything the server downloaded for the marked series is on the
device, and then to ask whether to **delete the server's copies** or **keep them**. Deleting is
done to free server disk space. A chapter removed this way is never downloaded again on its own;
it can be downloaded again from the source when the user asks, which the user considers cheap.

The app also shows how much space its folder takes on the device.

## Goals

- A **Sync** action in the app that, for every marked series, checks each chapter and volume the
  server holds against the device, copies whatever is missing (the existing import), and reports the
  result.
- When everything checked is on the device and verified, one question: **delete from the server** or
  **keep a copy on the server**. Keep is the default.
- A chapter deleted from the server becomes `offloaded`: the server never queues it by itself, the
  interfaces say where it lives, and "Download range" can bring it back.
- A storage indicator in Settings: the size of `<picked folder>/Soshuhen/`, per series, and the free
  space on the volume that holds it.

## Non-goals

- Automatic deletion on either side. The server deletes only when the user answers the question; the
  app deletes nothing as part of this.
- Offloading series that are not marked, or chapters the device has not verified.
- Moving files back from the phone to the server. Getting a chapter back means downloading it again
  from the source.
- A server-side retention policy.

## Anti-goals

- **Deleting a server file the phone does not actually hold.** Every deletion is checked against the
  ETag the phone recorded when it copied the file; a mismatch keeps the file.
- An offloaded chapter downloading again by itself (cron, `auto_download`, discovery re-finding a
  file). That would make the space saving silently undo itself.
- An offloaded chapter shown as broken or missing in the web interface.

## Approaches

| | Approach | Trade-off |
|---|---|---|
| **A (picked)** | New chapter/volume state `offloaded`. The phone posts the ids and ETags it verified; a job on the download lane deletes matching files, sets `offloaded`, clears `file_path`, and queues a Komga scan. | A migration-free state value, a job, an endpoint and UI labels on both clients. Honest everywhere. |
| B | Delete the file and leave the row `downloaded`. | Less server code, but the archive endpoint 404s, the web reader breaks, stats count space no longer used, and "Download range" cannot fetch it again. |
| C | The server deletes by itself once a device reports holding a chapter. | Drops the question the user asked for. Rejected. |

The user picked A.

Accepted consequence: an offloaded chapter is no longer in Komga or readable in the web reader. Only
the phone can read it until it is downloaded again.

## Constraints found in the codebase

- `chapter.state` is plain text with no check constraint. `volume.state` is guarded by
  `volume_state_check` (`alembic/versions/0023_volume.py`), so volumes need a migration that widens it.
- `api` mounts `/manga` read-only (`docker-compose.yml`). Only `worker-download` writes the library,
  so deletion must run as a job in that lane.
- Today nothing turns a `downloaded` chapter back into `known` when its file disappears. The guards
  that queue chapters for download (`chapter_discover.py`, `download_batch.py`, `reader_cache.py`) filter
  on explicit states, so `offloaded` is excluded from automatic chapter downloads.
- **But two reconcile paths would undo an offload** and must gain a `state <> 'offloaded'` guard:
  `chapter_discover.reconcile_with_komga` matches `file_path is null and number = :number` with no
  state filter, and `komga_scan.py` (~line 433) marks volumes `downloaded` by number. Komga keeps deleted
  books in its trash (`komga/client.py`: `emptyTrashAfterScan: False`), so it keeps reporting them.
- The download lane already runs `download_batch`, `download_chapter`, `volume_download` and
  `import_files` (`enums.py`); `offload` is a fifth job type there.
- `POST /api/series/{id}/download` selects `state in ('known', 'failed', 'skipped', 'streaming')`.
- The archive endpoint (`routes_chapters.py`, `routes_volumes.py`) serves through Starlette's
  `FileResponse`, whose ETag is derived from mtime and size. The phone stores that ETag per file in
  `device_chapter.etag` / `device_volume.etag`, with `size`.
- The phone decides availability device-first (`core/ChapterRows.kt`), so an offloaded chapter it holds
  already shows as on device. The importer copies only `state == "downloaded" && filePath != null`, so it
  ignores offloaded rows.

## Design

### Server

**State.** `offloaded` joins `downloaded`, `known`, ... for chapters and volumes. Meaning: the archive
existed, a device confirmed holding it, and the server file was deleted on the user's request.
`file_path` is set to null; `komga_book_id` is cleared after the scan.

**Endpoint.** `POST /api/offload` with

```json
{ "chapters": [{ "id": 123, "etag": "\"abc\"", "size": 48213 }],
  "volumes":  [{ "id": 9,   "etag": "\"def\"", "size": 913044 }] }
```

It validates the ids exist and are `downloaded` with a `file_path`, enqueues one `offload` job carrying
the list, and returns `{ "queued": n, "skipped": [{id, reason}] }`. Nothing is deleted in the request.

**Job `offload`** — registered on the download lane only (`worker-download`), alongside
`download_batch` and `download_chapter`, so it is the only writer and cannot race a download of the same
series in the other worker. For each item, in one transaction per item:

1. Re-read the row; skip unless still `downloaded` with the same `file_path`.
2. Resolve the path and check it sits inside `library_path` (as `library_file` does).
3. Recompute the ETag the archive endpoint would serve and compare with the phone's, plus size. Skip on
   mismatch: the file was rebuilt after the phone copied it.
4. Delete the file, set `state = 'offloaded'`, `file_path = null`. A missing file still becomes
   `offloaded` (the phone has it, which is all the state promises).
5. Remove the series folder if it is now empty.

Then queue one `komga_scan` for the affected series, and remove the deleted books from Komga so it
shows no ghost entries: through a series-scoped Komga call if its OpenAPI document offers one,
otherwise by deleting each book by `komga_book_id` (**builder's call, verified from Komga's own API
document, never from memory**). Clear `komga_book_id` once Komga no longer lists the book. Results (deleted, skipped and why, bytes freed)
are logged and announced over `pg_notify` like other jobs. Failure of one item does not fail the rest.

**Getting it back.** `POST /api/series/{id}/download` includes `offloaded` in its state list, so the
existing "Download range" on the web brings chapters back. The download handlers set `downloaded` on
completion as they do now.

**Volumes (light novels).** The user chose to include them. Three things differ from chapters:

- *Migration.* Widen `volume_state_check` to allow `offloaded`, with a downgrade that refuses while any
  volume is `offloaded` rather than silently rewriting it.
- *Revisions.* `jnc_library_sync.needs_download` ignores `state`, so a J-Novel Club revision would
  queue an offloaded volume by itself. It returns false for `offloaded`. Whether a newer revision exists
  stays derived, as it is today (`downloaded_updated < last_updated`): no new column. The web shows such
  a volume as "On device · newer revision on J-Novel Club", and the phone's Sync report lists it, so
  the user decides when to download it again. This follows the rule the user gave: an offloaded item
  keeps its status, or waits to be downloaded again when the user asks. **(My call.)**
- *Way back.* "Download range" handles chapters only. A new `POST /api/volumes/{id}/download` enqueues
  `volume_download` at priority 0 (deduped on `volume_download:{id}` as the sync does) and sets
  `queued`; the web volume row gains a "Download again" button for `offloaded` volumes.

**Counts.** Series detail and dashboard queries gain an `offloaded` count next to `downloaded`;
`library_content.py`'s "has content" check counts `offloaded` too, so a fully offloaded series stays in
the library.

**Web interface.** The chapter table shows `offloaded` as "On device" (a distinct badge, not an error),
and a series header shows "N on device only" when there are any. No new screen.

### App

**Scope.** Marked series of both kinds, comics and prose: every server item that is a file on the
server. **(My call.)**

**Sync** lives in Settings under "On this device" as a button, and as an action on a marked series'
detail screen (scoped to that series). It runs at home only.

1. Run the existing import for the scope (same `ImportRunner`, foreground, with progress), which copies
   anything missing and re-copies files whose ETag changed.
2. Build the report: for each chapter/volume the server lists as `downloaded`, is it indexed on the
   device, does the file still exist (`folder.exists(uri)`), does its size match the index, and does the
   index hold an ETag. An item indexed without an ETag (older imports) gets one from the importer's
   existing last-byte probe during step 1; if it still has none it counts as unverified. **(My call.)**
3. If anything is still missing or failed, show the report ("142 of 150 on device · 8 could not be
   copied") with the reasons, and **do not** offer deletion.
4. If everything is verified, show the question with the numbers:
   "All 150 chapters of 3 series are on this device. Free 2.1 GB on the server?"
   Buttons: **Keep on server** (default) / **Delete from server**. The size shown is the sum of the
   device index sizes for the server-held items.
5. On delete, `POST /api/offload` with the verified ids, ETags and sizes; show "Removing from server…"
   and refresh the series afterwards.

**Labels.** A chapter row whose server state is `offloaded` and that is on the device reads
"On device only". One not on the device (deleted from the phone later) reads "Removed from server —
download again from the web". `DetailRules.next` treats it as unavailable then.

**Deleting on the phone.** Deleting a chapter (single or "delete read chapters") that is `offloaded`
warns that it is the only copy: "This is the only copy. It will have to be downloaded again from the
source." Unmarking a series with offloaded chapters says the same in its existing prompt.

### Storage indicator

In Settings, "On this device" section, under the folder:

```
Chapters folder   /storage/…/Soshuhen
Used by Soshuhen  4.8 GB  ·  Free on this card 21.3 GB
[ bar: used by Soshuhen | other | free ]
Per series  ›   (list sorted by size: title, chapters, size)
```

- **Used** is the sum of `size` in `device_chapter` and `device_volume`, overall and grouped by series.
  It comes from the index, not from walking the folder, so it is instant. (Builder's call: a walk over
  SAF is slow; the index is what the app trusts elsewhere.)
- **Free** and the volume total come from the platform: an `expect` in `commonMain` with the Android
  side using `StorageManager`/`StatFs` on the volume behind the tree URI. If the volume cannot be
  resolved, show only "Used".
- Updates live as imports land (the DAOs already return `Flow`).

## Testing

- Backend, against the real test Postgres: the volume migration upgrades and downgrades;
  `needs_download` is false for an offloaded volume even after a revision; `POST /api/volumes/{id}/download`
  queues one job and dedupes a second call; the job deletes a file whose ETag matches and sets
  `offloaded`; `reconcile_with_komga` and `komga_scan` leave an `offloaded` row alone while Komga still
  lists its book; skips a rebuilt file (ETag mismatch); skips a row no longer `downloaded`; refuses a path
  outside `library_path`; `download_range` picks `offloaded`; `chapter_discover`, cron and
  `auto_download` never queue `offloaded`; the job is not registered on the general lane.
- App, `commonTest`: sync report states (all verified, some missing, file deleted by hand, size
  mismatch); deletion is only offered when all verified; labels for offloaded on/off device; storage
  sums per series.

## Left to the builder

- Exact names: `offload` job type, `POST /api/offload` path, UI strings beyond those above.
- Whether the web badge reuses an existing primitive.
- Batch size of a single `offload` job if a large list should be split (the `setting` batch size is a
  reasonable reuse).
- Updating `docs/data-model.md`, `docs/architecture.md` (the new state, the fifth download-lane job)
  and `docs/features.md`.
