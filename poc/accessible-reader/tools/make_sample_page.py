"""Draw a synthetic manga page to try the reader on: `python tools/make_sample_page.py`.

A drawn page rather than a scanned one because a real page is someone's copyrighted work and does
not belong in the repository. It also has a known right answer: five panels, laid out so that
sorting on coordinates alone gets the order wrong, with one wordless panel.
"""

import argparse
import glob
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGE_SIZE = (1200, 1700)

# (x, y, width, height), listed in the order they should be read. Panel 3 is tall and sits beside
# panels 4 and 5, which is the case a row-by-row sort cannot order.
PANELS = [
    (520, 40, 640, 520),
    (40, 40, 450, 520),
    (640, 590, 520, 1070),
    (40, 590, 570, 510),
    (40, 1130, 570, 530),
]

# Panel index -> bubbles as (centre x, centre y, text), in reading order. Panel 4 has none.
BUBBLES = {
    0: [(1010, 270, "おはよう！"), (680, 310, "今日はいい天気だね")],
    1: [(260, 300, "どこへ行くの？")],
    2: [(1010, 800, "学校だよ"), (800, 1300, "急がないと遅れる！")],
    4: [(320, 1380, "待って！")],
}

PANEL_TONES = [176, 150, 188, 140, 164]

FONT_SIZE = 44
CHARACTERS_PER_COLUMN = 5

# Fonts with Japanese glyphs, where the common systems keep them.
FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W*.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/**/NotoSansCJK*.ttc",
    "/usr/share/fonts/**/NotoSansJP*.otf",
    "/usr/share/fonts/**/ipag*.ttf",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]


def find_font() -> str | None:
    for pattern in FONT_CANDIDATES:
        matches = sorted(glob.glob(pattern, recursive=True))
        if matches:
            return matches[0]
    return None


def draw_bubble(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, x: int, y: int, text: str):
    """An elliptical bubble with its text set vertically, columns running right to left."""
    columns = [
        text[start : start + CHARACTERS_PER_COLUMN]
        for start in range(0, len(text), CHARACTERS_PER_COLUMN)
    ]
    text_width = len(columns) * FONT_SIZE
    text_height = max(len(column) for column in columns) * FONT_SIZE

    # An ellipse has to be about 1.6 times its inscribed rectangle to clear the corners.
    half_width = text_width * 0.8 + 30
    half_height = text_height * 0.8 + 30
    draw.ellipse(
        (x - half_width, y - half_height, x + half_width, y + half_height),
        fill=255,
        outline=0,
        width=5,
    )

    for column_index, column in enumerate(columns):
        column_x = x + text_width / 2 - (column_index + 0.5) * FONT_SIZE
        for row_index, character in enumerate(column):
            row_y = y - text_height / 2 + (row_index + 0.5) * FONT_SIZE
            draw.text((column_x, row_y), character, font=font, fill=0, anchor="mm")


def draw_page(font_path: str) -> Image.Image:
    page = Image.new("L", PAGE_SIZE, 255)
    draw = ImageDraw.Draw(page)
    font = ImageFont.truetype(font_path, FONT_SIZE)

    for (x, y, width, height), tone in zip(PANELS, PANEL_TONES, strict=True):
        draw.rectangle((x, y, x + width, y + height), fill=tone, outline=0, width=7)

    for bubbles in BUBBLES.values():
        for x, y, text in bubbles:
            draw_bubble(draw, font, x, y, text)

    return page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=Path("pagina_exemplo.jpg"))
    parser.add_argument(
        "--font", help="a font file with Japanese glyphs (default: search the system)"
    )
    arguments = parser.parse_args()

    font_path = arguments.font or find_font()
    if font_path is None:
        print("error: no Japanese font found; pass one with --font.", file=sys.stderr)
        return 1

    draw_page(font_path).save(arguments.output, quality=92)
    print(f"Sample page written to {arguments.output} (font: {font_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
