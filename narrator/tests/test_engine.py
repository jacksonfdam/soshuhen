"""The one test that loads the real model. Its files ship inside the wheel, so it needs no network."""

import cv2

from narrator.engine import RapidOcrEngine
from narrator.geometry import Box
from tests.conftest import blank


def test_the_real_engine_reads_lettering_the_test_drew():
    page = blank(900, 600)
    cv2.putText(page, "GOOD MORNING", (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    cv2.putText(page, "WHERE ARE YOU", (60, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    engine = RapidOcrEngine()
    lines = engine.read(page)

    found = " ".join(line.text.upper() for line in lines)
    assert "GOOD MORNING" in found
    assert "WHERE ARE YOU" in found
    assert all(isinstance(line.box, Box) and line.box.width > 0 for line in lines)
    assert all(0 <= line.score <= 1 for line in lines)
    assert engine.language == "en"
    assert engine.name.startswith("rapidocr ")


def test_a_page_with_nothing_on_it_reads_as_no_lines():
    assert RapidOcrEngine().read(blank(900, 600)) == []
