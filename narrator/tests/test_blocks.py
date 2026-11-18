from narrator.blocks import clean, group_lines
from narrator.geometry import Box
from narrator.lines import TextLine


def test_capitals_become_sentence_case():
    assert clean(["GOOD MORNING.", "WHERE ARE YOU GOING?"]) == "Good morning. Where are you going?"


def test_a_lone_i_stays_capital():
    assert clean(["I THINK I'M LATE"]) == "I think I'm late"


def test_a_word_split_by_a_hyphen_is_put_back_together():
    assert clean(["EVERY-", "THING IS READY"]) == "Every-thing is ready"


def test_whitespace_is_collapsed():
    assert clean(["  SO   QUIET ", "HERE"]) == "So quiet here"


def test_stray_lower_case_from_the_engine_is_normalised():
    assert clean(["HEy THERE"]) == "Hey there"


def test_a_sentence_after_an_ellipsis_or_an_exclamation_starts_with_a_capital():
    assert clean(["WAIT! NOT YET... MAYBE LATER"]) == "Wait! Not yet... Maybe later"


def test_nothing_in_nothing_out():
    assert clean([]) == ""
    assert clean(["   "]) == ""


def test_stacked_lines_are_one_block_read_top_to_bottom():
    lines = [
        TextLine(Box(100, 140, 180, 30), "ARE YOU", 0.99),
        TextLine(Box(110, 100, 160, 30), "WHERE", 0.99),
        TextLine(Box(105, 180, 170, 30), "GOING?", 0.99),
    ]

    [block] = group_lines(lines)

    assert block.text == "Where are you going?"
    assert block.box == Box(100, 100, 180, 110)


def test_lines_side_by_side_are_separate_blocks():
    lines = [
        TextLine(Box(100, 100, 150, 30), "LEFT", 0.99),
        TextLine(Box(500, 100, 150, 30), "RIGHT", 0.99),
    ]

    assert len(group_lines(lines)) == 2


def test_lines_far_apart_vertically_are_separate_blocks():
    lines = [
        TextLine(Box(100, 100, 150, 30), "ABOVE", 0.99),
        TextLine(Box(100, 300, 150, 30), "BELOW", 0.99),
    ]

    assert len(group_lines(lines)) == 2


def test_a_chain_of_lines_joins_even_when_its_ends_do_not_touch():
    lines = [TextLine(Box(100, 100 + 40 * row, 150, 30), f"ROW {row}", 0.99) for row in range(5)]

    assert len(group_lines(lines)) == 1


def test_no_lines_no_blocks():
    assert group_lines([]) == []
