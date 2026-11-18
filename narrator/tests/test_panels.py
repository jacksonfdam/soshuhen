import cv2
import numpy as np

from narrator.geometry import Box
from narrator.panels import detect_panels


def test_three_bordered_panels_are_found():
    page = np.full((800, 600), 255, np.uint8)
    for top_left, bottom_right in (
        ((20, 20), (580, 380)),
        ((20, 420), (290, 780)),
        ((310, 420), (580, 780)),
    ):
        cv2.rectangle(page, top_left, bottom_right, 0, 4)

    assert len(detect_panels(page)) == 3


def test_a_page_with_no_borders_is_one_panel_covering_it():
    page = np.full((800, 600), 128, np.uint8)

    assert detect_panels(page) == [Box(0, 0, 600, 800)]
