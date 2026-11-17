# Accessible manga reader: proof of concept

Reads one manga page aloud for a listener who cannot see it. An image goes in; a transcript in
reading order and one audio file come out.

It is a proof of concept and lives apart from Soshuhen's backend on purpose: nothing in `backend/`
imports it, it has its own dependencies, and CI does not run it. The OCR stage alone installs
about a gigabyte.

## Install

Python 3.12 (the version it was run on; the pinned NumPy does not install on much older ones), and `ffmpeg` on `PATH` (it joins the spoken clips and writes the MP3):

```bash
brew install ffmpeg            # Debian/Ubuntu: sudo apt install ffmpeg
```

Then, from this folder:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

The first run downloads the manga-ocr model, about 400 MB, from Hugging Face into
`~/.cache/huggingface`. Later runs load it from there.

## Run

There is no manga page in the repository, since a real one is somebody's copyrighted work. Draw
the sample, or use a page of your own:

```bash
.venv/bin/python tools/make_sample_page.py
```

```bash
.venv/bin/python -m manga_narrator pagina_exemplo.jpg -o out/narracao.mp3 --overlay out/overlay.png
```

```text
Panel 1
  おはよう！
  今日はいい天気だね
Panel 2
  どこへ行くの？
Panel 3
  学校だよ。
  急がないと遅れる！
Panel 4
  (no text)
Panel 5
  待って！
Overlay written to out/overlay.png
Narration written to out/narracao.mp3 (26.1 s)
```

| Flag | What it does |
| --- | --- |
| `-o`, `--output` | Audio file to write. The extension picks the format: `.mp3` or `.wav`. Default `narration.mp3`. |
| `--tts gtts` | Default. Google Translate's voices. Needs the network, and **sends the page's text to Google**. |
| `--tts pyttsx3` | Offline, with the operating system's voices. Fails by name if no installed voice speaks the language. |
| `--cue-language en\|pt\|ja` | Language of the narrator's announcements ("Panel 2", "Painel 2"). Default `en`. |
| `--left-to-right` | Read rows left to right, for pages not laid out in the Japanese order. |
| `--overlay FILE` | Also write the page with the detected panels and bubbles numbered in reading order. |
| `--no-audio` | Print the transcript and stop before speech. Needs no ffmpeg and sends nothing to a speech service. |

## How it works

```
page image
   │
   ├─ panels.detect_panels ──── where the panels are            (OpenCV contours)
   ├─ panels.reading_order ──── which order to read them in     (recursive XY-cut)
   ├─ bubbles.detect_text_regions ── where the text is          (OpenCV contours)
   ├─ ocr.MangaOcrEngine ────── what each bubble says           (manga-ocr)
   ├─ narration.build_script ── what is said, in which voice, with which pauses
   └─ tts.render ────────────── one audio file                  (gTTS or pyttsx3, joined by ffmpeg)
```

**OCR.** manga-ocr recognises the text in a crop; it does not find text on a page. `bubbles.py`
is the detector it needs: a speech bubble is a bright, roughly convex blob with ink in it. Each
crop reaches the model with everything outside the bubble painted white.

**Reading order.** `reading_order` is a recursive XY-cut. A gutter that crosses the whole group
splits it into bands read top to bottom; where none does, a vertical gutter splits it into columns
read from the right. The recursion is what orders a tall panel beside two stacked ones, which a
sort on coordinates cannot. The same function orders the bubbles inside a panel.

**Speech.** A narrator voice announces each panel and the dialogue voice reads its lines, so a
listener can tell what is on the page from what the reader added. The pause between panels
(1.2 s) is longer than the pause between lines (0.5 s). A wordless panel is announced as such
rather than skipped. With `--cue-language pt` the two voices also differ in language: Portuguese
structure, Japanese dialogue.

The three parts likely to be replaced each sit behind a small seam: `OcrEngine` and `TtsBackend`
are protocols, and panel detection is a function separate from the ordering that consumes it.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m pytest -q
```

The suite draws its own page and uses a stand-in OCR engine, so it loads no model and touches no
network. The audio tests are skipped where ffmpeg is missing.

## What this does not do

- **It reads Japanese only.** That is manga-ocr's limit, not a setting. A page lettered in English
  or Portuguese comes back as confident nonsense. Another language needs another `OcrEngine`.
- **It does not translate.** Japanese text is spoken in Japanese.
- **It has been run on the drawn sample page, not on scanned manga.** The detectors are contour
  heuristics and will miss on real pages: borderless panels, art that crosses the gutter, text
  laid over artwork or screentone, bubbles joined to each other. A trained detector such as
  comic-text-detector is the replacement for `bubbles.py`.
- **It does not describe the artwork.** A listener hears the dialogue and where the panels fall,
  not what is drawn in them.
- **It does not say who is speaking.** Every line is in the same dialogue voice.
- **One page at a time**, with no link to the Soshuhen library or reader.
