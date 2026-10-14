# Light novels: prose series end to end

Date: 2026-10-14
Status: approved design, awaiting implementation plan

## Goal

A light novel on a user's MyAnimeList or AniList list is matched against a prose source, its
chapters download as EPUB files, and Komga serves them for reading in its web reader. Reading
progress flows back to the lists the same way it does for manga.

Content is English only. Sources are hand-written (`native`) for this block.

### What exists today

- Providers already report novels. MAL maps `novel` and `light_novel` to `NOVEL`, and AniList
  sends `format: NOVEL` (`providers/base.py:24`, `PROSE_FORMATS`).
- `list_sync` keeps those entries and creates a series for each one, but it records no kind. Their
  `match_search` then runs against image sources, which is meaningless.
- The only prose-aware logic is the merge guard from issue #88 (`crosses_prose_boundary`,
  `entry_kind_from_raw`, `series_kind_from_entries` in `handlers/list_sync.py`, and migration
  `0010`).
- Everything after matching assumes images: `PageRef`, `cbz.py`, `ComicInfo.xml`, the reader.
  Komga's library is created with `scanEpub: False`.

### Decomposition

Light novel support is four sub-projects. This spec covers the first three as one block:

1. **Media kind as a first-class field** on `series`, with routing by kind.
2. **Prose sources**: a text contract beside the image one, plus three native sources.
3. **EPUB output and Komga**: an EPUB writer, Komga scanning EPUB, metadata and covers.
4. *Later, separate spec:* a text reader in the Soshuhen web interface.

Also deferred, each to its own spec:

- Bundling chapters into volume EPUBs, together with RanobeDB as a volume metadata provider.
- Porting LNReader plugin templates to cover sites in bulk.
- Webnovel (Cloudflare plus paid locked chapters) and J-Novel Club (an authenticated publisher
  API).

## Decisions

| Decision | Choice | Reason |
|---|---|---|
| Output granularity | One EPUB per chapter | Keeps `chapter` = Komga book, so `chapter.state`, reconciliation and `progress_push` work unchanged. Volume bundling comes later with RanobeDB. |
| Contract shape | Parallel `ProseSource` beside `Source` (approach A) | Image code never sees text and text code never sees `descramble`. One branch point, in the handler. |
| First sources | lolobun.com, novelight.net, empirenovel.com | Two plain-HTML sites and one behind Cloudflare, which exercises the existing FlareSolverr path. |
| Komga library | Same library, `scanEpub: True` | Komga handles mixed CBZ and EPUB libraries. One folder per series stays. |
| Reading | Komga web reader | It reads EPUB already. The Soshuhen text reader is sub-project 4. |

## 1. Data model

### `series.kind`

A new nullable `text` column, `kind`, holding `comic`, `prose` or null.

- **Null means unknown and behaves as `comic`.** That is today's behaviour, so no existing series
  changes path unless a provider has already said it is a novel.
- `series.meta.kind_locked: true` marks a kind the user set by hand. Sync never overwrites a locked
  kind.

### Migration `0019_series_kind`

1. Add the column.
2. Backfill each series from its entries' `raw`. The rules match `series_kind_from_entries`: any
   comic entry makes the series `comic`, otherwise any prose entry makes it `prose`, otherwise
   null.
3. The migration carries its own copy of the MAL, AniList and MangaBaka format maps. Migrations
   must not import app code that will keep changing.

### Who sets it

- `list_sync` sets `kind` when it creates a series. When an entry attaches to an existing series,
  it recomputes `kind` from all of that series' entries with `series_kind_from_entries`, unless
  the kind is locked. A mixed series stays `comic`, the safe direction from issue #88.
- The user sets it with `POST /api/series/{id}/kind` (`{"kind": "comic" | "prose"}`), following the
  existing per-action routes such as `/auto-download`. This also sets
  `kind_locked`. It covers `local`-provider series and providers that state nothing.
- `series_kind_from_entries` keeps returning provider vocabulary (`MANGA` / `NOVEL`). A small
  mapping turns that into `comic` / `prose` where the column is written.

### Unchanged

- `chapter`. `file_path` ends in `.epub` for prose. `number`, `state` and `komga_book_id` keep
  their meaning.
- `source_mapping` and `series_candidate`. The source key identifies the source, and the source
  declares its own kind.
- Folder layout: one folder per series under the library root.

No `volume` table in this block.

## 2. Sources

### Contract (`sources/base.py`)

```python
class SiteSource(ABC):
    site: str
    domains: tuple[str, ...]
    kind: ClassVar[Literal["comic", "prose"]]

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]: ...
    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]: ...


class Source(SiteSource):            # kind = "comic"; name and methods unchanged
    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]: ...
    def descramble(self, data: bytes, page: PageRef) -> bytes: ...


class ProseSource(SiteSource):       # kind = "prose"
    async def fetch_chapter(self, chapter_url: str, *, language: str = "en") -> ChapterText: ...


@dataclass(frozen=True)
class ChapterText:
    title: str | None
    body: str              # sanitised XHTML fragment; images appear as {{img:N}}
    images: list[PageRef]  # index N in body refers to images[N]
```

`Source` keeps its name, so the existing image sources and templates don't change.

### Registry

- One registry holds both kinds. `all_sources(kind: str | None = None)` filters by kind.
- `get_source(site)` stays. Two narrowed getters are added, `get_comic_source(site) -> Source` and
  `get_prose_source(site) -> ProseSource`. Each raises `TypeError` if the site is the other kind,
  so a mismatched mapping fails loudly instead of calling a method that doesn't exist.

### Sanitising (`sources/prose.py`, pure)

`clean_chapter_html(fragment: str) -> tuple[str, list[str]]` returns the XHTML body with
placeholders, and the image URLs in order.

- Each source removes its own site chrome first: ads, navigation, translator banners. Then it
  passes the chapter fragment to the shared cleaner.
- Allowlisted elements: `p br hr em strong i b blockquote h1 h2 h3 h4 ul ol li img`. Any other
  element is unwrapped, so its text survives. `script`, `style`, `iframe`, `noscript` and `form`
  are dropped together with their content. Every attribute is dropped except `img@src`.
- `img` becomes the text `{{img:N}}` inside its own `<p>`, and its absolute URL is appended to the
  returned list.
- The output must parse as XML. Entities are normalised and void elements are self-closed.
- Parsing uses `selectolax`, already a dependency, and the XHTML is serialised by hand from the
  allowlisted nodes. The test parses the output with the standard library `xml.etree`. No new
  dependency.
- If the body has no text after cleaning, the source raises `ChapterUnavailable`.

### Errors

- A 404 on the chapter, an empty body, or a chapter the site marks locked or paywalled raises
  `ChapterUnavailable`, which the handler maps to `PermanentError`, as it does today.
- Cloudflare goes through `sources/net.py` unchanged. Without `flaresolverr_url` set, empirenovel
  fails with the error every Cloudflare-protected source raises today.

### The three sources

`sources/lolobun.py`, `sources/novelight.py`, `sources/empirenovel.py`:

- Native `ProseSource` classes, with catalogue rows marked `native` and keyed by the source's own
  `site` (the `0014` rule).
- Each parser is written from the real pages, fetched when the work starts. Recorded HTML fixtures
  for search, chapter list and chapter live under `backend/tests/fixtures/`.
- Observed while designing (2026-10-14): lolobun and novelight answer 200 with the content in
  server-rendered HTML (lolobun chapter text sits in `.text-content-box`, and novelight routes
  books under `/book/`). empirenovel answers a Cloudflare challenge (403, "Just a moment...").

## 3. EPUB output and Komga

### `downloader/epub.py`

`write_epub(chapter: EpubChapter, destination: Path) -> None` hand-rolls the zip the same way
`cbz.py` does. No new dependency.

```python
@dataclass
class EpubChapter:
    series: str
    number: Decimal
    identifier: str               # stable: f"soshuhen:{series_id}:{number}"
    title: str | None
    body: str                     # ChapterText.body
    images: list[bytes]           # same order as ChapterText.images
    cover: bytes | None
    language: str = "en"
    authors: list[str] = field(default_factory=list)
    summary: str | None = None
```

Archive layout:

```
mimetype                      first entry, stored uncompressed: application/epub+zip
META-INF/container.xml        points to OEBPS/content.opf
OEBPS/content.opf             EPUB 3 package
OEBPS/nav.xhtml               one entry, the chapter
OEBPS/chapter.xhtml           body with {{img:N}} resolved to images/NNN.ext
OEBPS/images/NNN.ext          extension from bytes, using cbz.page_extension
OEBPS/images/cover.ext        when a cover exists
```

- An unresolved `{{img:N}}` (an image that failed to download) fails the chapter. No half-built
  file ships.
- It writes to a temp file and renames it, as `write_cbz` does.

### OPF metadata

These fields come from Komga's own `EpubMetadataProvider` and `EpubExtractor`, verified against
`gotson/komga` master on 2026-10-14:

| Komga reads | Written as |
|---|---|
| Book title: `metadata > title` | `dc:title`: `"{series} - Chapter {number}"`, plus `": {title}"` when the source gives one |
| Book number: `meta[property=belongs-to-collection]@id`, then `meta[refines=#id][property=group-position]` | `group-position` = the chapter number |
| Series title: `meta[property=belongs-to-collection]` text | the series' canonical title |
| Authors: `metadata > creator`, role from `opf:role` or `marc:relators` refinement, default writer | `dc:creator` for each author the provider supplied |
| Summary: `metadata > description` | the series summary when known |
| Language: `metadata > language` | `dc:language` = `en` |
| Cover: manifest item with `properties="cover-image"` | the series cover |

Also set: `dc:identifier` (as above) and `meta property="dcterms:modified"`, both required by
EPUB 3, and `meta property="belongs-to-collection"` with `collection-type` = `series`.

### Cover

The cover is fetched once per batch from `cover_url_for(series_id)` (`handlers/komga_scan.py:146`)
and embedded in every chapter. Komga takes book thumbnails from the `cover-image` item, and a
scraped chapter has no art of its own. If no cover is available, the EPUB is written without one.

### Paths (`downloader/paths.py`)

- `chapter_filename(series_slug, number, title=None, *, kind="comic")` returns `.epub` for prose and
  `.cbz` otherwise. `chapter_path` passes `kind` through.
- `number_from_filename` accepts both extensions.

### Komga library

- `library_payload` sets `"scanEpub": True`. `importEpubBook` and `importEpubSeries` are already
  `True`.
- **Existing installs** have a library created with `scanEpub: False`. Bootstrap reads the library
  and, if `scanEpub` is false, sends `PATCH /api/v1/libraries/{libraryId}` with
  `{"scanEpub": true}`. That endpoint accepts partial bodies; fields left out are not changed (Komga
  `LibraryController.updateLibraryById`, since 1.3.0). The deprecated `PUT` is not used.

### Reader cache

Prose doesn't use `reader-cache`. The download lane writes the EPUB directly. The comic flow
(cache, then archive) is unchanged.

## 4. Handlers and API

The chain doesn't change. Each handler reads `series.kind` once; null counts as `comic`.

| Component | Change |
|---|---|
| `match_search` | `all_sources(kind=series_kind)` instead of `all_sources()`. |
| Mapping confirmation (`POST /api/series/{id}/mapping`) | Rejects with 422 a mapping whose source kind differs from the series kind. |
| `chapter_discover` | Passes `kind` to `chapter_path`. A file with the other extension also counts as present, so a corrected kind does not redownload everything. |
| `download_batch`, `download_chapter` | One branch at the archive write. **comic**: unchanged (`list_pages` → reader cache → `write_cbz`). **prose**: `get_prose_source().fetch_chapter()`, fetch `images` through the same rate-limited fetcher, fetch the cover, then `write_epub`. Batching, leasing, partial results with the remainder requeued, and the `ChapterUnavailable` → `PermanentError` mapping sit outside the branch and don't change. |
| `komga_scan` | No change beyond `number_from_filename` accepting `.epub`. |
| `progress_push` | No change. Komga marks an EPUB `completed` when the reader's total progression reaches ≥ 0.99 (`BookLifecycle.markProgression`, verified 2026-10-14), so chapter = book read progress keeps flowing. |
| `list_sync` | Sets and recomputes `kind` (Section 1). Its auto-download `MATCH_SEARCH` now reaches prose sources. |
| `POST /api/series/{id}/kind` (new) | Sets `kind` and `kind_locked`. |
| Series API responses | Include `kind`. |

### Frontend (this block only)

- A kind badge on library rows and the series header.
- A comic/prose selector on the series detail page, calling `POST /api/series/{id}/kind`.
- For a prose series, the read action opens the chapter's Komga book URL instead of the image
  reader, which can't render an EPUB. Sub-project 4 replaces this.
- Review needs no change, because its candidates are already filtered by kind.
- Token-layer rules apply. Any new class must be confirmed by a `grep` over `frontend/dist/`.

### Docs

- `docs/architecture.md`: the prose branch and the kind routing.
- `docs/data-model.md`: `series.kind` and `kind_locked`.
- `docs/features.md`: light novel support, the three sources, empirenovel needing FlareSolverr.
- `CLAUDE.md` "Module boundaries": `ProseSource`, and that sources declare a kind.

## 5. Testing

### Pure, no network, no DB

- `clean_chapter_html`:
  - Keeps allowlisted tags and unwraps unknown ones without losing their text.
  - Drops `script`, `style`, `iframe` and every attribute except `img@src`.
  - Its output parses as XML.
  - Images become ordered placeholders with absolute URLs.
- Each source, against recorded fixtures:
  - Search returns candidates.
  - The chapter list has the right numbers, order and URLs.
  - A chapter returns a non-empty body with the site chrome removed.
  - A locked or 404 chapter raises `ChapterUnavailable`.
  - For empirenovel, fixtures are recorded through FlareSolverr, and a challenge response raises
    the existing `net.py` error.
- `write_epub`:
  - `mimetype` is the first entry and stored uncompressed.
  - `container.xml` points to the OPF, and every manifest href exists in the zip.
  - No `{{img:` remains.
  - The cover item carries `cover-image`.
  - `belongs-to-collection` and `group-position` are present and refined correctly.
  - A missing image raises.
- `chapter_filename` and `number_from_filename` round-trip both extensions.
- `library_payload` has `scanEpub: True`. The bootstrap reconcile sends the PATCH only when the
  recorded library has it off.
- Registry: `all_sources(kind=...)` filters, and the narrowed getters raise on the wrong kind.

### Against Postgres

- Migration `0019`, on seeded entries:
  - MAL `light_novel` → `prose`
  - AniList `NOVEL` → `prose`
  - mixed comic and prose → `comic`
  - no kind stated → null
- `list_sync`: sets kind on create, recomputes on attach, leaves a locked kind alone.
- `match_search`: searches only same-kind sources, with fake comic and prose sources installed in
  the registry.
- Mapping confirmation rejects a kind mismatch.
- `download_batch` on a prose series writes `.epub` files and marks the chapters downloaded. The
  existing comic tests stay green unchanged.
- `chapter_discover` treats an existing file with the other extension as present.

### Manual end to end

This needs the real stack; fixtures can't prove Komga's behaviour.

1. `docker compose build api && docker compose up -d --force-recreate api worker worker-download`.
2. For one real novel per source: confirm a mapping and download three chapters.
3. In Komga: the series appears once, chapters are ordered by number, titles and thumbnails are
   correct, and the web reader opens them.
4. Read one chapter to the end in Komga, then confirm `progress_push` advances the list entry.

### Checks

- `ruff check app/ tests/`
- The full pytest suite on a fresh Postgres container
- `npm run build`
- A `grep` over `frontend/dist/` for each new class

## Out of scope

- The Soshuhen web text reader (sub-project 4).
- Volume EPUBs, and RanobeDB.
- LNReader templates, Webnovel, J-Novel Club.
- Languages other than English.
