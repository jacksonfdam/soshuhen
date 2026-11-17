# Reader Narration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Read aloud control in the comic reader that speaks a chapter page by page, in reading order, from text recognised by a local sidecar.

**Architecture:** A new `narrator/` service (RapidOCR on ONNX Runtime) turns a page image into panels and text blocks. The api gets the page through the existing `serve_page`, asks the narrator, and answers the transcript. The reader feeds the transcript to the read-aloud player the prose reader already has, moved to `lib/` and `ui/` so both readers share it.

**Tech Stack:** Python 3.12, FastAPI, RapidOCR 3.10.0, ONNX Runtime 1.32.0, OpenCV headless 5.0.0.93, httpx; React, TypeScript, Tailwind 4, the browser's `speechSynthesis`.

**Spec:** `docs/superpowers/specs/2026-11-17-reader-narration-design.md`

## Global Constraints

- No page image and no page text leaves the installation. No outside service is called, by default or as a fallback.
- No page from the library is ever a test fixture. Tests draw their own pages and invent their own text.
- The feature is off unless `NARRATOR_URL` is set. With it unset, nothing a user sees changes.
- No migration, no job type, nothing queued. The chapter manifest (`GET /api/reader/chapters/{id}`) is not changed.
- `narrator/` imports nothing from `backend/` or `poc/`, has no database, no volume, no outbound network at run time.
- New Python dependencies are installed with `--exclude-newer 2026-11-03` (versions at least two weeks old) and pinned exactly in `narrator/pyproject.toml`.
- Frontend: colours, sizes and spacing only from `frontend/tailwind.config.ts`; a class is real only if `grep` finds it in `frontend/dist/` after `npm run build`; feature folders never import from each other.
- Comments explain why a line exists, never what it does.
- Commits: English, one focused change each, files staged by name (never `git add -A`), no assistant attribution of any kind in messages.
- Backend tests need a Postgres of this worktree's own: `docker run -d --name manga-pg-narration -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5434:5432 postgres:17-alpine`, then prefix test commands with `POSTGRES_HOST=localhost POSTGRES_PORT=5434`.

## Review Focus

Conditions the spec implies and a person will meet, most likely first. Each is pinned by a test or check in the task named.

1. **A page with no lettering** (splash art, a cover). The narrator answers 200 with wordless panels; the reader says the page number and "No text." and turns the page instead of stalling. Tasks 4 and 11.
2. **A very tall strip page** (16,000 px). It is tiled, a line in a tile overlap is spoken once, and boxes are in page coordinates. Task 2.
3. **The narrator stops or stalls mid-chapter.** The api answers 502 within its timeout; the reader says its one sentence, stays on the page, and does not walk on through the chapter. Tasks 7 and 12.
4. **Pages turned quickly by hand while narration is on.** A transcript that arrives for a page no longer on screen is never spoken. Task 12.
5. **A page the narrator cannot decode** (a truncated download, a format OpenCV lacks). 422 from the narrator, 502 from the api naming the narrator, and the same one sentence in the reader. Tasks 5 and 7.

---

### Task 1: Narrator package with geometry and reading order

**Files:**
- Create: `narrator/pyproject.toml`, `narrator/.gitignore`, `narrator/narrator/__init__.py`, `narrator/narrator/geometry.py`, `narrator/narrator/panels.py`, `narrator/tests/__init__.py`, `narrator/tests/test_reading_order.py`, `narrator/tests/test_panels.py`

**Interfaces:**
- Produces: `narrator.geometry.Box(x, y, width, height)` with `right`, `bottom`, `area`, `center`, `overlap(other) -> int`; `narrator.panels.detect_panels(gray: np.ndarray) -> list[Box]`; `narrator.panels.reading_order(items, box_of=lambda item: item, *, right_to_left=True, tolerance=0) -> list[T]`.

- [ ] **Step 1: Write `narrator/pyproject.toml`**

Project `soshuhen-narrator`, `requires-python = ">=3.12"`, packages found under `narrator/`. Dependencies pinned exactly: `rapidocr==3.10.0`, `onnxruntime==1.32.0`, `opencv-python-headless==5.0.0.93`, `numpy==2.5.5`, plus `fastapi` and `uvicorn` pinned to the newest versions `uv pip install --exclude-newer 2026-11-03` resolves. Extra `dev`: `pytest`, `httpx`, `ruff`, pinned the same way. `[tool.pytest.ini_options] pythonpath = ["."]`, `[tool.ruff] line-length = 100`. `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`.

- [ ] **Step 2: Install**

Run from `narrator/`: `uv venv --python 3.12 && uv pip install --exclude-newer 2026-11-03 -e ".[dev]"`
Expected: installs without resolving `torch`.

- [ ] **Step 3: Copy the two modules and their tests**

`poc/accessible-reader/manga_narrator/geometry.py` and `panels.py` to `narrator/narrator/`, and `poc/accessible-reader/tests/test_reading_order.py` to `narrator/tests/`, changing only the import prefix `manga_narrator` to `narrator`. Keep every comment.

- [ ] **Step 4: Write `narrator/tests/test_panels.py`**

```python
def test_three_bordered_panels_are_found():      # draw white 600x800, three black-bordered rectangles
    assert len(detect_panels(page)) == 3

def test_a_page_with_no_borders_is_one_panel_covering_it():   # plain grey 600x800
    assert detect_panels(page) == [Box(0, 0, 600, 800)]
```

- [ ] **Step 5: Run**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check .`
Expected: all pass, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add narrator/pyproject.toml narrator/.gitignore narrator/narrator narrator/tests
git commit -m "feat(narrator): start the service with panel detection and reading order"
```

---

### Task 2: Text lines, filtering and tiling

**Files:**
- Create: `narrator/narrator/lines.py`, `narrator/tests/conftest.py`, `narrator/tests/test_lines.py`

**Interfaces:**
- Consumes: `Box`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class TextLine: box: Box; text: str; score: float

  class LineEngine(Protocol):
      name: str          # reported to clients, e.g. "rapidocr 3.10.0 / PP-OCRv6 small"
      language: str      # ISO 639-1
      def read(self, image: np.ndarray) -> list[TextLine]: ...   # BGR image, boxes relative to it

  MIN_SCORE = 0.6
  TILE_HEIGHT = 1600
  TILE_OVERLAP = 200
  def is_text(line: TextLine) -> bool
  def tile_tops(height: int) -> list[int]
  def read_lines(image: np.ndarray, engine: LineEngine) -> list[TextLine]
  ```
- `tests/conftest.py` produces `FakeEngine(lines_by_call: list[list[TextLine]])`, with `name = "fake"`, `language = "en"`, a `seen: list[tuple[int, int]]` of the (height, width) of each image it was handed, returning the next list per call and `[]` once exhausted; and `blank(width, height) -> np.ndarray`, a white BGR image, which the tests below call `image` (800x5000) and `small_image` (800x1000).

- [ ] **Step 1: Write the failing tests** in `tests/test_lines.py`

```python
def line(text, score=0.99, box=Box(10, 10, 100, 20)): return TextLine(box, text, score)

def test_low_confidence_is_dropped():            assert not is_text(line("HELLO", 0.59))
def test_two_latin_letters_are_enough():         assert is_text(line("NO"))
def test_a_lone_letter_or_digit_is_noise():      assert not is_text(line("4")) and not is_text(line("A"))
def test_other_scripts_are_noise():              assert not is_text(line("が"))
def test_pure_punctuation_is_kept():             assert is_text(line("?!")) and is_text(line("..."))

def test_a_normal_page_is_one_tile():            assert tile_tops(1600) == [0] and tile_tops(2400) == [0]
def test_a_strip_is_cut_into_overlapping_tiles():
    tops = tile_tops(5000)
    assert tops[0] == 0 and tops[1] == 1400
    assert tops[-1] + TILE_HEIGHT >= 5000
    assert all(b - a == TILE_HEIGHT - TILE_OVERLAP for a, b in zip(tops, tops[1:]))

def test_tile_lines_come_back_in_page_coordinates():
    # 800x5000 image; the engine reports a line at y=100 in its second tile
    engine = FakeEngine([[], [line("SECOND TILE", box=Box(50, 100, 200, 30))]])
    [found] = read_lines(image, engine)
    assert found.box == Box(50, 1500, 200, 30)

def test_a_line_seen_in_two_tiles_is_kept_once_with_the_better_reading():
    # same place on the page: y=1500 in tile 0, y=100 in tile 1
    engine = FakeEngine([[line("WHERE ARE YO", 0.7, Box(50, 1500, 200, 30))],
                         [line("WHERE ARE YOU", 0.98, Box(50, 100, 210, 30))]])
    assert [found.text for found in read_lines(image, engine)] == ["WHERE ARE YOU"]

def test_noise_is_filtered_out_of_what_comes_back():
    engine = FakeEngine([[line("HELLO"), line("7"), line("FAINT", 0.3)]])
    assert [found.text for found in read_lines(small_image, engine)] == ["HELLO"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_lines.py -q`
Expected: FAIL, `narrator.lines` not found.

- [ ] **Step 3: Implement `narrator/narrator/lines.py`**

`is_text`: score at least `MIN_SCORE`, and either two or more ASCII letters or nothing but `?`, `!`, `.` and spaces. `tile_tops`: `[0]` when the height is at most `1.5 * TILE_HEIGHT`, otherwise steps of `TILE_HEIGHT - TILE_OVERLAP` until a tile reaches the bottom. `read_lines`: read each tile, shift boxes by the tile's top, treat two lines as the same when their overlap is more than half the smaller box's area and keep the higher score, then filter with `is_text`. A comment on `tile_tops` records why: the engine scales a page to 2,000 px on its long side, which makes a 16,000 px strip unreadable.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lines.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add narrator/narrator/lines.py narrator/tests/conftest.py narrator/tests/test_lines.py
git commit -m "feat(narrator): filter recognised lines and tile tall pages"
```

---

### Task 3: Blocks and clean-up for speech

**Files:**
- Create: `narrator/narrator/blocks.py`, `narrator/tests/test_blocks.py`

**Interfaces:**
- Consumes: `Box`, `TextLine`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Block: box: Box; text: str
  def clean(lines: Sequence[str]) -> str
  def group_lines(lines: Sequence[TextLine]) -> list[Block]
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_capitals_become_sentence_case():
    assert clean(["GOOD MORNING.", "WHERE ARE YOU GOING?"]) == "Good morning. Where are you going?"
def test_a_lone_i_stays_capital():
    assert clean(["I THINK I'M LATE"]) == "I think I'm late"
def test_a_word_split_by_a_hyphen_is_put_back_together():
    assert clean(["EVERY-", "THING IS READY"]) == "Every-thing is ready"
def test_whitespace_is_collapsed():
    assert clean(["  SO   QUIET ", "HERE"]) == "So quiet here"
def test_stray_lower_case_from_the_engine_is_normalised():
    assert clean(["HEy THERE"]) == "Hey there"

def test_stacked_lines_are_one_block_read_top_to_bottom():
    lines = [TextLine(Box(100, 140, 180, 30), "ARE YOU", 0.99),
             TextLine(Box(110, 100, 160, 30), "WHERE", 0.99),
             TextLine(Box(105, 180, 170, 30), "GOING?", 0.99)]
    [block] = group_lines(lines)
    assert block.text == "Where are you going?"
    assert block.box == Box(100, 100, 180, 110)

def test_lines_side_by_side_are_separate_blocks():
    lines = [TextLine(Box(100, 100, 150, 30), "LEFT", 0.99), TextLine(Box(500, 100, 150, 30), "RIGHT", 0.99)]
    assert len(group_lines(lines)) == 2

def test_lines_far_apart_vertically_are_separate_blocks():
    lines = [TextLine(Box(100, 100, 150, 30), "ABOVE", 0.99), TextLine(Box(100, 300, 150, 30), "BELOW", 0.99)]
    assert len(group_lines(lines)) == 2

def test_no_lines_no_blocks():
    assert group_lines([]) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_blocks.py -q` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement `narrator/narrator/blocks.py`**

`group_lines`: union-find over line pairs. Two lines join when the vertical gap between them is under `0.8` of the shorter line's height and their horizontal overlap is more than `0.3` of the narrower line's width (named constants `MAX_GAP_RATIO`, `MIN_OVERLAP_RATIO`). A block's box is the union of its lines; its text is `clean` of the lines sorted by `y`. `clean`: a line ending in `-` joins the next with no space, keeping the hyphen; everything else joins with one space; lower-case the whole, capitalise the first letter and the first letter after `.`, `!` or `?` followed by a space, and capitalise a standalone `i` (also before an apostrophe). A comment on the sentence-case step records why: speech engines spell out short words written in capitals.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_blocks.py -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add narrator/narrator/blocks.py narrator/tests/test_blocks.py
git commit -m "feat(narrator): group lines into blocks and clean them for speech"
```

---

### Task 4: Reading a page into a transcript

**Files:**
- Create: `narrator/narrator/page.py`, `narrator/tests/test_page.py`

**Interfaces:**
- Consumes: `detect_panels`, `reading_order`, `read_lines`, `group_lines`, `LineEngine`, `Block`, `Box`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Panel: box: Box; blocks: tuple[Block, ...]
  @dataclass(frozen=True)
  class Transcript: engine: str; language: str; width: int; height: int; panels: tuple[Panel, ...]
  STRIP_RATIO = 2.5
  def read_page(image: np.ndarray, engine: LineEngine, *, right_to_left: bool) -> Transcript   # image is BGR
  def as_json(transcript: Transcript) -> dict[str, Any]
  ```
  `as_json` shape: `{"engine", "language", "width", "height", "panels": [{"box": [x, y, w, h], "blocks": [{"box": [x, y, w, h], "text": str}]}]}`.

- [ ] **Step 1: Write the failing tests**

The `grid` fixture draws a white 1200x800 page with four bordered panels in a 2x2 grid. `FakeEngine` returns one line inside each panel, texts `"TOP LEFT"`, `"TOP RIGHT"`, `"BOTTOM LEFT"`, `"BOTTOM RIGHT"`.

```python
def texts(t): return [block.text for panel in t.panels for block in panel.blocks]

def test_right_to_left_reads_the_right_panel_first():
    assert texts(read_page(grid, engine, right_to_left=True)) == ["Top right", "Top left", "Bottom right", "Bottom left"]
def test_left_to_right_reads_the_left_panel_first():
    assert texts(read_page(grid, engine, right_to_left=False)) == ["Top left", "Top right", "Bottom left", "Bottom right"]
def test_a_panel_with_no_text_is_returned_empty_not_left_out():
    # engine returns lines for three of the four panels
    t = read_page(grid, engine, right_to_left=False)
    assert len(t.panels) == 4 and sum(1 for p in t.panels if not p.blocks) == 1
def test_a_page_with_no_text_at_all_is_still_a_transcript():
    t = read_page(grid, FakeEngine([[]]), right_to_left=True)
    assert len(t.panels) == 4 and texts(t) == []
def test_a_strip_is_one_panel_read_top_to_bottom_whatever_the_direction():
    # 800x4000 page, engine returns per tile: a line at the top, one in the middle, one near the bottom
    t = read_page(strip, engine, right_to_left=True)
    assert len(t.panels) == 1 and t.panels[0].box == Box(0, 0, 800, 4000)
    assert texts(t) == ["First", "Second", "Third"]
def test_the_transcript_names_its_engine_language_and_size():
    t = read_page(grid, engine, right_to_left=True)
    assert (t.engine, t.language, t.width, t.height) == ("fake", "en", 1200, 800)
def test_json_boxes_are_plain_lists():
    body = as_json(read_page(grid, engine, right_to_left=True))
    assert body["panels"][0]["box"] == [x, y, w, h]          # the top-right panel as drawn
    assert set(body["panels"][0]["blocks"][0]) == {"box", "text"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_page.py -q` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement `narrator/narrator/page.py`**

`read_page`: lines from `read_lines`, blocks from `group_lines`. A page with `height > STRIP_RATIO * width` is one panel covering the page, ordered left to right; otherwise `detect_panels` on the grayscale page, ordered with `reading_order` in the requested direction. Ordering tolerance is one per cent of the page's short side. A block belongs to the panel it overlaps most, or the nearest panel centre when it overlaps none. Blocks inside a panel are ordered with the same `reading_order` and direction.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add narrator/narrator/page.py narrator/tests/test_page.py
git commit -m "feat(narrator): read a page into ordered panels and blocks"
```

---

### Task 5: The engine, the HTTP surface and the image

**Files:**
- Create: `narrator/narrator/engine.py`, `narrator/narrator/main.py`, `narrator/Dockerfile`, `narrator/.dockerignore`, `narrator/tests/test_api.py`, `narrator/tests/test_engine.py`

**Interfaces:**
- Consumes: `read_page`, `as_json`, `LineEngine`, `TextLine`.
- Produces: `narrator.engine.RapidOcrEngine` (a `LineEngine`, `language = "en"`, `name = "rapidocr <installed version> / PP-OCRv6 small"`); `narrator.main.create_app(engine: LineEngine | None = None) -> FastAPI`, module-level `app = create_app()`; `MAX_BODY_BYTES = 40 * 1024 * 1024`.
- HTTP: `POST /v1/pages?direction=rtl|ltr` (body: image bytes; `direction` required) answering `as_json`; `GET /healthz` answering `{"ok": true}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_api.py`, using `fastapi.testclient.TestClient(create_app(FakeEngine(...)))` and a PNG encoded from the `grid` page

```python
def test_a_page_comes_back_as_a_transcript():
    response = client.post("/v1/pages?direction=rtl", content=png)
    assert response.status_code == 200
    assert response.json()["panels"][0]["blocks"][0]["text"] == "Top right"
def test_direction_is_required_and_checked():
    assert client.post("/v1/pages", content=png).status_code == 422
    assert client.post("/v1/pages?direction=up", content=png).status_code == 422
def test_bytes_that_are_not_an_image_are_422():
    response = client.post("/v1/pages?direction=ltr", content=b"not an image")
    assert response.status_code == 422 and "image" in response.json()["detail"]
def test_an_empty_body_is_422():
    assert client.post("/v1/pages?direction=ltr", content=b"").status_code == 422
def test_a_body_over_the_limit_is_413(monkeypatch):
    monkeypatch.setattr("narrator.main.MAX_BODY_BYTES", 10)
    assert client.post("/v1/pages?direction=ltr", content=png).status_code == 413
def test_health():
    assert client.get("/healthz").json() == {"ok": True}
```

and `tests/test_engine.py`, which runs the real model (its files ship inside the wheel, so no network):

```python
def test_the_real_engine_reads_lettering_the_test_drew():
    # white 900x600 page; cv2.putText "GOOD MORNING" and "WHERE ARE YOU" in black,
    # FONT_HERSHEY_SIMPLEX scale 1.5 thickness 3, well apart
    found = " ".join(line.text.upper() for line in RapidOcrEngine().read(page))
    assert "GOOD MORNING" in found and "WHERE ARE YOU" in found
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py tests/test_engine.py -q` — Expected: FAIL, modules not found.

- [ ] **Step 3: Implement `engine.py`**

`RapidOcrEngine.__init__` imports `rapidocr` inside the method (so the geometry tests never load ONNX Runtime) and builds `RapidOCR(params={"Global.log_level": "error"})`. `read` calls the engine on the image; its result has `txts`, `scores` and `boxes` (four corner points per line), all `None` when nothing was found; each box becomes the `Box` bounding its points.

- [ ] **Step 4: Implement `main.py`**

The engine is built once, on first use, when `create_app` was given none. The body is refused with 413 when `Content-Length` or the bytes read exceed `MAX_BODY_BYTES`, checked before decoding. Decode with `cv2.imdecode(..., cv2.IMREAD_COLOR)`; `None` or an empty body is 422 with detail `"the body is not an image that decodes"`. Recognition runs in `asyncio.to_thread` under one `asyncio.Lock`, with a comment saying why: it is CPU-bound and two pages at once only make both slower.

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check .` — Expected: PASS, clean.

- [ ] **Step 6: Write `narrator/Dockerfile` and `.dockerignore`**

`python:3.12-slim`; install the project with `pip install --no-cache-dir .`; create and switch to a non-root user; `EXPOSE 8000`; `CMD ["uvicorn", "narrator.main:app", "--host", "0.0.0.0", "--port", "8000"]`. `.dockerignore`: `.venv`, `tests`, caches.

- [ ] **Step 7: Verify the image answers**

```bash
docker build -t soshuhen-narrator:local narrator
docker run -d --rm --name narrator-check --network none soshuhen-narrator:local
docker exec narrator-check python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/healthz').read())"
docker exec narrator-check python -c "import cv2, numpy, urllib.request as u; p=numpy.full((600,900,3),255,numpy.uint8); cv2.putText(p,'GOOD MORNING',(60,300),cv2.FONT_HERSHEY_SIMPLEX,1.5,(0,0,0),3); print(u.urlopen(u.Request('http://localhost:8000/v1/pages?direction=ltr', data=cv2.imencode('.png',p)[1].tobytes())).read())"
docker stop narrator-check
```

Expected: `b'{"ok":true}'`, then a transcript whose text is `Good morning`. `--network none` is the proof that nothing is downloaded at run time. If the import of `cv2` fails on a missing shared library, add that one library with `apt-get install --no-install-recommends` in the Dockerfile and say which in a comment.

- [ ] **Step 8: Commit**

```bash
git add narrator/narrator/engine.py narrator/narrator/main.py narrator/Dockerfile narrator/.dockerignore narrator/tests/test_api.py narrator/tests/test_engine.py
git commit -m "feat(narrator): serve transcripts over HTTP with RapidOCR"
```

---

### Task 6: The api's narrator client

**Files:**
- Create: `backend/app/reader/narration.py`, `backend/tests/test_narration_client.py`
- Modify: `backend/app/config.py` (add the setting after `flaresolverr_url`)

**Interfaces:**
- Produces:
  ```python
  # backend/app/config.py
  narrator_url: str = ""          # env NARRATOR_URL; empty means narration is off

  # backend/app/reader/narration.py
  Direction = Literal["rtl", "ltr"]
  TIMEOUT = httpx.Timeout(60.0, connect=5.0)
  class NarratorFailed(RuntimeError): ...
  async def transcribe(client: httpx.AsyncClient, base_url: str, data: bytes, direction: Direction) -> dict[str, Any]
  ```

- [ ] **Step 1: Write the failing tests**, each with `httpx.MockTransport` as `tests/test_komga_client.py` does

```python
TRANSCRIPT = {"engine": "fake", "language": "en", "width": 10, "height": 20,
              "panels": [{"box": [0, 0, 10, 20], "blocks": [{"box": [1, 1, 5, 5], "text": "Hello."}]}]}

async def test_the_page_is_posted_and_the_transcript_returned():
    # handler records the request and answers 200 TRANSCRIPT
    assert await transcribe(http, "http://narrator:8000/", b"IMG", "rtl") == TRANSCRIPT
    assert (seen.method, seen.url.path, seen.url.params["direction"], seen.content) == ("POST", "/v1/pages", "rtl", b"IMG")
async def test_an_error_answer_is_a_failure_that_carries_the_detail():
    # handler answers 422 {"detail": "the body is not an image that decodes"}
    with pytest.raises(NarratorFailed, match="not an image"): ...
async def test_an_unreachable_narrator_is_a_failure():
    # handler raises httpx.ConnectError
    with pytest.raises(NarratorFailed): ...
async def test_a_timeout_is_a_failure():
    # handler raises httpx.ReadTimeout
    with pytest.raises(NarratorFailed): ...
async def test_an_answer_that_is_not_a_transcript_is_a_failure():
    # handler answers 200 {"unexpected": true}, then 200 with a non-JSON body
    with pytest.raises(NarratorFailed): ...
```

- [ ] **Step 2: Run to verify they fail**

Run from `backend/`: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_narration_client.py -q` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement `narration.py` and add the setting**

Pure like the rest of `reader/`: arguments in, a value out, no database, no settings lookup. Every `httpx.HTTPError`, a non-2xx status, a body that is not JSON, and a body without a `panels` list raise `NarratorFailed`. The setting's comment records that the service sits behind the `narrator` compose profile and that empty hides the feature.

- [ ] **Step 4: Run to verify they pass**, then `.venv/bin/python -m ruff check app/ tests/`

- [ ] **Step 5: Commit**

```bash
git add backend/app/reader/narration.py backend/app/config.py backend/tests/test_narration_client.py
git commit -m "feat(reader): add a client for the narrator service"
```

---

### Task 7: Transcript and availability routes

**Files:**
- Modify: `backend/app/api/reader_service.py`, `backend/app/api/routes_reader.py`
- Test: `backend/tests/test_reader_api.py` (append; it already has the `client` and `clean` fixtures and the `_series`, `_chapter`, `_cbz` helpers)

**Interfaces:**
- Consumes: `narration.transcribe`, `narration.NarratorFailed`, `narration.TIMEOUT`, `Settings.narrator_url`, the existing `serve_page`.
- Produces:
  ```python
  # reader_service.py
  class NarrationOff(RuntimeError): ...
  class NarrationFailed(RuntimeError): ...
  def narration_available() -> bool
  def narrator_client() -> httpx.AsyncClient          # tests replace this
  async def transcript(session, row: ChapterRow, index: int, direction: narration.Direction) -> dict[str, Any]
  ```
  ```
  GET /api/reader/narration                                         -> {"available": bool}
  GET /api/reader/chapters/{chapter_id}/pages/{index}/transcript?direction=rtl|ltr   (default ltr)
      200 the narrator's JSON, Cache-Control: private, max-age=86400
      503 "narration is not set up on this installation"
      502 "the narrator could not read this page: <reason>"
      everything serve_page raises keeps its status (404, 409, 410, 502)
  ```

- [ ] **Step 1: Write the failing tests**

A helper `_narrator(monkeypatch, handler)` sets `NARRATOR_URL=http://narrator:8000`, clears `get_settings`' cache, and replaces `reader_service.narrator_client` with one returning `httpx.AsyncClient(transport=httpx.MockTransport(handler))`. `TRANSCRIPT` as in Task 6.

```python
async def test_narration_is_unavailable_until_configured(client, monkeypatch):
    assert (await client.get("/api/reader/narration")).json() == {"available": False}
    _narrator(monkeypatch, lambda request: httpx.Response(200, json=TRANSCRIPT))
    assert (await client.get("/api/reader/narration")).json() == {"available": True}

async def test_a_transcript_is_read_from_the_archived_page(client, tmp_path, monkeypatch):
    # archived chapter with two pages whose bytes differ; handler records request.content
    response = await client.get(f"/api/reader/chapters/{cid}/pages/1/transcript?direction=rtl")
    assert response.status_code == 200 and response.json() == TRANSCRIPT
    assert sent == second_page_bytes and direction_seen == "rtl"
    assert response.headers["cache-control"] == "private, max-age=86400"

async def test_a_transcript_of_a_streamed_page_fetches_and_caches_it_as_showing_it_does(client, monkeypatch):
    # a mapped chapter with no file, set up as test_a_streamed_page_is_fetched_once_then_served_from_the_cache does
    assert (await client.get(f"/api/reader/chapters/{cid}/pages/0/transcript")).status_code == 200
    assert await _state(cid) == "streaming"
    # the page itself is then served without asking the source again

async def test_a_transcript_without_a_narrator_is_503(client, tmp_path): ...
async def test_a_narrator_that_fails_is_502_and_says_so(client, tmp_path, monkeypatch):
    # handler raises httpx.ConnectError
    assert response.status_code == 502 and "narrator" in response.json()["detail"]
async def test_a_page_the_narrator_cannot_decode_is_502(client, tmp_path, monkeypatch):
    # handler answers 422 {"detail": "the body is not an image that decodes"}
    assert response.status_code == 502 and "not an image" in response.json()["detail"]
async def test_a_transcript_past_the_last_page_is_404(client, tmp_path, monkeypatch): ...
async def test_a_transcript_of_a_prose_chapter_is_409(client, monkeypatch): ...
async def test_an_unknown_direction_is_422(client, tmp_path, monkeypatch): ...
async def test_the_manifest_does_not_change_when_narration_is_on(client, tmp_path, monkeypatch):
    before = (await client.get(f"/api/reader/chapters/{cid}")).json()
    _narrator(monkeypatch, ...)
    assert (await client.get(f"/api/reader/chapters/{cid}")).json() == before
```

- [ ] **Step 2: Run to verify they fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests/test_reader_api.py -q` — Expected: the new tests FAIL with 404 on the new paths.

- [ ] **Step 3: Implement**

`transcript`: raise `NarrationOff` when the URL is empty, before touching the page; get the bytes with `serve_page` (so a streamed page is fetched, cached and counted exactly as when it is shown); call `narration.transcribe` inside `async with narrator_client()`; turn `NarratorFailed` into `NarrationFailed`. In `routes_reader.py`, `service_errors` maps `NarrationOff` to 503 and `NarrationFailed` to 502 with the details above; the transcript route commits the session as the page route does, and its comment says why the header is not `immutable`: a later engine reads the same page differently.

- [ ] **Step 4: Run the whole backend suite and lint**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests -q && .venv/bin/python -m ruff check app/ tests/` — Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/reader_service.py backend/app/api/routes_reader.py backend/tests/test_reader_api.py
git commit -m "feat(reader): serve page transcripts from the narrator"
```

---

### Task 8: Compose, CI and documentation

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`, `docs/features.md`, `docs/configuration.md`, `docs/architecture.md`, `CLAUDE.md`

- [ ] **Step 1: Compose**

A `narrator` service: `build: ./narrator`, `profiles: ["narrator"]`, `restart: unless-stopped`, `expose: ["8000"]`, `read_only: true` with a `tmpfs` for `/tmp`, `logging: *logging`, no volumes, no `ports`, and a comment in the style of the `flaresolverr` one saying what it is and how to start it. Add `NARRATOR_URL: ${NARRATOR_URL:-}` to the `api` environment only (the workers never ask).

- [ ] **Step 2: `.env.example`**

A commented block after `FLARESOLVERR_URL`: what it does, that it is optional and empty by default, `docker compose --profile narrator up -d --build`, and the value `http://narrator:8000`. The variable itself is left empty.

- [ ] **Step 3: CI**

A `narrator` job after `frontend`: `working-directory: narrator`, `astral-sh/setup-uv@v5`, `uv venv && uv pip install -e ".[dev]"`, `.venv/bin/ruff check .`, `.venv/bin/pytest -q`.

- [ ] **Step 4: Documentation**

`docs/features.md`: reading a chapter aloud, what a listener hears, and the limits listed in the spec's "What was seen that is not solved". `docs/configuration.md`: `NARRATOR_URL` and the profile. `docs/architecture.md`: the narrator as a pure edge the api calls, why it is a separate image, and that nothing is stored. `CLAUDE.md`: the rebuild section gains `docker compose build narrator && docker compose --profile narrator up -d --force-recreate narrator`.

- [ ] **Step 5: Verify**

Run: `docker compose config --quiet && docker compose --profile narrator config --services | grep -x narrator`
Expected: no output from the first, `narrator` from the second.

- [ ] **Step 6: Commit** (two commits)

```bash
git add docker-compose.yml .env.example .github/workflows/ci.yml
git commit -m "feat(narrator): add the optional compose service and its CI job"
git add docs/features.md docs/configuration.md docs/architecture.md CLAUDE.md
git commit -m "docs: describe reading a chapter aloud"
```

---

### Task 9: Share the read-aloud player between readers

A move with no change in behaviour.

**Files:**
- Move: `frontend/src/features/prose-reader/readAloud.ts` to `frontend/src/lib/readAloud.ts`; `readAloud.test.ts` to `frontend/src/lib/readAloud.test.ts`; `webSpeech.ts` to `frontend/src/lib/webSpeech.ts`; `ReadAloudBar.tsx` to `frontend/src/ui/ReadAloudBar.tsx`
- Create: `frontend/src/lib/readAloudSettings.ts`
- Modify: `frontend/src/ui/index.ts`, `frontend/src/features/prose-reader/useReadAloud.ts`, `frontend/src/features/prose-reader/ProseReaderPage.tsx`

**Interfaces:**
- Produces: everything `readAloud.ts` exported, now from `lib/readAloud`; `webSpeechEngine` from `lib/webSpeech`; `ReadAloudBar` from `ui`, with one new required prop `unit: string` used as `Previous ${unit}` and `Next ${unit}`; and
  ```ts
  // lib/readAloudSettings.ts — the two functions and KEY/DEFAULT moved out of useReadAloud.ts unchanged
  export function loadSpeechSettings(): SpeechSettings
  export function saveSpeechSettings(settings: SpeechSettings): void
  ```
  The storage key stays `reader:read-aloud`.

- [ ] **Step 1: Move with `git mv`, fix imports, add the prop**

The prose reader passes `unit="paragraph"`, so its labels read exactly as before.

- [ ] **Step 2: Verify nothing changed**

Run from `frontend/`: `npm test && npm run build && grep -rn "features/prose-reader" src/lib src/ui`
Expected: tests pass, build passes, grep finds nothing. Then `grep -c "max-w-prose-column" dist/assets/*.css` is at least 1.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/readAloud.ts frontend/src/lib/readAloud.test.ts frontend/src/lib/webSpeech.ts frontend/src/lib/readAloudSettings.ts frontend/src/ui/ReadAloudBar.tsx frontend/src/ui/index.ts frontend/src/features/prose-reader
git commit -m "refactor(read-aloud): move the player where both readers can use it"
```

---

### Task 10: The player says when it ran out of text

**Files:**
- Modify: `frontend/src/lib/readAloud.ts`
- Test: `frontend/src/lib/readAloud.test.ts`

**Interfaces:**
- Produces: `PlayerEvents` gains optional `finished?(): void`, called once, after the state has become `stopped`, only when the last utterance of the last block finished speaking.

- [ ] **Step 1: Write the failing tests**, with the file's existing `fakeEngine`

```ts
test('running out of text is reported once, after stopping', () => {
  // two one-piece blocks; finish both utterances
  assert.deepEqual(order, ['playing', 'stopped', 'finished'])
})
test('stopping by hand is not running out', () => { /* start, stop() */ assert.equal(finished, 0) })
test('an utterance the engine gave up on is not running out', () => { /* done(false) */ assert.equal(finished, 0) })
test('skipping past the end is not running out', () => { /* skip(+5) */ assert.equal(finished, 0) })
test('a player started again from finished speaks the new text', () => {
  // finished() calls start() with another block; the engine is asked for it
})
```

- [ ] **Step 2: Run to verify they fail** — `npm test` — Expected: the first and last FAIL.

- [ ] **Step 3: Implement** in `advance()`: when the blocks run out, `stop()` then `this.events.finished?.()`.

- [ ] **Step 4: Run to verify they pass** — `npm test && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/readAloud.ts frontend/src/lib/readAloud.test.ts
git commit -m "feat(read-aloud): report when the text ran out"
```

---

### Task 11: Transcript calls and the narration script

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/features/reader/lib/narrationScript.ts`, `frontend/src/features/reader/lib/narrationScript.test.ts`

**Interfaces:**
- Produces:
  ```ts
  // lib/api.ts
  export type NarrationDirection = 'rtl' | 'ltr'
  export interface TranscriptBlock { box: number[]; text: string }
  export interface TranscriptPanel { box: number[]; blocks: TranscriptBlock[] }
  export interface PageTranscript { engine: string; language: string; width: number; height: number; panels: TranscriptPanel[] }
  api.readerNarration(): Promise<{ available: boolean }>
  api.readerTranscript(chapterId: number, index: number, direction: NarrationDirection): Promise<PageTranscript>

  // features/reader/lib/narrationScript.ts — no imports except types
  export interface ScriptItem { text: string; page: number; panel: number | null; block: number | null }
  export const UNREADABLE = 'This page could not be read aloud.'
  export const CHAPTER_END = 'End of chapter.'
  export function narrationDirection(mode: ReaderMode): NarrationDirection
  export function pageScript(page: number, transcript: PageTranscript): ScriptItem[]
  export function failureScript(page: number): ScriptItem[]
  ```
  `page` is the zero-based page index; it is spoken as `page + 1`.

- [ ] **Step 1: Write the failing tests**

```ts
const block = (text: string) => ({ box: [0, 0, 1, 1], text })
const transcript = (...panels: string[][]) =>
  ({ engine: 'fake', language: 'en', width: 1, height: 1, panels: panels.map((b) => ({ box: [0, 0, 1, 1], blocks: b.map(block) })) })
const said = (items: ScriptItem[]) => items.map((item) => item.text)

test('a page is its number, then each panel and its blocks', () => {
  assert.deepEqual(said(pageScript(4, transcript(['Good morning.', 'Where are you going?'], ['Wait!']))),
    ['Page 5.', 'Panel 1.', 'Good morning.', 'Where are you going?', 'Panel 2.', 'Wait!'])
})
test('a wordless panel is announced as such', () => {
  assert.deepEqual(said(pageScript(0, transcript(['Hello.'], []))), ['Page 1.', 'Panel 1.', 'Hello.', 'Panel 2.', 'No text.'])
})
test('a single panel is not announced', () => {
  assert.deepEqual(said(pageScript(2, transcript(['First.', 'Second.']))), ['Page 3.', 'First.', 'Second.'])
})
test('a page with no text still says its number', () => {
  assert.deepEqual(said(pageScript(0, transcript([]))), ['Page 1.', 'No text.'])
  assert.deepEqual(said(pageScript(0, transcript())), ['Page 1.', 'No text.'])
})
test('each item knows what on the page it is', () => {
  const items = pageScript(4, transcript(['A.'], ['B.']))
  assert.deepEqual(items.map(({ page, panel, block }) => [page, panel, block]),
    [[4, null, null], [4, 0, null], [4, 0, 0], [4, 1, null], [4, 1, 0]])
})
test('a page that could not be read says so, after its number', () => {
  assert.deepEqual(said(failureScript(6)), ['Page 7.', UNREADABLE])
})
test('only the right-to-left paged mode reads right to left', () => {
  assert.equal(narrationDirection('paged_rtl'), 'rtl')
  for (const mode of ['paged_ltr', 'double', 'long_strip'] as const) assert.equal(narrationDirection(mode), 'ltr')
})
```

The single-panel rule is a deliberate step past the spec, which accepted "Panel 1" for a whole page: every page of a long strip is one panel, and hearing it announced on each is noise.

- [ ] **Step 2: Run to verify they fail** — `npm test` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement both files.** In `api.ts` the transcript address is `/api/reader/chapters/${chapterId}/pages/${index}/transcript?direction=${direction}`.

- [ ] **Step 4: Run to verify they pass** — `npm test && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/features/reader/lib/narrationScript.ts frontend/src/features/reader/lib/narrationScript.test.ts
git commit -m "feat(reader): turn a page transcript into what is said"
```

---

### Task 12: Narration in the reader screen

**Files:**
- Create: `frontend/src/features/reader/lib/useNarration.ts`, `frontend/src/features/reader/TranscriptPanel.tsx`
- Modify: `frontend/src/features/reader/ReaderPage.tsx`, `DesktopChrome.tsx`, `TabletChrome.tsx`, `lib/useReaderKeys.ts`, `frontend/src/ui/Icon.tsx` (only if no existing icon suits the transcript button)

**Interfaces:**
- Consumes: `ReadAloudPlayer`, `utterances`, `webSpeechEngine`, `loadSpeechSettings`, `saveSpeechSettings`, `ReadAloudBar`, `api.readerNarration`, `api.readerTranscript`, `pageScript`, `failureScript`, `narrationDirection`, `CHAPTER_END`, `ScriptItem`.
- Produces:
  ```ts
  export function useNarration(options: {
    chapterId: number
    pages: number[]                       // the pages on screen, in page order
    direction: NarrationDirection
    available: boolean
    initiallyOn: boolean
    onChange: (on: boolean) => void
    onPagesDone: () => 'continue' | 'end' // turn the page; say whether the chapter ended
  }): {
    supported: boolean                    // available and the browser can speak
    on: boolean
    state: PlayState
    voices: SpeechVoice[]
    settings: SpeechSettings
    transcripts: Map<number, PageTranscript>
    failed: number | null                 // the page that could not be read, if any
    place: ScriptItem | null              // what is being spoken
    toggle: () => void                    // on and off: the chrome button and the n key
    playPause: () => void                 // the bar's middle button
    skip: (delta: number) => void
    configure: (next: SpeechSettings) => void
  }
  ```
  `Panel` in `ReaderPage.tsx` becomes `'settings' | 'chapters' | 'transcript' | null`. `ReaderKeyActions` gains `narrate: () => void` on the `n` key.

- [ ] **Step 1: Implement `useNarration`**

Behaviour the hook must have, each of which a later step checks in the browser:

- Turning on, or `pages` changing while on, cancels speech, fetches the transcript of every page on screen, joins their scripts in page order, and starts the player from the first item. Transcripts are kept in a `Map` for the life of the chapter and never fetched twice.
- Every fetch carries a turn number. A transcript that arrives after `pages` changed or narration was turned off is stored and not spoken.
- A fetch that fails speaks `failureScript` for that page and sets `failed`. When that script finishes, `onPagesDone` is **not** called: narration stays on the page.
- When a script that did not fail finishes, `onPagesDone()` is called. On `'end'` the hook speaks `CHAPTER_END` and turns itself off. On `'continue'` it waits for `pages` to change.
- While a page is being spoken, the transcript of the page after the last one on screen is requested and stored.
- `playPause` pauses and resumes the player without turning narration off. `toggle` off stops the player. Unmounting stops it.
- `onChange` is called whenever `on` changes. With `initiallyOn`, narration starts when the hook mounts.

- [ ] **Step 2: Wire `ReaderPage`**

- `ReaderRoute` keeps a ref of whether narration is on and passes it down as `initiallyOn` and `onChange`, with a comment: the reader is remounted per chapter, and a listener who opens the next chapter should not have to start narration again.
- Availability comes from `api.readerNarration()` through `useAsyncData`; a failure of that call means unavailable.
- Paged modes: `pages` is `groups[step]`, and `onPagesDone` calls `forward()` and answers `'end'` when `step` was the last group, else `'continue'`. At the end screen (`atEnd`) `pages` is empty and nothing is fetched.
- Long strip: narration keeps a cursor in state, set to `page` when narration is turned on. `pages` is `[cursor]`. `onPagesDone` moves the cursor on and calls `seek(cursor + 1)`, or at the last page calls `finish()` and answers `'end'`.
- The `ReadAloudBar` from `ui` is rendered while narration is on, with `unit="line"`, `onToggle={playPause}`, and `onClose={toggle}`. It must not cover the page slider or the tablet footer; on the desktop the slider is not rendered while the bar is.

- [ ] **Step 3: Chrome, keys and the transcript panel**

- `DesktopChrome` and `TabletChrome` take `narration: { supported: boolean; on: boolean; onToggle: () => void } `. When supported they show a Read aloud button (icon `headphones`, label `Read aloud (n)` on the desktop, `aria-pressed`) and a Page transcript button that opens the `'transcript'` panel. Neither is rendered when unsupported.
- `TranscriptPanel` is a `ReaderSheet` titled "Page transcript". For each page on screen: a heading "Page N"; for each panel a heading "Panel K" (left out when the page has one panel) and an ordered list of its blocks, "No text" for an empty panel. The block being spoken carries `aria-current="true"` and a token-based highlight. A page in `failed` shows `UNREADABLE`; a page not fetched yet says narration has not reached it. No `aria-live` anywhere in it, with a comment saying why: a screen reader would talk over the narration.

- [ ] **Step 4: Build and check the classes**

Run: `npm test && npm run build`, then `grep` `dist/assets/*.css` for every class this task introduced.
Expected: each one is found.

- [ ] **Step 5: Check it in a browser with drawn pages**

None of this touches the running stack. Start the narrator image with `-p 8001:8000`. Start the backend from `backend/` with `uvicorn app.api.main:app --port 8000` and the environment `POSTGRES_HOST=localhost POSTGRES_PORT=5434 LIBRARY_PATH=<a scratch folder> READER_CACHE_PATH=<another> NARRATOR_URL=http://localhost:8001`, after `alembic upgrade head` against that database. Put two CBZ files of pages drawn with `cv2.putText` in the scratch library (one of 1100x1600 pages with bordered panels, one of 800x4000 strips, each with one page left blank) and insert a `series` and two `chapter` rows pointing at them, as `_series` and `_chapter` in `backend/tests/test_reader_api.py` do. Run `npm run dev` in `frontend/`, which proxies `/api` to port 8000, and open `/read/<chapter id>`. Check, and note each result:

1. With `NARRATOR_URL` unset: no Read aloud button, no transcript button, `n` does nothing.
2. Paged right-to-left: `n` starts narration, the right panel is read before the left, the page turns by itself, the last page shows the end screen and "End of chapter." is said once. `chapter complete` was posted once (network tab).
3. Double page: both pages of a spread are read before it turns.
4. Long strip: pages are read top to bottom and scrolled into view; the end is announced once.
5. A page with no lettering: its number and "No text." are said and the page turns. (Review Focus 1)
6. Stop the narrator container mid-chapter: the next page says "This page could not be read aloud." once and narration stays there; arrow keys still turn pages. (Review Focus 3)
7. Hold the arrow key through six pages while narration is on: only the page that ends up on screen is spoken. (Review Focus 4)
8. The bar pauses, resumes, skips a line back and forward, and a speed chosen here is the one the prose reader starts with.
9. The transcript panel shows the page's text and marks the block being spoken.
10. The prose reader's read-aloud still works and its labels still say "paragraph".

- [ ] **Step 6: Commit** (three commits)

```bash
git add frontend/src/features/reader/lib/useNarration.ts frontend/src/features/reader/lib/useReaderKeys.ts frontend/src/features/reader/ReaderPage.tsx
git commit -m "feat(reader): narrate the page on screen and turn it"
git add frontend/src/features/reader/DesktopChrome.tsx frontend/src/features/reader/TabletChrome.tsx
git commit -m "feat(reader): add the read aloud control"
git add frontend/src/features/reader/TranscriptPanel.tsx frontend/src/ui/Icon.tsx
git commit -m "feat(reader): show the transcript of the page"
```

If `ReaderPage.tsx` cannot build without the chrome and panel changes, commit them together and say so in the message body.

---

### Task 13: Try it on a real work

This task changes the user's running stack. **Do not start it without their go-ahead in the conversation.**

- [ ] **Step 1: Ask.** State exactly what will be rebuilt and recreated (`api`, `web`, and the new `narrator`, from this branch), that the database is untouched because there is no migration, and that going back is rebuilding `api` and `web` from `main` and removing `NARRATOR_URL`.

- [ ] **Step 2: Bring it up**, from the checkout the stack runs from, on this branch: set `NARRATOR_URL=http://narrator:8000` in `.env`, then

```bash
docker compose build api web narrator
docker compose --profile narrator up -d --force-recreate api worker worker-download web narrator
docker compose --profile narrator ps
```

Expected: every service the stack had before is still up, plus `narrator`. Read the `ps` output, not the `up` output.

- [ ] **Step 3: Read a real chapter aloud.** One downloaded right-to-left manga chapter, one long-strip chapter, one chapter that is streamed rather than downloaded. For each: narration starts, the order makes sense to a listener, pages turn, the end is announced, and list progress moved as reading would have moved it. Note what was misread; the spec's list of unsolved problems says which are expected.

- [ ] **Step 4: Report** what was heard, with timings from `docker compose logs narrator`, and anything outside the expected limits.
