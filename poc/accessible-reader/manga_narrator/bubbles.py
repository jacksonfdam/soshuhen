"""Find where the text is, so stage 1 has something to read.

manga-ocr recognises the text in a crop; it does not find text on a page. Handing it a whole page
returns one confident, meaningless line. This module is the detector it needs, done with contours
rather than a model: a speech bubble is a bright, roughly convex blob with ink inside it.

It finds bubbles and bordered caption boxes. Text laid straight over artwork or screentone has no
bright blob around it and is missed; a trained detector such as comic-text-detector is the
replacement when that matters.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from manga_narrator.geometry import Box

# Paper white, with room for JPEG noise and slightly grey scans.
LIGHT_THRESHOLD = 200

# Bubbles are small against the page. The upper bound is what keeps out the page background and
# panels with a white interior, which are bright blobs with ink inside them too.
MIN_AREA_RATIO = 0.002
MAX_AREA_RATIO = 0.08

# Area over convex-hull area. Ellipses and rounded boxes sit near 1; the white space left between
# drawn figures is ragged and sits well below.
MIN_SOLIDITY = 0.85

# Share of the blob that is ink. Lettering fills a bubble only partly: less than the lower bound
# is an empty highlight, more than the upper bound is artwork.
MIN_INK_RATIO = 0.02
MAX_INK_RATIO = 0.5


@dataclass(frozen=True)
class TextRegion:
    box: Box
    # The crop handed to OCR, with everything outside the bubble painted white.
    image: np.ndarray


def detect_text_regions(gray: np.ndarray) -> list[TextRegion]:
    """Speech bubbles and caption boxes on a grayscale page, in no particular order."""
    page_area = gray.shape[0] * gray.shape[1]
    _, light = cv2.threshold(gray, LIGHT_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Two-level hierarchy: the outline of each bright blob, and the holes in it. The holes are the
    # lettering, and a blob without any is not worth measuring.
    contours, hierarchy = cv2.findContours(light, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []

    regions: list[TextRegion] = []
    for contour, (_, _, first_hole, parent) in zip(contours, hierarchy[0], strict=True):
        if parent != -1 or first_hole == -1:
            continue

        area = cv2.contourArea(contour)
        if not MIN_AREA_RATIO * page_area <= area <= MAX_AREA_RATIO * page_area:
            continue

        hull_area = cv2.contourArea(cv2.convexHull(contour))
        if hull_area == 0 or area / hull_area < MIN_SOLIDITY:
            continue

        box = Box(*cv2.boundingRect(contour))
        inside = np.zeros((box.height, box.width), np.uint8)
        cv2.drawContours(inside, [contour], -1, 255, cv2.FILLED, offset=(-box.x, -box.y))
        crop = gray[box.y : box.bottom, box.x : box.right]

        ink = np.count_nonzero((inside == 255) & (crop <= LIGHT_THRESHOLD))
        if not MIN_INK_RATIO <= ink / max(np.count_nonzero(inside), 1) <= MAX_INK_RATIO:
            continue

        # The bounding box of a round bubble has artwork in its corners, and OCR reads it as text.
        cleaned = crop.copy()
        cleaned[inside == 0] = 255
        regions.append(TextRegion(box=box, image=cleaned))

    return regions
