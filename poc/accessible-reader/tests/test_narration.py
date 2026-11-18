from manga_narrator.narration import (
    CUES,
    PAUSE_AFTER_CUE,
    PAUSE_BETWEEN_LINES,
    PAUSE_BETWEEN_PANELS,
    PanelText,
    Pause,
    Speech,
    Voice,
    build_script,
)

EN = CUES["en"]


def test_each_panel_is_announced_by_the_narrator_before_its_lines():
    script = build_script([PanelText(("first", "second"))], EN)

    assert script == [
        Speech("Panel 1.", Voice.NARRATOR),
        Pause(PAUSE_AFTER_CUE),
        Speech("first", Voice.DIALOGUE),
        Pause(PAUSE_BETWEEN_LINES),
        Speech("second", Voice.DIALOGUE),
    ]


def test_the_longest_pause_is_the_one_between_panels():
    script = build_script([PanelText(("a",)), PanelText(("b",))], EN)

    pauses = [segment.seconds for segment in script if isinstance(segment, Pause)]
    assert pauses == [PAUSE_AFTER_CUE, PAUSE_BETWEEN_PANELS, PAUSE_AFTER_CUE]
    assert max(pauses) == PAUSE_BETWEEN_PANELS


def test_a_wordless_panel_is_announced_rather_than_skipped():
    script = build_script([PanelText(())], EN)

    assert script == [
        Speech("Panel 1.", Voice.NARRATOR),
        Pause(PAUSE_AFTER_CUE),
        Speech("No text.", Voice.NARRATOR),
    ]


def test_the_script_neither_starts_nor_ends_on_a_pause():
    script = build_script([PanelText(("a",)), PanelText(()), PanelText(("b", "c"))], EN)

    assert isinstance(script[0], Speech)
    assert isinstance(script[-1], Speech)


def test_cues_are_spoken_in_the_language_asked_for():
    script = build_script([PanelText(("a",))], CUES["pt"])

    assert script[0] == Speech("Painel 1.", Voice.NARRATOR)


def test_no_panels_is_an_empty_script():
    assert build_script([], EN) == []
