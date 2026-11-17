"""Command line: `python -m manga_narrator pagina_exemplo.jpg -o narracao.mp3`."""

import argparse
import sys
from pathlib import Path

import cv2

from manga_narrator.narration import CUES, build_script
from manga_narrator.ocr import MangaOcrEngine
from manga_narrator.pipeline import PageError, ReadPanel, draw_overlay, load_page, read_page
from manga_narrator.tts import (
    GttsBackend,
    Pyttsx3Backend,
    TtsBackend,
    TtsError,
    render,
    require_ffmpeg,
)

BACKENDS: dict[str, type[GttsBackend] | type[Pyttsx3Backend]] = {
    "gtts": GttsBackend,
    "pyttsx3": Pyttsx3Backend,
}


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="manga_narrator",
        description="Read a manga page aloud: OCR the bubbles, order the panels, speak the result.",
    )
    parser.add_argument("image", type=Path, help="the page to read (jpg, png, webp)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("narration.mp3"),
        help="audio file to write; the extension picks the format (default: narration.mp3)",
    )
    parser.add_argument(
        "--tts",
        choices=sorted(BACKENDS),
        default="gtts",
        help="gtts: online, sends the text to Google. pyttsx3: offline, system voices "
        "(default: gtts)",
    )
    parser.add_argument(
        "--cue-language",
        choices=sorted(CUES),
        default="en",
        help="language of the narrator's panel announcements (default: en)",
    )
    parser.add_argument(
        "--left-to-right",
        action="store_true",
        help="read rows left to right, for pages not laid out in the Japanese order",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        help="also write the page with detected panels and bubbles numbered in reading order",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="print the transcript and stop before speech synthesis",
    )
    return parser.parse_args(argv)


def print_transcript(panels: list[ReadPanel]) -> None:
    for number, panel in enumerate(panels, start=1):
        print(f"Panel {number}")
        for line in panel.lines:
            print(f"  {line.text}")
        if not panel.lines:
            print("  (no text)")


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        # Both checked before the model loads: a bad path or a missing ffmpeg should not cost the
        # ten seconds it takes to find out after OCR.
        page = load_page(arguments.image)
        ffmpeg = None if arguments.no_audio else require_ffmpeg()

        ocr = MangaOcrEngine()
        panels = read_page(page, ocr, right_to_left=not arguments.left_to_right)
        print_transcript(panels)

        if arguments.overlay:
            arguments.overlay.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(arguments.overlay), draw_overlay(page, panels))
            print(f"Overlay written to {arguments.overlay}")

        if ffmpeg is None:
            return 0

        cues = CUES[arguments.cue_language]
        backend: TtsBackend = BACKENDS[arguments.tts](
            dialogue_language=ocr.language, narrator_language=cues.language
        )
        script = build_script([panel.as_text() for panel in panels], cues)
        seconds = render(script, backend, arguments.output, ffmpeg)
        print(f"Narration written to {arguments.output} ({seconds:.1f} s)")
    except (PageError, TtsError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
