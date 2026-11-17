"""Lines grouped into the blocks a listener hears as one utterance: a bubble, a caption.

The engine reports lettering a line at a time, and a bubble is usually several. Nothing here
looks at the artwork; lines that sit on top of each other are taken to belong together.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from narrator.geometry import Box
from narrator.lines import TextLine

# Lines of one bubble are set closer than a line is tall; the next bubble down is further away.
MAX_GAP_RATIO = 0.8
# Lettering in a bubble is centred, so its lines share most of their width. A bubble beside this
# one shares none.
MIN_OVERLAP_RATIO = 0.3

_SENTENCE_START = re.compile(r"([.!?]\s+)([a-z])")
_LONE_I = re.compile(r"\bi\b")


@dataclass(frozen=True)
class Block:
    box: Box
    text: str


def clean(lines: Sequence[str]) -> str:
    """The lines of one block as a sentence a speech engine reads naturally."""
    text = ""
    for line in (" ".join(raw.split()) for raw in lines):
        if not line:
            continue
        # A word the letterer broke across two lines. The hyphen stays: it cannot be told from
        # the one in a compound, and a voice reads "every-thing" correctly either way.
        text += line if not text or text.endswith("-") else f" {line}"

    # Comic lettering is capitals throughout, and a speech engine spells out a short word in
    # capitals ("NO" becomes "en oh") instead of saying it.
    text = text.lower()
    text = _SENTENCE_START.sub(lambda found: found.group(1) + found.group(2).upper(), text)
    text = _LONE_I.sub("I", text)
    return text[:1].upper() + text[1:]


def group_lines(lines: Sequence[TextLine]) -> list[Block]:
    """Blocks made of the lines stacked on each other, each read top to bottom."""
    parent = list(range(len(lines)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first, a in enumerate(lines):
        for second in range(first + 1, len(lines)):
            if _stacked(a.box, lines[second].box):
                parent[root(first)] = root(second)

    members: dict[int, list[TextLine]] = {}
    for index, line in enumerate(lines):
        members.setdefault(root(index), []).append(line)

    blocks = [_block(group) for group in members.values()]
    return sorted(blocks, key=lambda block: (block.box.y, block.box.x))


def _stacked(a: Box, b: Box) -> bool:
    gap = max(a.y, b.y) - min(a.bottom, b.bottom)
    overlap = min(a.right, b.right) - max(a.x, b.x)
    return gap < MAX_GAP_RATIO * min(a.height, b.height) and overlap > MIN_OVERLAP_RATIO * min(
        a.width, b.width
    )


def _block(lines: list[TextLine]) -> Block:
    ordered = sorted(lines, key=lambda line: line.box.y)
    left = min(line.box.x for line in ordered)
    top = min(line.box.y for line in ordered)
    right = max(line.box.right for line in ordered)
    bottom = max(line.box.bottom for line in ordered)
    return Block(Box(left, top, right - left, bottom - top), clean([line.text for line in ordered]))
