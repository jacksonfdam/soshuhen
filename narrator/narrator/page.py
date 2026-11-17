"""A page read into what a listener is told: its panels in order, and the text in each."""

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from narrator.blocks import Block, group_lines
from narrator.geometry import Box
from narrator.lines import LineEngine, read_lines
from narrator.panels import detect_panels, reading_order

# A page this many times taller than it is wide is a webtoon strip, not a page of panels.
STRIP_RATIO = 2.5

# Share of the page's short side two boxes may overlap and still count as separate. Detected
# panels include their border stroke, so neighbours overlap by a few pixels.
ORDER_TOLERANCE = 0.01


@dataclass(frozen=True)
class Panel:
    box: Box
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Transcript:
    engine: str
    language: str
    width: int
    height: int
    panels: tuple[Panel, ...]


def read_page(image: np.ndarray, engine: LineEngine, *, right_to_left: bool) -> Transcript:
    """Read a BGR page. `right_to_left` is how its rows are read; a strip ignores it."""
    height, width = image.shape[:2]
    blocks = group_lines(read_lines(image, engine))
    tolerance = round(ORDER_TOLERANCE * min(width, height))

    if height > STRIP_RATIO * width:
        # A strip is scrolled, not laid out: there are no gutters to find, and what little sits
        # side by side on one is read from the left whatever the series' own direction.
        right_to_left = False
        boxes = [Box(0, 0, width, height)]
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        boxes = reading_order(detect_panels(gray), right_to_left=right_to_left, tolerance=tolerance)

    held: list[list[Block]] = [[] for _ in boxes]
    for block in blocks:
        held[_owner(block.box, boxes)].append(block)

    panels = tuple(
        Panel(
            box,
            tuple(
                reading_order(
                    members,
                    lambda block: block.box,
                    right_to_left=right_to_left,
                    tolerance=tolerance,
                )
            ),
        )
        for box, members in zip(boxes, held, strict=True)
    )
    return Transcript(engine.name, engine.language, width, height, panels)


def _owner(box: Box, panels: list[Box]) -> int:
    """The panel a block belongs to: the one it overlaps most, else the nearest.

    Lettering often breaks out of its panel into the gutter, and a caption can sit wholly in it.
    Such a block still has to be read somewhere, and beside the panel it is closest to is where
    a reader's eye takes it.
    """
    overlaps = [panel.overlap(box) for panel in panels]
    if max(overlaps) > 0:
        return overlaps.index(max(overlaps))
    x, y = box.center
    distances = [(panel.center[0] - x) ** 2 + (panel.center[1] - y) ** 2 for panel in panels]
    return distances.index(min(distances))


def as_json(transcript: Transcript) -> dict[str, Any]:
    return {
        "engine": transcript.engine,
        "language": transcript.language,
        "width": transcript.width,
        "height": transcript.height,
        "panels": [
            {
                "box": _corners(panel.box),
                "blocks": [
                    {"box": _corners(block.box), "text": block.text} for block in panel.blocks
                ],
            }
            for panel in transcript.panels
        ],
    }


def _corners(box: Box) -> list[int]:
    # int(): boxes from the engine carry NumPy integers, which the JSON encoder refuses.
    return [int(box.x), int(box.y), int(box.width), int(box.height)]
