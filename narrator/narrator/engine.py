"""The engine that finds and reads lettering: RapidOCR, PaddleOCR's models on ONNX Runtime.

Chosen over EasyOCR and Tesseract on eight real pages. It read nearly every line, took under a
second a page on a CPU, needs no PyTorch, and ships its three model files inside its wheel, so
this service never reaches for the network.
"""

from importlib.metadata import version

import numpy as np

from narrator.geometry import Box
from narrator.lines import TextLine


class RapidOcrEngine:
    # The default recognition model reads Latin script. Nothing here detects the language of a
    # page; a series lettered in another script needs another engine behind the same protocol.
    language = "en"

    def __init__(self) -> None:
        # Imported here, not at module level: it loads ONNX Runtime and three models, and the
        # geometry must stay importable, and testable, without either.
        import onnxruntime
        from rapidocr import RapidOCR

        # The package's __init__ already set the environment opt-out. This is the runtime's own
        # switch for the same thing, thrown as well in case a later release stops reading it.
        onnxruntime.disable_telemetry_events()

        self.name = f"rapidocr {version('rapidocr')} / PP-OCRv6 small"
        # Its default logging prints a line per page at INFO, which drowns the access log.
        self._engine = RapidOCR(params={"Global.log_level": "error"})

    def read(self, image: np.ndarray) -> list[TextLine]:
        result = self._engine(image)
        # All three are None, not empty, when the page has no text on it.
        if result.txts is None or result.boxes is None or result.scores is None:
            return []
        return [
            TextLine(_bounds(corners), text, float(score))
            for corners, text, score in zip(result.boxes, result.txts, result.scores, strict=True)
        ]


def _bounds(corners: np.ndarray) -> Box:
    """The upright box around a line the engine reports as four corner points."""
    points = np.asarray(corners).reshape(-1, 2)
    left, top = points.min(axis=0)
    right, bottom = points.max(axis=0)
    return Box(int(left), int(top), int(right - left), int(bottom - top))
