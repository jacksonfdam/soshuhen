import cv2
import numpy as np

from narrator.geometry import Box
from narrator.lines import TextLine
from narrator.page import Transcript, as_json, read_page
from tests.conftest import FakeEngine, blank

# Where the lettering of each panel of `grid()` sits, keyed by what it says.
IN_PANEL = {
    "TOP LEFT": Box(200, 150, 200, 30),
    "TOP RIGHT": Box(800, 150, 200, 30),
    "BOTTOM LEFT": Box(200, 550, 200, 30),
    "BOTTOM RIGHT": Box(800, 550, 200, 30),
}


def grid() -> np.ndarray:
    """A 1200x800 page of four bordered panels, two by two."""
    page = blank(1200, 800)
    for left, top in ((20, 20), (610, 20), (20, 410), (610, 410)):
        cv2.rectangle(page, (left, top), (left + 570, top + 370), (0, 0, 0), 4)
    return page


def lettering(*texts: str) -> FakeEngine:
    return FakeEngine([[TextLine(IN_PANEL[text], text, 0.99) for text in texts]])


def texts(transcript: Transcript) -> list[str]:
    return [block.text for panel in transcript.panels for block in panel.blocks]


def test_right_to_left_reads_the_right_panel_first():
    transcript = read_page(grid(), lettering(*IN_PANEL), right_to_left=True)

    assert texts(transcript) == ["Top right", "Top left", "Bottom right", "Bottom left"]


def test_left_to_right_reads_the_left_panel_first():
    transcript = read_page(grid(), lettering(*IN_PANEL), right_to_left=False)

    assert texts(transcript) == ["Top left", "Top right", "Bottom left", "Bottom right"]


def test_a_panel_with_no_text_is_returned_empty_not_left_out():
    engine = lettering("TOP LEFT", "TOP RIGHT", "BOTTOM RIGHT")

    transcript = read_page(grid(), engine, right_to_left=False)

    assert [len(panel.blocks) for panel in transcript.panels] == [1, 1, 0, 1]


def test_a_page_with_no_text_at_all_is_still_a_transcript():
    transcript = read_page(grid(), FakeEngine([[]]), right_to_left=True)

    assert len(transcript.panels) == 4
    assert texts(transcript) == []


def test_two_blocks_in_one_panel_follow_the_reading_direction():
    engine = FakeEngine(
        [
            [
                TextLine(Box(60, 150, 150, 30), "ON THE LEFT", 0.99),
                TextLine(Box(380, 150, 150, 30), "ON THE RIGHT", 0.99),
            ]
        ]
    )

    transcript = read_page(grid(), engine, right_to_left=True)

    assert texts(transcript) == ["On the right", "On the left"]


def test_a_strip_is_one_panel_read_top_to_bottom_whatever_the_direction():
    # One prepared answer per tile of an 800x4000 page, each relative to its own tile.
    engine = FakeEngine(
        [
            [TextLine(Box(100, 100, 200, 30), "FIRST", 0.99)],
            [TextLine(Box(100, 600, 200, 30), "SECOND", 0.99)],
            [TextLine(Box(100, 900, 200, 30), "THIRD", 0.99)],
        ]
    )

    transcript = read_page(blank(800, 4000), engine, right_to_left=True)

    assert [panel.box for panel in transcript.panels] == [Box(0, 0, 800, 4000)]
    assert texts(transcript) == ["First", "Second", "Third"]


def test_two_columns_of_a_strip_are_read_left_to_right():
    engine = FakeEngine(
        [
            [
                TextLine(Box(500, 100, 200, 30), "RIGHT SIDE", 0.99),
                TextLine(Box(60, 100, 200, 30), "LEFT SIDE", 0.99),
            ]
        ]
    )

    transcript = read_page(blank(800, 4000), engine, right_to_left=True)

    assert texts(transcript) == ["Left side", "Right side"]


def test_the_transcript_names_its_engine_language_and_size():
    transcript = read_page(grid(), lettering(*IN_PANEL), right_to_left=True)

    assert (transcript.engine, transcript.language) == ("fake", "en")
    assert (transcript.width, transcript.height) == (1200, 800)


def test_json_carries_plain_lists_and_only_what_the_contract_names():
    body = as_json(read_page(grid(), lettering(*IN_PANEL), right_to_left=True))

    assert set(body) == {"engine", "language", "width", "height", "panels"}
    first = body["panels"][0]
    assert set(first) == {"box", "blocks"}
    left, top, width, height = first["box"]
    assert left > 600 and top < 100 and width > 500 and height > 300
    assert all(type(value) is int for value in first["box"])
    assert first["blocks"] == [{"box": [800, 150, 200, 30], "text": "Top right"}]
