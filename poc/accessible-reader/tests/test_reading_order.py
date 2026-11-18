from manga_narrator.geometry import Box
from manga_narrator.panels import reading_order

TOP_RIGHT = Box(300, 0, 280, 200)
TOP_LEFT = Box(0, 0, 280, 200)
BOTTOM_RIGHT = Box(300, 220, 280, 200)
BOTTOM_LEFT = Box(0, 220, 280, 200)


def test_a_grid_reads_right_to_left_then_down():
    shuffled = [BOTTOM_LEFT, TOP_LEFT, BOTTOM_RIGHT, TOP_RIGHT]

    assert reading_order(shuffled) == [TOP_RIGHT, TOP_LEFT, BOTTOM_RIGHT, BOTTOM_LEFT]


def test_left_to_right_only_flips_the_rows():
    shuffled = [BOTTOM_LEFT, TOP_LEFT, BOTTOM_RIGHT, TOP_RIGHT]

    ordered = reading_order(shuffled, right_to_left=False)

    assert ordered == [TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT]


def test_a_tall_panel_is_read_before_the_two_stacked_beside_it():
    # Sorting on (row, column) puts the lower-left panel last but cannot decide between the tall
    # panel and the upper-left one, which start on the same line.
    tall = Box(300, 0, 280, 420)
    upper = Box(0, 0, 280, 200)
    lower = Box(0, 220, 280, 200)

    assert reading_order([lower, upper, tall]) == [tall, upper, lower]


def test_a_wide_panel_between_two_rows_keeps_its_place():
    wide = Box(0, 220, 580, 150)
    bottom_right = Box(300, 390, 280, 200)
    bottom_left = Box(0, 390, 280, 200)

    ordered = reading_order([bottom_left, wide, TOP_LEFT, bottom_right, TOP_RIGHT])

    assert ordered == [TOP_RIGHT, TOP_LEFT, wide, bottom_right, bottom_left]


def test_touching_borders_still_separate_within_the_tolerance():
    # Detected boxes include the border stroke, so neighbours overlap by a few pixels.
    right = Box(296, 0, 284, 200)
    left = Box(0, 0, 300, 200)

    assert reading_order([left, right], tolerance=6) == [right, left]


def test_boxes_no_gutter_separates_come_back_complete_and_in_a_stable_order():
    # A pinwheel: every straight line across the group cuts through a box.
    pinwheel = [
        Box(0, 0, 200, 100),
        Box(200, 0, 100, 200),
        Box(100, 200, 200, 100),
        Box(0, 100, 100, 200),
    ]

    first = reading_order(pinwheel)
    second = reading_order(list(reversed(pinwheel)))

    assert sorted(first, key=lambda b: (b.x, b.y)) == sorted(pinwheel, key=lambda b: (b.x, b.y))
    assert first == second


def test_items_are_ordered_by_the_box_they_carry():
    items = [("left", TOP_LEFT), ("right", TOP_RIGHT)]

    ordered = reading_order(items, lambda item: item[1])

    assert [name for name, _ in ordered] == ["right", "left"]


def test_nothing_and_one_thing_are_already_in_order():
    assert reading_order([]) == []
    assert reading_order([TOP_LEFT]) == [TOP_LEFT]
