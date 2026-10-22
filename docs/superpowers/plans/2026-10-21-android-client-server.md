# Android Client, Part 1: Server Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the server the four things the Android client needs: an identity answer for the LAN
scan, a whole-archive download, covers served from the LAN, and position and completion writes that
carry when the reading happened.

**Architecture:** Three new read-only routes and two widened write routes in the existing FastAPI
app. Covers are cached by `api` under `reader-cache/covers/`. The `read_at` time travels from the
route through the `progress_write` job payload into `progress_event.created_at`. Every change keeps
the web interface's current requests working unchanged.

**Tech Stack:** Python 3.12, FastAPI 0.141 on Starlette 1.6 (`FileResponse` handles `Range` and
`ETag`), SQLAlchemy async with raw `text()` SQL, asyncpg, httpx, pytest-asyncio against a real
Postgres.

**Spec:** `docs/superpowers/specs/2026-10-20-android-client-design.md`, section "Server changes".

This is the first of three plans. Part 2 is the app foundation (project, theme, icon and splash,
server discovery, online library and detail). Part 3 is offline: import, reader, progress queue,
notifications. Each depends on the one before.

## Global Constraints

- Commands run from `backend/`: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q` and `.venv/bin/python -m ruff check app/ tests/`. Both must pass before every commit.
- No migration. Every change fits the existing schema (`setting`, `reading_position.updated_at`, `progress_event.created_at`, `job.payload`).
- `/manga` is never written by `api`. Covers go under `get_settings().reader_cache_path / "covers"`.
- Prose (`series.kind == "prose"`) chapters get 409 from the archive route, the same as the reader.
- asyncpg cannot infer a null parameter's type: a nullable timestamp parameter is written `cast(:at as timestamptz)`.
- A `read_at` later than the database's `now()` is clamped to `now()`, in SQL.
- Requests without `read_at` behave exactly as they do today. The web client sends none.
- Comments explain why a line exists, never what it does (repository `CLAUDE.md`).
- Commits: English, one focused change each, no assistant attribution of any kind.

## Review Focus

1. **A chapter whose `file_path` points outside `library_path`, or at a deleted file**: the archive route answers 404, never streams it. Test in Task 2.
2. **An interrupted copy resumed with `Range: bytes=N-`**: 206 with exactly the remaining bytes. Test in Task 2.
3. **A cover CDN that times out or answers 404**: the route answers 404, nothing is cached, and the next request tries again. Test in Task 3.
4. **Two completions for one series queued offline, replayed out of order** (later `read_at` first): the job ends with the higher chapter and the `read_at` that came with it, never an older time on a newer chapter. Test in Task 5.
5. **A phone whose clock runs a day fast**: its position must not beat a later web position forever. Clamped to `now()`, so a later web write still wins. Test in Task 4.

---

### Task 1: Identity endpoint

**Files:**
- Create: `backend/app/api/routes_identity.py`
- Modify: `backend/app/settings_store.py` (add the key constant), `backend/app/api/main.py` (include the router)
- Test: `backend/tests/test_identity_api.py`

**Interfaces:**
- Produces: `GET /api/identity` → `{"app": "soshuhen", "name": "Soshuhen", "version": str, "instance_id": str}`. `INSTANCE_ID = "instance_id"` in `settings_store`, deliberately absent from `all_settings()`'s key list (it is an identity, not a knob).

- [ ] **Step 1: Write the failing tests** in `tests/test_identity_api.py`, using the `client` fixture pattern from `tests/test_reader_api.py` and an autouse fixture that truncates `setting`:

```python
async def test_identity_names_the_app(client):
    body = (await client.get("/api/identity")).json()
    assert body["app"] == "soshuhen"
    assert body["name"] == "Soshuhen"
    assert body["version"]

async def test_instance_id_is_a_uuid_and_stable(client):
    first = (await client.get("/api/identity")).json()["instance_id"]
    second = (await client.get("/api/identity")).json()["instance_id"]
    assert uuid.UUID(first) and first == second

async def test_instance_id_survives_in_the_setting_table(client):
    first = (await client.get("/api/identity")).json()["instance_id"]
    async with get_sessionmaker()() as session:
        assert await settings_store.stored(session, settings_store.INSTANCE_ID) == first

async def test_instance_id_is_not_listed_with_the_settings(client):
    # all_settings() feeds GET /api/settings "values"; called directly because that
    # route also probes Comick over the network.
    await client.get("/api/identity")
    async with get_sessionmaker()() as session:
        assert "instance_id" not in await settings_store.all_settings(session)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_identity_api.py -q`
Expected: FAIL, 404 on `/api/identity`.

- [ ] **Step 3: Implement `identity(session) -> dict[str, str]` in `routes_identity.py`**

Router `APIRouter(prefix="/api/identity", tags=["identity"])`, route `GET ""`. Read `settings_store.stored(session, INSTANCE_ID)`; when `None`, generate `str(uuid.uuid4())`, store it with an `insert ... on conflict (key) do nothing`, commit, and re-read so two first requests racing agree on one id. `version` is `importlib.metadata.version("soshuhen")`, falling back to `"0.0.0"` on `PackageNotFoundError`. Include the router in `main.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Same command. Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_identity.py backend/app/settings_store.py backend/app/api/main.py backend/tests/test_identity_api.py
git commit -m "feat(backend): answer who this server is for a LAN scan"
```

### Task 2: Whole-archive endpoint

**Files:**
- Create: `backend/app/api/routes_chapters.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_chapter_archive_api.py`

**Interfaces:**
- Consumes: `reader_service.chapter(session, chapter_id) -> ChapterRow` (raises `ChapterMissing`, `ProseChapter`) and `reader_service.archive_of(row) -> Path | None` (`None` when no file or outside `library_path`).
- Produces: `GET /api/chapters/{chapter_id}/archive` → the CBZ bytes, `media_type="application/vnd.comicbook+zip"`, `Content-Disposition` with the file's own name, `ETag` and `Accept-Ranges: bytes` from `FileResponse`.

- [ ] **Step 1: Write the failing tests.** Reuse `_series`, `_chapter`, `_cbz` and the `clean` fixture shape from `tests/test_reader_api.py` (copy the helpers; test modules there do not import each other's private helpers except `test_download_chapter_handler`):

```python
async def test_serves_the_whole_archive(client, tmp_path):
    # chapter with file_path = _cbz(tmp_path/"manga"/"teto"/"c1.cbz", [JPEG])
    response = await client.get(f"/api/chapters/{chapter_id}/archive")
    assert response.status_code == 200
    assert response.content == path.read_bytes()
    assert response.headers["content-length"] == str(path.stat().st_size)
    assert response.headers["etag"]
    assert 'filename="c1.cbz"' in response.headers["content-disposition"]

async def test_a_range_request_resumes(client, tmp_path):
    response = await client.get(url, headers={"Range": "bytes=10-"})
    assert response.status_code == 206
    assert response.content == path.read_bytes()[10:]

async def test_a_chapter_without_a_file_is_404(client): ...        # file_path None -> 404
async def test_a_deleted_file_is_404(client, tmp_path): ...         # file_path set, file unlinked -> 404
async def test_a_file_outside_the_library_is_404(client, tmp_path): # _cbz(tmp_path/"elsewhere"/"x.cbz") -> 404
async def test_an_unknown_chapter_is_404(client): ...               # id 999999 -> 404
async def test_a_prose_chapter_is_409(client, tmp_path): ...        # update series set kind='prose' -> 409
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_chapter_archive_api.py -q`
Expected: FAIL, 404 for every case including the ones expecting 200 and 206.

- [ ] **Step 3: Implement `archive(chapter_id: int, session) -> FileResponse` in `routes_chapters.py`**

Router `APIRouter(prefix="/api/chapters", tags=["chapters"])`. Map `ChapterMissing` → 404 and `ProseChapter` → 409, the same as `routes_reader.service_errors` does (import and reuse that context manager rather than copying it). `archive_of(row) is None` → 404 `"chapter is not in the library"`. Return `FileResponse(path, media_type=..., filename=path.name)`. Include the router in `main.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Same command. Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_chapters.py backend/app/api/main.py backend/tests/test_chapter_archive_api.py
git commit -m "feat(backend): serve a chapter's whole archive for offline copies"
```

### Task 3: Cover endpoint

**Files:**
- Create: `backend/app/reader/covers.py` (pure: path in, bytes out; no database)
- Modify: `backend/app/api/routes_series.py` (the route)
- Test: `backend/tests/test_series_cover_api.py`

**Interfaces:**
- Consumes: `app.downloader.cbz.page_extension(data: bytes) -> str` for the stored file's extension, and `routes_reader.MEDIA_TYPES` for the response type.
- Produces:
  - `covers.cached(root: Path, url: str) -> Path | None`: the stored file for this URL, if any.
  - `async covers.fetch(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> bytes | None`: one GET, 15 s timeout, follows redirects; `None` on any HTTP error, timeout, non-2xx, or a body `page_extension` does not recognise as an image.
  - `covers.store(root: Path, url: str, data: bytes) -> Path`: writes `root/<sha256(url)>.<ext>` through a `.part` file and `rename`, so a reader never sees half a cover.
  - `GET /api/series/{series_id}/cover` → image bytes, `ETag` = the sha256 key, `Cache-Control: public, max-age=86400`, 304 on a matching `If-None-Match`. 404 when the series does not exist, has no `meta.cover_url`, or the fetch failed.
  - Module attribute `covers.TRANSPORT: httpx.AsyncBaseTransport | None = None`, read by the route, so tests swap in `httpx.MockTransport` with `monkeypatch`.

- [ ] **Step 1: Write the failing tests.** Autouse fixture sets `READER_CACHE_PATH` to `tmp_path/"cache"` and clears `get_settings` as `tests/test_reader_api.py` does. A series with `meta = {"cover_url": "https://cdn.test/c.jpg"}`. A `MockTransport` handler that counts calls:

```python
async def test_first_request_fetches_and_caches(client, tmp_path, monkeypatch):
    # handler returns 200 JPEG
    response = await client.get(f"/api/series/{sid}/cover")
    assert response.status_code == 200 and response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert len(list((tmp_path / "cache" / "covers").glob("*.jpg"))) == 1

async def test_second_request_does_not_refetch(client, monkeypatch):
    await client.get(url); await client.get(url)
    assert calls == 1

async def test_matching_etag_is_304(client, monkeypatch):
    etag = (await client.get(url)).headers["etag"]
    assert (await client.get(url, headers={"If-None-Match": etag})).status_code == 304

async def test_a_failed_fetch_is_404_and_retried_later(client, monkeypatch):
    # handler returns 404 the first time, 200 JPEG the second
    assert (await client.get(url)).status_code == 404
    assert (await client.get(url)).status_code == 200

async def test_a_timeout_is_404(client, monkeypatch): ...      # handler raises httpx.ReadTimeout
async def test_a_non_image_body_is_404(client, monkeypatch): ... # 200 with b"<html>"
async def test_no_cover_url_is_404(client): ...                 # meta '{}'; handler never called
async def test_a_changed_cover_url_fetches_the_new_one(client, monkeypatch): ...
    # update series meta to a second URL; calls == 2, two files in covers/
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_series_cover_api.py -q`
Expected: FAIL, 404 or 405 on the route.

- [ ] **Step 3: Implement `covers.py` and the route** with the signatures above. The route reads `meta->>'cover_url'` with one `select`, then `cached` → `fetch` → `store`. A failed fetch stores nothing, which is what lets the next request try again.

- [ ] **Step 4: Run the tests to verify they pass**

Same command. Expected: 8 passed. Then the whole suite, to confirm `reader_cache` pruning ignores `covers/` (`cache.stale_chapters` skips non-numeric directory names, so it should).

- [ ] **Step 5: Commit**

```bash
git add backend/app/reader/covers.py backend/app/api/routes_series.py backend/tests/test_series_cover_api.py
git commit -m "feat(backend): serve series covers from the LAN"
```

### Task 4: Positions that carry their reading time

**Files:**
- Modify: `backend/app/api/routes_reader.py` (`PositionIn`, `save_position` route), `backend/app/api/reader_service.py:298-318` (`save_position`)
- Test: `backend/tests/test_reader_position_read_at.py`

**Interfaces:**
- Produces: `PositionIn.read_at: datetime | None = None` (timezone-aware). `reader_service.save_position(session, series_id, chapter_id, page, read_at: datetime | None = None) -> bool`, True when the row was written. `PUT /api/reader/series/{id}/position` → `{"ok": True, "applied": bool}`.

- [ ] **Step 1: Write the failing tests** (series and two chapters via the `tests/test_reader_api.py` helpers; read back `reading_position`):

```python
async def test_without_read_at_it_always_applies(client): ...
    # two PUTs, no read_at -> second wins, applied True both times

async def test_an_older_read_at_does_not_overwrite_a_newer_position(client):
    await put(chapter=c2, page=5)                              # web, now()
    body = await put(chapter=c1, page=3, read_at=now - 1 hour) # offline replay
    assert body == {"ok": True, "applied": False}
    assert stored() == (c2, 5)

async def test_a_newer_read_at_applies_and_becomes_updated_at(client):
    body = await put(chapter=c1, page=3, read_at=t)            # t = now - 1 minute, no row yet
    assert body["applied"] is True and stored_updated_at() == t

async def test_a_future_read_at_is_clamped_to_now(client):
    await put(chapter=c1, page=3, read_at=now + 1 day)
    assert stored_updated_at() <= db_now()
    assert (await put(chapter=c2, page=1))["applied"] is True  # a later web write still wins
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_reader_position_read_at.py -q`
Expected: FAIL, `applied` missing from the response.

- [ ] **Step 3: Widen `save_position`.** The upsert's timestamp becomes `least(coalesce(cast(:at as timestamptz), now()), now())`. With `read_at` present, the `do update` gets `where reading_position.updated_at < excluded.updated_at`. Without it, no `where`, as today. Add `returning 1` and report whether a row came back.

- [ ] **Step 4: Run the tests, then `tests/test_reader_api.py`, to verify both pass**

Expected: new file 4 passed; existing reader tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_reader.py backend/app/api/reader_service.py backend/tests/test_reader_position_read_at.py
git commit -m "feat(backend): let a replayed reading position lose to a newer one"
```

### Task 5: Completions that carry their reading time

**Files:**
- Modify: `backend/app/api/routes_reader.py` (`complete`), `backend/app/api/progress_queue.py` (`queue_progress_write`), `backend/app/handlers/progress_write.py` (pass the time on), `backend/app/handlers/progress_events.py` (`record`)
- Test: `backend/tests/test_reader_progress.py` (extend)

**Interfaces:**
- Consumes: Task 4's clamping expression.
- Produces:
  - `class CompleteIn(BaseModel): read_at: datetime | None = None`. `complete(chapter_id, session, body: CompleteIn | None = None)`, so the web's bodiless POST still works.
  - `queue_progress_write(session, series_id, chapter, *, source, read_at: datetime | None = None)`. Payload gains `"read_at": read_at.isoformat()` when given. The existing raise-the-chapter `update` also sets `payload.read_at` to the new value (or removes it when the new request has none), in the same statement, so chapter and time always move together.
  - `progress_events.record(..., at: datetime | None = None) -> bool`. `created_at` becomes `least(coalesce(cast(:at as timestamptz), now()), now())`.
  - `progress_write.handle` reads `ctx.payload.get("read_at")`, parses it with `datetime.fromisoformat`, and passes it as `at=`.

- [ ] **Step 1: Write the failing tests** in `tests/test_reader_progress.py`, following that file's `_series_at` and `_chapter` helpers and its way of running the handler on a leased job:

```python
async def test_a_completion_with_read_at_records_that_time(client):
    # series at progress 3; POST complete chapter 4 with read_at = now - 2 days; run the job
    assert progress_event_created_at() == read_at

async def test_a_completion_without_a_body_still_works(client):
    response = await client.post(f"/api/reader/chapters/{c4}/complete")
    assert response.json()["progress_queued"] is True

async def test_replayed_out_of_order_keeps_the_higher_chapter_with_its_time(client):
    # progress 3; complete ch 5 with read_at=t2, then ch 4 with read_at=t1 (t1 < t2); run the job
    assert payload_of_pending_job() == {"chapter": 5, "read_at": t2.isoformat(), ...}
    assert progress_event() == (5, t2)

async def test_a_future_completion_time_is_clamped(client): ...
    # read_at = now + 1 day -> progress_event.created_at <= db now()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_reader_progress.py -q`
Expected: the four new tests FAIL; the existing ones pass.

- [ ] **Step 3: Implement the four signature changes above.** Only the reader passes `read_at`. The progress button (`routes_series.py:879`) and `progress_push` call without it and keep `now()`.

- [ ] **Step 4: Run the whole suite and ruff**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, no lint findings.

- [ ] **Step 5: Document the client endpoints.** Add a short section "Endpoints the Android client uses" to `docs/architecture.md` after "The reader and the library". It names the four routes, says why each exists (scan identity; offline copies; nothing leaves the LAN; replayed reading must not move time or position backwards) and points to the spec.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_reader.py backend/app/api/progress_queue.py backend/app/handlers/progress_write.py backend/app/handlers/progress_events.py backend/tests/test_reader_progress.py docs/architecture.md
git commit -m "feat(backend): record when an offline chapter was actually read"
```
