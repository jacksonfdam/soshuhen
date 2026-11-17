# Reading a chapter aloud in the web reader

## Why

The accessible reader proof of concept (`poc/accessible-reader/`) reads one image from the command
line: it finds the panels, reads the speech bubbles, and speaks them into an audio file. It showed
the idea works and nothing more. It is not connected to the library, and its OCR engine, manga-ocr,
reads Japanese only, while every confirmed source in this installation is an English one.

The user wants to open a chapter of a real series in the web reader and hear it. That is the test
that says whether the idea is worth carrying further: real lettering, real layouts, real chapters,
with the reader turning its own pages.

## Goals

- In the comic reader, a **Read aloud** control starts narration of the page on screen, in reading
  order, and keeps going: it turns the page when a page is finished and stops at the end of the
  chapter.
- It works on **any comic chapter the reader can already open**, whether it comes from an archive in
  the library, from the reader cache, or streamed from the source.
- **The pages never leave the installation.** Recognition runs in a local service and speech is
  produced by the browser.
- The text being spoken is **also on screen** as a transcript, as ordinary markup a screen reader or
  a braille display can read.
- It **sounds and is driven like the prose reader's read-aloud**, which already exists: the same
  bar (pause, back, forward, speed, voice) and the same saved voice and speed.
- The whole feature is **optional and off by default**. An installation that does not configure the
  new service sees no new control and behaves exactly as before.

## Non-goals

- Describing the artwork, or saying who is speaking. A listener hears the lettering and where the
  panels fall. That needs a vision model and is the "Claude vision" option in Approaches.
- Languages other than English. The seam for it exists (the transcript names its language), the
  work does not.
- Translating.
- Changing how the prose reader behaves. Its read-aloud code moves so both readers can use it, and
  that is all that changes there.
- The Android client.
- A second voice or timed silences to mark panels, which the proof of concept had. A spoken
  announcement marks a panel; the shared player speaks in one voice.
- Storing transcripts on the server, correcting them by hand, or searching them.
- Audio files, downloads of narration, or server-side speech.
- Replacing the proof of concept. It stays where it is as the record of the first experiment.

## Anti-goals

- **A page sent to a third party.** No page image and no page text goes to an outside service, by
  default or by fallback.
- **A reader that depends on the narrator.** With the service stopped, slow or broken, every existing
  reader function works unchanged and the failure is said in one sentence, once.
- **Narration that moves progress the user did not earn, or fails to move progress they did.**
  Listening to the last page finishes the chapter exactly as turning to its end does, through the
  same call, and nothing else writes progress.
- **Two voices at once.** The transcript is not a live region, so a screen reader does not talk over
  the narration.
- **A fat shared image.** The recognition stack does not go into `soshuhen:local`, which four
  services run.

## Approaches

**Where recognition runs.** Decided with the user: **a local sidecar service.**

- *Local OCR in its own container (chosen).* Pages stay on the machine, there is no per-page cost
  and no key. Quality on comic lettering had to be checked, and was (below).
- *A vision model over an API.* Reads lettering better, and could describe artwork and attribute
  speakers. Sends every page out, costs per page, needs a key. Not built; the transcript contract is
  what a second engine would have to produce, so it can be added behind the same route later.
- *OCR inside the backend image.* No new service, but the dependencies land in the api, both workers
  and bootstrap. Rejected for that.

**Which engine.** Tried on eight pages from four series in the library: five paged manga pages, two
webtoon pages, and one 800 x 16,222 strip. Timings are CPU-only on the development Mac.

| Engine | Per page | Long strip | Size | Result |
| --- | --- | --- | --- | --- |
| RapidOCR 3.10 (PP-OCRv6 small, ONNX Runtime) | 0.3 to 0.9 s | 3 to 5 s in tiles | about 110 MB installed, models included, plus OpenCV | Finds and reads the lettering itself, including captions and text outside white bubbles. Nearly every line correct. |
| EasyOCR 1.7 | 3 to 9 s | 55 s | needs PyTorch, about 600 MB | Finds the same text, reads it worse (mixed case, wrong letters). |
| Tesseract 5.5 | 0.1 to 0.5 s | 2.5 s | small | Usable only on a clean crop. On a whole page it reads art as text and misses most lettering. |

**RapidOCR** is the engine: Apache-2.0, no PyTorch, and its three model files (30 MB) ship inside
the wheel, so the container needs no network at run time.

**How text is found.** The proof of concept found bubbles by their shape (a bright convex blob with
ink in it) and handed each crop to the reader. On real pages that detector missed most text that is
not in a white bubble: on the long strip it found two lettered regions where the engine's own text
detector found twenty-seven lines. So the engine detects text lines on the whole page, and geometry
groups the lines into blocks. The proof of concept's panel detection and its recursive reading
order are kept; its bubble detector is not used.

**Where speech is made.** *My call:* the browser's speech synthesis, through the player the prose
reader already has (`features/prose-reader/readAloud.ts`, `webSpeech.ts`, `ReadAloudBar.tsx`), not
audio rendered on the server. That player already handles what a new one would have to learn again:
Chrome cutting an utterance off after fifteen seconds, Chrome on Android never resuming a pause, and
the late callback of a cancelled utterance. It needs no ffmpeg and no speech service, and keeps the
page text on the machine. The trade is that the voice is whichever voices the listener's browser
and operating system have. Writing a second player inside the comic reader was the alternative, and
is rejected: two copies of those workarounds would drift.

**Where transcripts are kept.** *My call:* nowhere on the server. A page takes under a second, the
reader asks for the next page's transcript while the current one is spoken, and the response carries
a cache header so the browser does not ask twice. A table can come later if transcripts gain a
second use; none exists today, and this way the change has no migration to roll back.

## What was seen that is not solved

The builder should not chase these; they are the honest limits of the first version.

- Words sometimes come back joined, where the lettering is tight.
- Sound effects drawn into the art, page numbers and credits are sometimes read as text.
- A line is occasionally left out of its block when it sits far from the rest of the bubble.
- Lettering in capitals comes back in capitals with stray lower-case letters.
- Panel detection is the proof of concept's contour heuristic, unchanged. On the five paged pages it
  found between two and six panels and the order was right on the six-panel page; on one page it
  merged several panels into one. A borderless page comes back as a single panel. Both are accepted:
  the blocks are still read in order inside whatever panel they land in, and "Panel 1" for a whole
  page is a correct, if unhelpful, announcement.

## Starting values from the trial

So the result can be reproduced; every one of them is the builder's to move.

- `RapidOCR()` with its defaults: PP-OCRv6 small detection and recognition models and the angle
  classifier, on ONNX Runtime. The default recognition model reads Latin script. All three model
  files are listed in the wheel's `RECORD` under `rapidocr/models/`, so nothing is downloaded.
- The page is passed whole, in colour. Tiles are 1,600 px tall with a 200 px overlap, used when the
  page is taller than 2,400 px.
- A line is kept at a confidence of 0.6 or more.
- Two lines join a block when the vertical gap between them is under 0.8 of the shorter line's
  height and they overlap horizontally by more than 0.3 of the narrower line's width.
- A page is a strip when its height is more than 2.5 times its width.
- Panel and block ordering use a tolerance of one per cent of the page's short side.

## How it works

```
browser ── GET …/pages/{index}/transcript ──> api ── POST /v1/pages (image bytes) ──> narrator
   │                                           │                                         │
   │                                           └─ gets the bytes from serve_page         └─ detect lines, group,
   └─ speaks the blocks, shows the transcript,    (archive, cache or source)                find panels, order
      turns the page
```

### The narrator service

A new top-level folder `narrator/`, beside `backend/` and `frontend/`: its own `pyproject.toml`,
Dockerfile, tests and image. It imports nothing from `backend/` and has no database, no volume and
no outbound network. It is one more optional compose service behind a profile, like `comick` and
`flaresolverr`.

Inside, the same shape as the proof of concept: geometry and ordering are pure functions, and the
engine sits behind a small protocol so the tests use a stand-in and never load a model.

- **Lines.** RapidOCR detects and recognises text lines on the page. A page taller than about one
  and a half times the tile height is cut into overlapping tiles first, because the engine scales a
  page down to 2,000 px on its long side and a 16,000 px strip becomes unreadable. Lines found twice
  in an overlap are merged.
- **Filtering.** A line is dropped when the engine's confidence is low, or when it has fewer than
  two Latin letters and is not pure punctuation.
- **Blocks.** Lines stacked closely with overlapping horizontal extents are one block, read top to
  bottom. A block is what a listener hears as one utterance: usually one bubble or one caption.
- **Clean-up for speech.** Within a block: a word broken by a hyphen at a line end is rejoined,
  whitespace is collapsed, and the text is put in sentence case, because speech engines spell out
  short words in capitals.
- **Panels and order.** `detect_panels` and `reading_order` from the proof of concept, copied with
  their tests. Panels are ordered by the requested direction, blocks inside a panel the same way. A
  page more than two and a half times as tall as it is wide is treated as a single column read top
  to bottom, with no panel detection. A block belongs to the panel it overlaps most.

Contract:

```
POST /v1/pages?direction=rtl|ltr        body: the image bytes, as the reader serves them
200  {
       "engine": "rapidocr 3.10.0 / PP-OCRv6 small",
       "language": "en",
       "width": 1114, "height": 1600,
       "panels": [
         { "box": [x, y, w, h],
           "blocks": [ { "box": [x, y, w, h], "text": "…" } ] }
       ]
     }
413  the body is larger than the limit
422  the body is not an image that decodes
GET /healthz
```

A panel with no blocks is returned, not left out: the reader announces it as wordless, as the proof
of concept does. Recognition is CPU-bound, so it runs off the event loop, one page at a time.

The container runs as a non-root user, exposes its port to the compose network only, and has no
volume. It decodes images that came from third-party sites, which is one more reason it is a
separate process with nothing mounted.

*Found while building:* ONNX Runtime 1.31 reports usage to a Microsoft collector by default, on
Linux and macOS, starting when the runtime loads. That is outbound traffic this design forbids, so
the service forces the runtime's opt-out on import and in the image, and its compose network is
marked `internal`, shared only with `api`, so the container has no route off the host whatever a
dependency attempts.

### The api

- `Settings.narrator_url`, from `NARRATOR_URL`, empty by default. Empty means the feature is off.
- A pure client beside the other edges, `backend/app/reader/narration.py`: bytes and a direction in,
  a transcript out, raising one error type when the service cannot answer. It touches no database.
- `reader_service.transcript(session, row, index, direction)`: gets the page through the existing
  `serve_page`, so a streamed page is fetched, cached and counted towards assembly exactly as when it
  is displayed, then asks the client.
- `GET /api/reader/chapters/{chapter_id}/pages/{index}/transcript?direction=rtl|ltr` in
  `routes_reader.py`, answering the narrator's JSON unchanged, with
  `Cache-Control: private, max-age=86400`. Not `immutable`: a later engine reads the same page
  differently.
- `GET /api/reader/narration`, answering `{"available": true|false}` from whether the URL is set,
  and nothing more: it does not probe the service. A narrator that is configured but stopped shows
  the control and fails when asked, in the one sentence described below. The chapter manifest is
  left as it is, because the Android client decodes it.

Errors, through the existing `service_errors`: everything `serve_page` already raises keeps its
status (404, 409 for prose, 410, 502). Narration not configured is 503. The narrator unreachable,
timing out or answering an error is 502 with a detail that names the narrator, so it cannot be
mistaken for a source failure.

No migration, no job type, nothing queued.

### The reader screen

**What moves first.** Feature folders never import from each other, so what both readers need
leaves `features/prose-reader/`: `readAloud.ts` with its test and `webSpeech.ts` go to `lib/`, and
`ReadAloudBar.tsx` goes to `ui/`. The bar's two skip labels say "paragraph" today; they become a
prop, so the comic reader can say "line". The settings stay under the `reader:read-aloud` key, so a
voice and speed chosen in one reader are the ones heard in the other. The prose reader's imports
change and its behaviour does not; its own hook, `useReadAloud.ts`, stays where it is because it
reads the book's markup. This is a commit of its own, before anything is added.

One thing the shared player cannot say today: it reports `stopped` both when it runs out of text and
when it is stopped or the engine fails, and only the first should turn a page. It gains a way to
tell them apart, with a test.

The rest is inside `frontend/src/features/reader/`; the transcript types and the two calls go in
`lib/api.ts`.

- **Control.** A Read aloud button in `DesktopChrome` and `TabletChrome`, shown only when
  `/api/reader/narration` says it is available and the browser can speak. The `n` key does the same
  through `useReaderKeys`. Starting shows the shared bar; its close button stops narration. Browsers
  refuse to speak before the user has acted on the page, so narration always starts from that
  button or key and is never started on load.
- **Script.** A pure function turns a transcript into the player's list of blocks: the page number,
  then for each panel its number and its text blocks, with "no text" for a wordless panel. Back and
  forward on the bar move one block.
- **Turning pages.** When the player runs out of a page's blocks, narration calls the reader's own
  `forward`. In a paged mode that shows the next page, and at the end of the chapter it shows the
  end screen and marks the chapter finished, through the code that already does that. Narration
  then says the chapter has ended and stops; it does not open the next chapter on its own. In long
  strip mode, where `forward` only scrolls, narration keeps its own page cursor, starting from the
  page on screen, and scrolls each page into view as it reaches it.
- **Double page mode.** `forward` moves a whole spread there, so narration reads every page of the
  spread on screen, in page order, before calling it.
- **Direction.** `rtl` for the right-to-left paged mode, `ltr` for every other mode, which is how
  the reader itself draws them.
- **Interruptions.** Turning the page by hand, seeking or changing chapter cancels what is being
  said and, if narration is on, starts on the new page. Leaving the reader stops it.
- **Transcript.** A panel listing the current page's panels and blocks as headings and list items,
  opened from the same chrome, with the block being spoken marked. Plain markup with no live region.
- **Failure.** A transcript that cannot be fetched is said once ("This page could not be read
  aloud") and shown in the transcript panel. Narration stays on that page; it does not skip ahead
  through a chapter it cannot read.
- **Looking ahead.** While a page is spoken, the next page's transcript is requested.

The usual rules of the interface apply: tokens only from `tailwind.config.ts`, classes verified in
`frontend/dist/`, nothing imported from another feature folder.

### Configuration and running it

- Compose: a `narrator` service built from `./narrator`, `profiles: ["narrator"]`, `expose` only.
  `NARRATOR_URL: ${NARRATOR_URL:-}` is added to the `api` environment.
- Turning it on: `NARRATOR_URL=http://narrator:8000` in `.env`, then
  `docker compose --profile narrator up -d --build`.
- Turning it off: remove the variable and recreate `api`. Nothing is left behind.
- `docs/features.md`, `docs/configuration.md`, `docs/architecture.md` and the rebuild section of
  `CLAUDE.md` gain the new service. `.env.example` gains the variable, commented.

### Tests

- `narrator/`: grouping, filtering, clean-up, tiling and ordering against drawn pages and a stand-in
  engine; one test that runs the real engine on a page the test draws itself, with English text in
  bubbles, since the models are in the wheel and need no network. No page from the library is ever a
  fixture.
- Backend: the client against a recorded response with `httpx.MockTransport`, as the Komga client is
  tested; the route for the happy path, not configured, narrator down, a prose chapter, and a page
  index out of range.
- Frontend: the script builder as a `node --test` unit, like the reader's other pure helpers; the
  moved player's existing tests keep passing from their new place, plus one for the new signal.
- CI gains a job for `narrator/` (ruff and pytest).

## Left to the builder

- Thresholds: confidence, the grouping distances, tile height and overlap, the body size limit, the
  request timeout.
- How lines found twice in a tile overlap are merged.
- Names inside `narrator/`, and its web framework (FastAPI, as the backend uses, unless something is
  lighter and no less clear).
- How the shared player tells running out of text from being stopped.
- Whether the transcript is a sheet or a side panel, and the copy, in the interface's existing voice.
- How the strip cursor behaves when the user scrolls far away by hand.
- Base image and dependency pins for `narrator/`, with versions at least two weeks old.

## Done

With the `narrator` profile running, in the web interface: opening a downloaded chapter of a
right-to-left manga and pressing Read aloud speaks the page in panel order, turns the pages by
itself, and at the last page shows the end of the chapter and moves list progress as reading it
would. The same on a long-strip chapter, top to bottom, and on a chapter that is streamed rather
than downloaded. The transcript panel shows what is being said. The prose reader's read-aloud works
as it did. With `NARRATOR_URL` unset, the comic reader shows no narration control and nothing else
changes. CI passes.
