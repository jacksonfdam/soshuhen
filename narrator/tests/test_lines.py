from itertools import pairwise

from narrator.geometry import Box
from narrator.lines import TILE_HEIGHT, TILE_OVERLAP, TextLine, is_text, read_lines, tile_tops
from tests.conftest import FakeEngine, blank


ANYWHERE = Box(10, 10, 100, 20)


def line(text: str, score: float = 0.99, box: Box = ANYWHERE) -> TextLine:
    return TextLine(box, text, score)


def test_low_confidence_is_dropped():
    assert not is_text(line("HELLO", 0.59))


def test_two_latin_letters_are_enough():
    assert is_text(line("NO"))


def test_a_lone_letter_or_digit_is_noise():
    assert not is_text(line("4"))
    assert not is_text(line("A"))


def test_other_scripts_are_noise():
    assert not is_text(line("が"))


def test_pure_punctuation_is_kept():
    assert is_text(line("?!"))
    assert is_text(line("..."))


def test_a_normal_page_is_one_tile():
    assert tile_tops(1600) == [0]
    assert tile_tops(2400) == [0]


def test_a_strip_is_cut_into_overlapping_tiles():
    tops = tile_tops(5000)

    assert tops[0] == 0
    assert tops[1] == 1400
    assert tops[-1] + TILE_HEIGHT >= 5000
    assert all(b - a == TILE_HEIGHT - TILE_OVERLAP for a, b in pairwise(tops))


def test_every_tile_handed_to_the_engine_is_at_most_a_tile_high():
    engine = FakeEngine([])

    read_lines(blank(800, 5000), engine)

    assert len(engine.seen) == len(tile_tops(5000))
    assert all(height <= TILE_HEIGHT and width == 800 for height, width in engine.seen)


def test_tile_lines_come_back_in_page_coordinates():
    engine = FakeEngine([[], [line("SECOND TILE", box=Box(50, 100, 200, 30))]])

    [found] = read_lines(blank(800, 5000), engine)

    assert found.box == Box(50, 1500, 200, 30)


def test_a_line_seen_in_two_tiles_is_kept_once_with_the_better_reading():
    # The same place on the page: y=1500 in the first tile is y=100 in the second.
    engine = FakeEngine(
        [
            [line("WHERE ARE YO", 0.7, Box(50, 1500, 200, 30))],
            [line("WHERE ARE YOU", 0.98, Box(50, 100, 210, 30))],
        ]
    )

    assert [found.text for found in read_lines(blank(800, 5000), engine)] == ["WHERE ARE YOU"]


def test_two_lines_that_only_touch_are_both_kept():
    engine = FakeEngine(
        [
            [
                line("FIRST LINE", box=Box(50, 100, 200, 30)),
                line("NEXT LINE", box=Box(50, 128, 200, 30)),
            ]
        ]
    )

    assert len(read_lines(blank(800, 1000), engine)) == 2


def test_noise_is_filtered_out_of_what_comes_back():
    engine = FakeEngine([[line("HELLO"), line("7"), line("FAINT", 0.3)]])

    assert [found.text for found in read_lines(blank(800, 1000), engine)] == ["HELLO"]
