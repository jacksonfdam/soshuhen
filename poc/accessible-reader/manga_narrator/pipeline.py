"""The page-reading half of the pipeline: an image in, ordered text out.

Speech is not called from here. Reading a page and speaking it fail for unrelated reasons, and
keeping them apart means a transcript can be had, and checked, without making any audio.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from manga_narrator.bubbles import TextRegion, detect_text_regions
from manga_narrator.geometry import Box
from manga_narrator.narration import PanelText
from manga_narrator.ocr import OcrEngine
from manga_narrator.panels import detect_panels, reading_order

# Share of the page's short side two panel boxes may overlap and still count as neighbours.
# Detected boxes include the border stroke, so touching panels overlap by its width.
PANEL_TOLERANCE_RATIO = 0.01

# A "bubble" this large against its panel is the panel's own white interior, not lettering.
MAX_REGION_SHARE_OF_PANEL = 0.6


class PageError(RuntimeError):
    """The page could not be read as an image."""


@dataclass(frozen=True)
class ReadLine:
    box: Box
    text: str


@dataclass(frozen=True)
class ReadPanel:
    box: Box
    lines: tuple[ReadLine, ...]

    def as_text(self) -> PanelText:
        return PanelText(lines=tuple(line.text for line in self.lines))


def load_page(path: Path) -> np.ndarray:
    # imread returns None for a missing file and for an unreadable one alike, and never raises.
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise PageError(f"Could not read an image from {path}.")
    return image


def read_page(gray: np.ndarray, ocr: OcrEngine, *, right_to_left: bool = True) -> list[ReadPanel]:
    """Panels in reading order, each with the text of its bubbles in reading order."""
    tolerance = round(PANEL_TOLERANCE_RATIO * min(gray.shape[:2]))
    panels = reading_order(detect_panels(gray), right_to_left=right_to_left, tolerance=tolerance)

    by_panel: dict[Box, list[TextRegion]] = {panel: [] for panel in panels}
    for region in detect_text_regions(gray):
        panel = _owner(region.box, panels)
        if region.box.area <= MAX_REGION_SHARE_OF_PANEL * panel.area:
            by_panel[panel].append(region)

    result: list[ReadPanel] = []
    for panel in panels:
        ordered = reading_order(by_panel[panel], lambda r: r.box, right_to_left=right_to_left)
        lines = (ReadLine(region.box, ocr.read(region.image)) for region in ordered)
        # OCR can come back empty for a region that held no lettering after all.
        result.append(ReadPanel(panel, tuple(line for line in lines if line.text)))
    return result


def _owner(box: Box, panels: list[Box]) -> Box:
    """The panel a text region belongs to.

    Largest overlap wins, since a bubble may straddle a border. Text in the gutter overlaps
    nothing and goes to the nearest panel rather than being dropped: losing a line is worse for a
    listener than hearing it one panel early.
    """
    best = max(panels, key=box.overlap)
    if box.overlap(best) > 0:
        return best

    x, y = box.center

    def distance(panel: Box) -> float:
        dx = max(panel.x - x, 0, x - panel.right)
        dy = max(panel.y - y, 0, y - panel.bottom)
        return dx * dx + dy * dy

    return min(panels, key=distance)


def draw_overlay(gray: np.ndarray, panels: list[ReadPanel]) -> np.ndarray:
    """The page with the detected panels and bubbles numbered in reading order.

    For the sighted person debugging detection: the transcript shows what was read, this shows
    where the reader looked.
    """
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    scale = max(min(gray.shape[:2]) / 1000, 0.5)
    thickness = max(round(2 * scale), 1)

    for panel_number, panel in enumerate(panels, start=1):
        box = panel.box
        cv2.rectangle(canvas, (box.x, box.y), (box.right, box.bottom), (0, 0, 255), thickness * 2)
        origin = (box.x + round(12 * scale), box.y + round(44 * scale))
        cv2.putText(
            canvas,
            str(panel_number),
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            1.4 * scale,
            (0, 0, 255),
            thickness * 2,
        )
        for line_number, line in enumerate(panel.lines, start=1):
            box = line.box
            cv2.rectangle(canvas, (box.x, box.y), (box.right, box.bottom), (255, 128, 0), thickness)
            cv2.putText(
                canvas,
                f"{panel_number}.{line_number}",
                (box.x, max(box.y - round(6 * scale), round(20 * scale))),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7 * scale,
                (255, 128, 0),
                thickness,
            )
    return canvas
