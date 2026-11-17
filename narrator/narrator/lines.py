"""The lines of text on a page, as the engine found them, minus what is not lettering.

The engine both finds and reads the lines. Finding bubbles by their shape first, as the proof of
concept did, missed most text that is not in a white bubble: captions, narration boxes, and
almost everything on a coloured webtoon page.
"""

from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np

from narrator.geometry import Box

# Below this the engine is guessing, and what it guesses at is usually artwork.
MIN_SCORE = 0.6

TILE_HEIGHT = 1600
# Taller than any line of lettering, so a line cut by one tile's edge is whole in the next.
TILE_OVERLAP = 200

# Two readings covering more than this share of the smaller box are the same line seen twice.
SAME_LINE_OVERLAP = 0.5

_PUNCTUATION = set("?!. ")


@dataclass(frozen=True)
class TextLine:
    box: Box
    text: str
    score: float


class LineEngine(Protocol):
    # Reported to clients with every transcript, so a reading can be traced to what produced it.
    name: str
    # ISO 639-1 code of the text this engine produces; the reader picks its voice from it.
    language: str

    def read(self, image: np.ndarray) -> list[TextLine]:
        """Lines found in a BGR image, with boxes relative to that image."""
        ...


def is_text(line: TextLine) -> bool:
    """Whether a line is lettering rather than a page number, a stray mark or a sound effect.

    Punctuation alone is kept: a bubble holding only "?!" is something a character says.
    """
    if line.score < MIN_SCORE:
        return False
    stripped = line.text.strip()
    if not stripped:
        return False
    letters = sum(character.isascii() and character.isalpha() for character in stripped)
    return letters >= 2 or set(stripped) <= _PUNCTUATION


def tile_tops(height: int) -> list[int]:
    """Where each tile of a page starts.

    The engine scales a page down to 2,000 px on its long side, which turns the lettering of a
    16,000 px strip into smudges. A page only somewhat taller than a tile is left whole: the
    scaling costs it little, and cutting it would cost a second pass.
    """
    if height <= TILE_HEIGHT * 1.5:
        return [0]
    tops = [0]
    while tops[-1] + TILE_HEIGHT < height:
        tops.append(tops[-1] + TILE_HEIGHT - TILE_OVERLAP)
    return tops


def read_lines(image: np.ndarray, engine: LineEngine) -> list[TextLine]:
    """Every line of lettering on the page, in page coordinates, each one once."""
    found: list[TextLine] = []
    for top in tile_tops(image.shape[0]):
        for line in engine.read(image[top : top + TILE_HEIGHT]):
            box = line.box
            found.append(replace(line, box=Box(box.x, box.y + top, box.width, box.height)))
    return [line for line in _once(found) if is_text(line)]


def _once(lines: list[TextLine]) -> list[TextLine]:
    """Drop the weaker of two readings of the same line, which a tile overlap produces."""
    kept: list[TextLine] = []
    for line in sorted(lines, key=lambda candidate: candidate.score, reverse=True):
        if all(not _same_place(line.box, other.box) for other in kept):
            kept.append(line)
    return kept


def _same_place(a: Box, b: Box) -> bool:
    return a.overlap(b) > SAME_LINE_OVERLAP * min(a.area, b.area)
