"""A drawn page and a stand-in OCR engine, so the suite needs neither a font nor the model."""

import cv2
import numpy as np
import pytest

PAGE_WIDTH, PAGE_HEIGHT = 600, 800

# (x, y, width, height) in the order they should be read: two panels on top, then a tall panel on
# the right beside two stacked ones.
PANELS = [
    (310, 20, 270, 240),
    (20, 20, 270, 240),
    (330, 280, 250, 500),
    (20, 280, 290, 240),
    (20, 540, 290, 240),
]

# Panel index -> bubble centres, in reading order. The fourth panel is wordless.
BUBBLES = {
    0: [(510, 100), (390, 180)],
    1: [(150, 140)],
    2: [(455, 400), (455, 650)],
    4: [(160, 660)],
}


def _bubble(page: np.ndarray, x: int, y: int) -> None:
    cv2.ellipse(page, (x, y), (48, 34), 0, 0, 360, 255, cv2.FILLED)
    cv2.ellipse(page, (x, y), (48, 34), 0, 0, 360, 0, 2)
    # Latin text is ink like any other; what is being tested is where the reader looks.
    cv2.putText(page, "abc", (x - 30, y + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)


@pytest.fixture
def page() -> np.ndarray:
    image = np.full((PAGE_HEIGHT, PAGE_WIDTH), 255, np.uint8)
    for x, y, width, height in PANELS:
        cv2.rectangle(image, (x, y), (x + width, y + height), 160, cv2.FILLED)
        cv2.rectangle(image, (x, y), (x + width, y + height), 0, 4)
    for centres in BUBBLES.values():
        for x, y in centres:
            _bubble(image, x, y)
    return image


class FakeOcr:
    """Answers with a counter, so a test can tell in which order the regions were read."""

    language = "ja"

    def __init__(self) -> None:
        self.calls = 0

    def read(self, image: np.ndarray) -> str:
        self.calls += 1
        return f"line {self.calls}"


@pytest.fixture
def ocr() -> FakeOcr:
    return FakeOcr()
