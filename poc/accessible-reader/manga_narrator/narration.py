"""Turn the text of a page into a script: what is said, in which voice, with which silences.

Kept apart from speech synthesis so that how a page is narrated can be read, changed and tested
without producing any audio.
"""

from dataclasses import dataclass
from enum import Enum


class Voice(Enum):
    # Announces structure ("Panel 2"). A different voice from the dialogue, so a listener can tell
    # what is on the page from what the narration added.
    NARRATOR = "narrator"
    DIALOGUE = "dialogue"


@dataclass(frozen=True)
class Speech:
    text: str
    voice: Voice


@dataclass(frozen=True)
class Pause:
    seconds: float


Segment = Speech | Pause


@dataclass(frozen=True)
class PanelText:
    """One panel in reading order, with the lines read from it, also in reading order."""

    lines: tuple[str, ...]


@dataclass(frozen=True)
class Cues:
    """The narrator's own words, in the listener's language rather than the manga's."""

    language: str
    panel: str
    no_text: str


CUES = {
    "en": Cues(language="en", panel="Panel {number}.", no_text="No text."),
    "pt": Cues(language="pt", panel="Painel {number}.", no_text="Sem texto."),
    "ja": Cues(language="ja", panel="コマ{number}。", no_text="セリフなし。"),
}

# Long enough to hear as a boundary, short enough that a page of six panels does not drag.
PAUSE_AFTER_CUE = 0.4
PAUSE_BETWEEN_LINES = 0.5
PAUSE_BETWEEN_PANELS = 1.2


def build_script(panels: list[PanelText], cues: Cues) -> list[Segment]:
    """The narration of one page: each panel announced, then its lines, with a gap between panels.

    A panel without text is still announced. Skipping it would leave a listener unable to tell a
    wordless panel from one the reader failed to see.
    """
    script: list[Segment] = []
    for number, panel in enumerate(panels, start=1):
        if script:
            script.append(Pause(PAUSE_BETWEEN_PANELS))

        script.append(Speech(cues.panel.format(number=number), Voice.NARRATOR))
        script.append(Pause(PAUSE_AFTER_CUE))

        if not panel.lines:
            script.append(Speech(cues.no_text, Voice.NARRATOR))
            continue

        for index, line in enumerate(panel.lines):
            if index:
                script.append(Pause(PAUSE_BETWEEN_LINES))
            script.append(Speech(line, Voice.DIALOGUE))

    return script
