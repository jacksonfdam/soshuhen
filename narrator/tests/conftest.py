"""Stand-ins shared by the tests, so none of them loads a model or reads a real page."""

import numpy as np

from narrator.lines import TextLine


class FakeEngine:
    """Answers each call with the next prepared list of lines, and nothing once they run out."""

    name = "fake"
    language = "en"

    def __init__(self, lines_by_call: list[list[TextLine]]) -> None:
        self._pending = list(lines_by_call)
        self.seen: list[tuple[int, int]] = []

    def read(self, image: np.ndarray) -> list[TextLine]:
        self.seen.append((image.shape[0], image.shape[1]))
        return self._pending.pop(0) if self._pending else []


def blank(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 255, np.uint8)
