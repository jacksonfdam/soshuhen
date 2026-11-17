"""Stage 1: turn a cropped text region into text.

The engine sits behind a protocol because it is the part most likely to change. manga-ocr reads
Japanese and nothing else, so a page in another language needs a different engine, and the engine
is what tells the speech stage which language it is about to speak.
"""

from typing import Protocol

import numpy as np


class OcrEngine(Protocol):
    # ISO 639-1 code of the text this engine produces; the speech stage picks its voice from it.
    language: str

    def read(self, image: np.ndarray) -> str: ...


class MangaOcrEngine:
    """manga-ocr: a model trained on manga lettering, vertical text and furigana included."""

    language = "ja"

    def __init__(self) -> None:
        # Imported here, not at module level: this pulls in torch and loads a 400 MB model, and
        # the geometry and narration code must stay importable (and testable) without either.
        from manga_ocr import MangaOcr

        self._model = MangaOcr()

    def read(self, image: np.ndarray) -> str:
        from PIL import Image

        return self._model(Image.fromarray(image)).strip()
