# J-Novel Club parts as a prose source

Date: 2026-10-14
Status: approved design, awaiting implementation plan
Branch: `feat/jnovelclub-parts`, based on `feat/light-novels` (PR #251, not yet merged). It needs that
branch's prose pipeline: `series.kind`, `ProseSource`, `clean_chapter_html`, the EPUB writer and the
prose download branch.

## Goal

A light novel that J-Novel Club publishes can be mapped to J-Novel Club, and its pre-publication
parts are downloaded with the user's Premium membership, one EPUB per part. They are then read in
Komga, and reading progress flows to MyAnimeList and AniList like any other chapter. J-Novel Club
carries 7 of the 18 light novels on the user's lists today.

This is piece 1 of 3. The other two each get their own spec:

2. Owned volumes: read the user's J-Novel Club library and download each owned volume's official
   EPUB, downloading it again when `lastUpdated` changes. Volumes need their own rows and file
   naming.
3. Volume progress: write `num_volumes_read` / `progressVolumes` to MAL and AniList when a volume
   book is finished.

## Decisions taken with the user

| Question | Decision |
|---|---|
| Access the user has | Owned volumes and Premium membership |
| How volumes and parts coexist (pieces 1–2) | **Keep both.** Part EPUBs are never deleted when the volume is owned. The user chose this knowing J-Novel Club's stated wish below. |
| Where progress goes | MAL and AniList only, never back to J-Novel Club |
| Progress units | Parts move chapters read; volumes move volumes read (piece 3) |
| Credentials | `.env` first (`JNC_LOGIN`, `JNC_PASSWORD`, renews itself); otherwise sign in from Settings, which stores **only the token**, never the password |
| Expiring parts | Downloading stays opt-in; Soshuhen warns about parts expiring within 7 days that are not downloaded |
| Approach | A native `ProseSource`, built on each registry reload with its credentials, like MangaFire |

### J-Novel Club's position, recorded

Every part's `data.xhtml` carries the comment "I would not recommend using this content to build
EPUBs". The Terms of Service (j-novel.club/tos, last modified 3 October 2025):
- restrict Premium content to personal, non-commercial use;
- bar third-party tools that harm the service;
- bar reverse engineering.

The user chose to build EPUBs from parts for personal reading on their own Komga. The design keeps
to that:
- one account, the user's own;
- 1 request per second;
- no sharing;
- no use of any endpoint that is not the one J-Novel Club's own web reader calls.

## API contract

Gathered from J-Novel Club's own web bundle and observed live (anonymous calls), on 2026-10-14. It
is corroborated by `gvellut/jncep` at commit 85e8d38. J-Novel Club publishes no API documentation.
Every call sends `?format=json`; without it the API answers in protobuf.

| Purpose | Call | Notes |
|---|---|---|
| Sign in | `POST https://labs.j-novel.club/app/v2/auth/login?format=json` with `{"login", "password", "slim": true, "ttl": 1209600}` | 201 with `{id, ttl, created}`; `id` is the token. 401 wrong credentials, 429 too many attempts. The web app asks for a 14-day `ttl`. |
| Authenticated calls | header `Authorization: Bearer <id>` | 401 or 410 means the session is no longer valid |
| Sign out | `POST /app/v2/auth/logout` | 204 |
| Membership | `GET /app/v2/me?format=json` | `level` (USER, MEMBER, PREMIUM_MEMBER …), `subscriptionFeatures.premium` |
| Search | `GET /app/v2/series?format=json&query=<title>` | Anonymous. Returns NOVEL and MANGA series; `cover.thumbnailUrl`, `volumeCount`, `slug` |
| Whole series | `GET /app/v2/series/{slug}/aggregate?format=json` | Anonymous. `{series, volumes: [{volume, parts}]}`. Volume: `number`, `publishing`, `owned`. Part: `id` (PRT-…), `slug`, `number`, `title`, `preview`. |
| Part content | `GET https://labs.j-novel.club/embed/v2/{partId}/data.xhtml` with Bearer | `application/xhtml+xml`, plain XHTML, images as absolute CDN URLs. 402 needs purchase, 403 needs membership or login, 410 expired, 451 region. |

Part `number` counts across the whole series: The Apothecary Diaries volume 16 holds parts 204–216.

**Expiry.** A Premium member can read a part until a date the API does not report reliably: its
`expiration` field was null for every part of a volume published on 9 October. J-Novel Club's web
app and `jncep` both compute it from the volume's `publishing` date:
- the 15th, at 10:00, of the same month if the publishing day is before the 9th, otherwise of the
  next month;
- moved to the 16th or 17th when that day falls on a weekend.

The plan reads the timezone of that 10:00 from the web bundle and `jncep` before implementing it.
Preview parts, and parts of volumes the user owns, do not expire.

## 1. Sign-in and credentials

### `backend/app/sources/jnovel_auth.py`

Pure HTTP, no database, shaped like `mangadex_auth.py`.

- `@dataclass(frozen=True) class JncSession: token: str; expires_at: datetime`
- `class JncAuthError(RuntimeError)`
- `async def login(client, login: str, password: str, ttl: int = 1_209_600) -> JncSession`:
  401 raises `JncAuthError("wrong email or password")`, and 429 raises
  `JncAuthError("too many sign-in attempts, try again later")`.
- `async def logout(client, token: str) -> None`. Best effort; failures are logged.
- `class TokenKeeper`. It is built from either credentials (`login`, `password`) or a stored
  session, never both.
  - `async def token() -> str` returns a valid token. With credentials, it signs in when there is
    no session, and renews it 1 hour before `expires_at`.
  - `async def invalidate() -> None` is called on a 401 or 410. With credentials, the next `token()`
    signs in again. With only a stored session, there is nothing to renew with, so `token()` raises
    `NotConfigured("J-Novel Club sign-in expired; sign in again in Settings")`.
  - With neither credentials nor a session, `token()` raises
    `NotConfigured("J-Novel Club is not signed in")`.
  - Renewal runs under one `asyncio.Lock`, so parallel callers cause one sign-in.

### Where the credentials come from

1. `config.py` gains `jnc_login: str = ""` and `jnc_password: str = ""`, read from `JNC_LOGIN` and
   `JNC_PASSWORD`. When both are set they win, and Settings cannot change them.
2. Otherwise `settings_store` keys `jnc_token` and `jnc_token_expires_at` (ISO 8601), written only
   by the sign-in route.
   - Neither key is in `routes_settings.py`'s readable or editable set, so the token never reaches
     the browser.
   - `registry._configured_natives` reads them and builds the keeper, the same way it builds
     MangaFire from its cookie.

### Endpoints (`backend/app/api/routes_sources.py`)

| Route | Behaviour |
|---|---|
| `POST /api/sources/jnovelclub/sign-in` `{login, password}` | Calls `login()` and stores the token and expiry; the password is not logged or stored. Reloads the registry. Returns `{"signed_in": true, "expires_at": ...}`. A `JncAuthError` returns 400 with its message. If `.env` credentials are set, returns 409 "signed in from .env". |
| `DELETE /api/sources/jnovelclub/sign-in` | Calls `logout()` best effort, clears both keys, reloads the registry. Returns `{"signed_in": false}`. |
| `GET /api/sources/jnovelclub/session` | Returns `{"via": "env" \| "settings" \| "none", "expires_at": ... \| null, "level": ... \| null}`. `level` comes from `GET /me` when a token is available; a failure there leaves it null rather than failing the route. |

### Settings card

`frontend/src/features/settings/`, a J-Novel Club card next to the MangaFire one:

| State | Shows |
|---|---|
| Signed out | email and password fields and a Sign in button |
| Signed in | membership level, expiry date ("Premium · expires 28 Oct") and a Sign out button |
| `.env` | "Signed in from .env", no fields |

A failed sign-in shows the route's message.

## 2. The source

### `backend/app/sources/jnovelclub.py`

`class JNovelClubSource(ProseSource)`:
- `site = "jnovelclub"`, `domains = ("j-novel.club",)`.
- Constructed with a `TokenKeeper` and a client from `get_client(CatalogueRow(key="jnovelclub",
  base_url="https://labs.j-novel.club"))`.

**`search(titles)`** calls `GET /app/v2/series?format=json&query=<titles[0]>`. It keeps
`type == "NOVEL"` and returns `Candidate`s:
- `source_url = https://j-novel.club/series/{slug}`
- `cover_url = cover.thumbnailUrl`
- `chapter_count = None`
- `score = best_similarity` over `title`, `shortTitle` and `originalTitle`

Anonymous.

**`list_chapters(url)`** takes the slug from the URL and calls `/aggregate`. For every part of every
volume it returns a `ChapterRef`:
- `number = Decimal(part.number)`
- `url = https://j-novel.club/read/{part.slug}`
- `title = part.title`
- `volume = str(volume.number)`
- `available_until`: computed as in "Expiry" above. It is `None` for preview parts and for parts of
  owned volumes.

Anonymous. `owned` is only known when signed in, so the call sends the token when one is available,
and works without it.

**`fetch_chapter(chapter_url)`**:
1. Resolve the part id.
   - The URL carries the part slug. `GET /app/v2/parts/{slug}?format=json` gives the `id` (lookup
     by slug verified live; it answered 200 for `the-apothecary-diaries-volume-16-part-1`).
   - The plan may instead carry the id in the URL fragment (`#PRT-…`) to save that request, and
     decides from what the reader URL accepts.
2. `GET /embed/v2/{id}/data.xhtml` with the bearer token.
3. Status handling:
   - **401:** `keeper.invalidate()`, retry once, then let the keeper's `NotConfigured` propagate.
   - **402, 403, 410, 451:** `ChapterUnavailable`, with reasons: "needs purchase", "needs a
     membership", "expired", "not available in your region".
   - **404:** `ChapterUnavailable("gone")`.
4. Pass the `<body>` contents to `clean_chapter_html(fragment, chapter_url)` and return
   `ChapterText(title=None, body, images=[PageRef(url, headers={"Referer": "https://j-novel.club/"})])`.

Images stay webp; Komga's reader shows them.

### `ChapterRef.available_until`

`backend/app/sources/base.py`: `ChapterRef` gains `available_until: datetime | None = None`. Every
existing source leaves it unset.

### Registry and catalogue

- `registry.py`: `jnovelclub` joins `CONFIGURED_NATIVES`, built in `_configured_natives` from
  `.env` or the stored session. With neither, it is still built, with an empty keeper, so search
  works and fetches raise `NotConfigured`.
- Migration `0021_seed_jnovelclub`: a `site_catalogue` row (native, `en`, base
  `https://labs.j-novel.club`, `rate_limit` 1 request per second in the shape `site_catalogue`
  already uses), and an **enabled** `source_pref` row.

## 3. Expiry in the data model, and the warning

**Migration `0022_chapter_available_until`:** `chapter.available_until timestamptz null`. Null
means it never expires. There is no backfill.

**`chapter_discover`**:
- Its upsert writes `available_until`, and updates it on every rediscovery.
- After the upsert, it counts the series' chapters in `known`, `queued` or `failed` with
  `available_until` between now and now + 7 days.
- If there are any, it logs at warning level: "`<n>` parts expire on `<date>` and are not
  downloaded".
- It runs on the existing daily `CRON_CHAPTER_DISCOVER`.

**Series responses** (`LIST_SQL`, `LIST_SQL_ONE`) gain `expiring: {count, earliest} | null`. It is
computed from the same 7-day condition in the existing per-series chapter aggregate, never stored.

**Once a part has expired** nothing special happens. When it is fetched, J-Novel Club answers
403/410 and the chapter becomes `skipped` with the reason.

**Frontend:**

| Where | Shows |
|---|---|
| Series header | an amber badge "`<n>` parts expire `<date>`", with an existing warning token |
| Library card | a marker for series with expiring parts |
| Chapter table | "until `<date>`" on rows with a date, in the existing muted metadata style |

Downloading stays opt-in.

## 4. Matching, downloading, progress

**Matching:**
- `match_search` already limits light novels to prose sources, so J-Novel Club candidates appear in
  Review.
- For the user's 7 series:
  - 3 are unmapped (The Underdog of the Eight Greater Tribes, The Mythical Hero's Otherworld
    Chronicles, The Apothecary Diaries). They get J-Novel Club candidates on the next search.
  - 4 are mapped to manga sources (The Magic in this Other World Is Too Far Behind!, Seirei
    Gensouki, Teogonia, Arifureta). They need "Edit source" in Review.
- Nothing is remapped automatically.

**Downloading:**
- It goes through the existing prose branch of `download_batch` and `download_chapter`.
- Files are named `{slug} - Ch.{part number} - {title}.epub`.
- The cover and authors come from the user's list entries.
- An expired Settings token raises `NotConfigured`. In `download_batch` that leaves the batch's
  chapters `known` and fails the job with the message: it does not mark them skipped.
- **Plan check:** confirm how `download_batch` handles `NotConfigured` today, and add the handling
  if it is missing.

**Progress:**
- Finishing a part in Komga pushes its number as chapters read through the unchanged, forward-only
  `progress_push`.
- **Plan check:** series-wide part numbers can exceed the chapter total MAL or AniList hold for a
  light novel. Read how `progress_push`'s chapter ceiling treats a number above the total, and pin
  that behaviour with a test. If it would write an invalid value to a provider, clamp it to the
  provider's total and log it.

## 5. Testing

**Pure (no network, no database):**

| Area | Cases |
|---|---|
| `jnovel_auth`, via `httpx.MockTransport` | login body and token parsing; 401 and 429 errors; renewal 1 hour before expiry; renewal after `invalidate()`; a single sign-in under concurrent callers; `NotConfigured` with neither credential |
| Source, against fixtures recorded live (search, aggregate for The Apothecary Diaries, one preview part) | novels only; series-wide numbering (volume 16 = 204–216) with volume and title; expiry for publishing before and after the 9th, the weekend shift, and preview/owned parts without expiry; the body cleaned with image placeholders; 401 → invalidate → one retry → `NotConfigured`; 402/403/410/451/404 → `ChapterUnavailable` with the reason |

**Against Postgres:**

| Area | Cases |
|---|---|
| Migrations 0021 and 0022 | seed row enabled; nullable column |
| `chapter_discover` | stores and updates `available_until`; warns only for undownloaded parts within 7 days |
| Series responses | `expiring` count, earliest date, and null when there is nothing to report |
| Sign-in routes | token stored and password not stored; `GET /api/settings` never returns the token; sign-out clears it; session `via` for env/settings/none; wrong credentials → 400; `.env` configured → 409 |
| `download_batch` with a fake J-Novel Club source | `NotConfigured` leaves chapters `known` and fails the job; a 403 part becomes `skipped` |
| `progress_push` | a part number above the list's chapter total behaves as the plan pins it |

**Frontend:** `npm run build`, and a `grep` over `frontend/dist/` for every new class.

**Live, with the user's go-ahead** (it signs in with their account):
1. Sign in from Settings and check the card shows Premium and the expiry date.
2. Map The Apothecary Diaries to J-Novel Club.
3. Download one Premium part and one preview part.
4. Check them in Komga.
5. Finish one part and check that MAL or AniList moves.

## Out of scope

- Owned volume EPUBs (piece 2).
- Volume progress (piece 3).
- Writing progress back to J-Novel Club.
- J-Novel Club's manga.
- Automatic remapping of existing series.
- Deleting part files.
