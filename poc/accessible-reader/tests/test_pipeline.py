import numpy as np
import pytest

from manga_narrator.bubbles import detect_text_regions
from manga_narrator.panels import detect_panels
from manga_narrator.pipeline import PageError, draw_overlay, load_page, read_page
from tests.conftest import BUBBLES, PANELS

# Detected boxes sit on the border stroke, a few pixels either side of the drawn rectangle.
SLACK = 6


def _close(box, expected) -> bool:
    x, y, width, height = expected
    return (
        abs(box.x - x) <= SLACK
        and abs(box.y - y) <= SLACK
        and abs(box.right - (x + width)) <= SLACK
        and abs(box.bottom - (y + height)) <= SLACK
    )


def test_every_drawn_panel_is_found(page):
    found = detect_panels(page)

    assert len(found) == len(PANELS)
    assert all(any(_close(box, panel) for box in found) for panel in PANELS)


def test_a_page_without_panels_is_one_panel(page):
    blank = np.full_like(page, 255)

    (only,) = detect_panels(blank)

    assert (only.width, only.height) == (page.shape[1], page.shape[0])


def test_bubbles_are_found_and_the_panels_themselves_are_not(page):
    regions = detect_text_regions(page)

    centres = {(x, y) for centres in BUBBLES.values() for x, y in centres}
    assert len(regions) == len(centres)
    for region in regions:
        x, y = region.box.center
        assert any(abs(x - cx) <= SLACK and abs(y - cy) <= SLACK for cx, cy in centres)


def test_the_crop_handed_to_ocr_has_no_artwork_in_its_corners(page):
    region = detect_text_regions(page)[0]

    # The panel tone is 160; the corners of an ellipse's bounding box lie outside the bubble.
    assert region.image[0, 0] == 255
    assert region.image[-1, -1] == 255


def test_a_page_is_read_panel_by_panel_in_manga_order(page, ocr):
    panels = read_page(page, ocr)

    assert [len(panel.lines) for panel in panels] == [2, 1, 2, 0, 1]
    assert all(_close(panel.box, expected) for panel, expected in zip(panels, PANELS, strict=True))
    # The fake numbers its answers, so this is the order the bubbles were read in.
    spoken = [line.text for panel in panels for line in panel.lines]
    assert spoken == [f"line {number}" for number in range(1, 7)]


def test_bubbles_in_a_panel_are_read_from_the_right(page, ocr):
    first, second = read_page(page, ocr)[0].lines

    assert first.box.x > second.box.x


def test_an_empty_ocr_answer_is_not_a_line(page):
    class Silent:
        language = "ja"

        def read(self, image):
            return ""

    assert all(panel.lines == () for panel in read_page(page, Silent()))


def test_a_missing_file_is_reported_by_name(tmp_path):
    with pytest.raises(PageError, match=r"nowhere\.jpg"):
        load_page(tmp_path / "nowhere.jpg")


def test_the_overlay_is_the_page_in_colour(page, ocr):
    overlay = draw_overlay(page, read_page(page, ocr))

    assert overlay.shape == (*page.shape, 3)
