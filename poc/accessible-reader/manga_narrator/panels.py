"""Stage 2: find the panels on a page and put them in the order a reader follows.

Detection and ordering are separate functions on purpose. Detection is the part a proof of concept
gets wrong on real pages (borderless panels, art that bleeds into the gutter), and it can be
replaced by a trained detector without touching the ordering, which is plain geometry.
"""

from collections.abc import Callable, Sequence
from typing import TypeVar

import cv2
import numpy as np

from manga_narrator.geometry import Box

T = TypeVar("T")

# A panel smaller than this share of the page is a stray mark, a page number or lettering in the
# gutter, not a panel.
MIN_PANEL_AREA_RATIO = 0.02

# Above this share of a larger box, a box is that panel's own inner frame rather than a neighbour.
NESTED_OVERLAP_RATIO = 0.9


def detect_panels(gray: np.ndarray) -> list[Box]:
    """Bounding boxes of the panels on a grayscale page, in no particular order.

    Panels are taken to be the large ink-bounded shapes separated by white gutters. A page with no
    such shape (a full-page spread, a borderless layout) comes back as a single panel covering the
    page, so the stages after this one always have something to read.
    """
    page_height, page_width = gray.shape[:2]

    # Otsu rather than a fixed level: scans differ in how white their paper is.
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Hand-drawn borders have gaps; an open border is a contour that leaks into the next panel.
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    # External only: everything drawn inside a panel belongs to it and must not become a panel.
    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = MIN_PANEL_AREA_RATIO * page_width * page_height
    boxes = [Box(*cv2.boundingRect(contour)) for contour in contours]
    boxes = _drop_nested([box for box in boxes if box.area >= min_area])

    return boxes or [Box(0, 0, page_width, page_height)]


def _drop_nested(boxes: list[Box]) -> list[Box]:
    """Keep the outer box where one sits almost entirely inside another."""
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda b: b.area, reverse=True):
        if all(box.overlap(outer) < NESTED_OVERLAP_RATIO * box.area for outer in kept):
            kept.append(box)
    return kept


def reading_order(
    items: Sequence[T],
    box_of: Callable[[T], Box] = lambda item: item,  # type: ignore[assignment,return-value]
    *,
    right_to_left: bool = True,
    tolerance: int = 0,
) -> list[T]:
    """Order items the way a manga page is read: top to bottom, and right to left within a row.

    This is a recursive XY-cut. A gutter that runs clean across the group splits it into bands
    read top to bottom; where none does, a vertical gutter splits it into columns read from the
    right. Recursing is what gets a tall panel beside two stacked ones right, which sorting on
    coordinates alone cannot: the tall panel shares a row with both of its neighbours.

    `box_of` lets the same ordering serve panels and the speech bubbles inside one. `tolerance` is
    how many pixels two boxes may overlap and still count as separated, for detected boxes whose
    borders touch.
    """
    items = list(items)
    if len(items) <= 1:
        return items

    def recurse(group: list[T]) -> list[T]:
        return reading_order(group, box_of, right_to_left=right_to_left, tolerance=tolerance)

    rows = _split(items, lambda i: box_of(i).y, lambda i: box_of(i).bottom, tolerance)
    if len(rows) > 1:
        return [item for row in rows for item in recurse(row)]

    columns = _split(items, lambda i: box_of(i).x, lambda i: box_of(i).right, tolerance)
    if len(columns) > 1:
        if right_to_left:
            columns.reverse()
        return [item for column in columns for item in recurse(column)]

    # No gutter crosses the group either way (overlapping boxes, a pinwheel layout). There is no
    # right answer here, only a stable one: the same page must always read the same.
    horizontal = -1 if right_to_left else 1
    return sorted(items, key=lambda i: (box_of(i).y, horizontal * box_of(i).x))


def _split(
    items: list[T],
    start: Callable[[T], int],
    end: Callable[[T], int],
    tolerance: int,
) -> list[list[T]]:
    """Group items along one axis, starting a new group wherever a gap crosses all of them."""
    ordered = sorted(items, key=start)
    groups = [[ordered[0]]]
    reach = end(ordered[0])
    for item in ordered[1:]:
        if start(item) >= reach - tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
        reach = max(reach, end(item))
    return groups
