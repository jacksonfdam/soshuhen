import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from manga_narrator.narration import Pause, Speech, Voice
from manga_narrator.tts import SAMPLE_RATE, TtsError, _pick_voice, render

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


class ToneBackend:
    """Half a second of non-silence per speech, at a rate that differs from the output's."""

    CLIP_SECONDS = 0.5
    CLIP_RATE = 16_000

    def __init__(self) -> None:
        self.spoken: list[Speech] = []

    def synthesize(self, speeches, workdir: Path) -> list[Path]:
        self.spoken = list(speeches)
        paths = []
        for index, _ in enumerate(speeches):
            path = workdir / f"{index}.wav"
            with wave.open(str(path), "wb") as clip:
                clip.setnchannels(1)
                clip.setsampwidth(2)
                clip.setframerate(self.CLIP_RATE)
                clip.writeframes(b"\x10\x20" * round(self.CLIP_SECONDS * self.CLIP_RATE))
            paths.append(path)
        return paths


SCRIPT = [
    Speech("Panel 1.", Voice.NARRATOR),
    Pause(0.25),
    Speech("line", Voice.DIALOGUE),
    Pause(1.0),
    Speech("Panel 2.", Voice.NARRATOR),
]
EXPECTED_SECONDS = 3 * ToneBackend.CLIP_SECONDS + 0.25 + 1.0


@needs_ffmpeg
def test_speech_and_pauses_are_joined_into_one_wav(tmp_path):
    backend = ToneBackend()
    output = tmp_path / "nested" / "narration.wav"

    seconds = render(SCRIPT, backend, output, shutil.which("ffmpeg"))

    assert seconds == pytest.approx(EXPECTED_SECONDS, abs=0.01)
    with wave.open(str(output)) as result:
        assert result.getframerate() == SAMPLE_RATE
        assert result.getnchannels() == 1
        assert result.getnframes() / SAMPLE_RATE == pytest.approx(EXPECTED_SECONDS, abs=0.01)
    # Pauses are the assembler's business; the backend is only ever handed things to say.
    assert backend.spoken == [segment for segment in SCRIPT if isinstance(segment, Speech)]


@needs_ffmpeg
def test_the_pause_between_clips_is_silence(tmp_path):
    output = tmp_path / "narration.wav"

    render(SCRIPT, ToneBackend(), output, shutil.which("ffmpeg"))

    with wave.open(str(output)) as result:
        # Skip the first clip and land in the middle of the quarter-second pause.
        result.setpos(round((ToneBackend.CLIP_SECONDS + 0.1) * SAMPLE_RATE))
        assert set(result.readframes(round(0.05 * SAMPLE_RATE))) == {0}


@needs_ffmpeg
def test_the_extension_picks_the_format(tmp_path):
    output = tmp_path / "narration.mp3"

    render(SCRIPT, ToneBackend(), output, shutil.which("ffmpeg"))

    # An MP3 starts with an ID3 tag or a frame sync; a WAV would start with RIFF.
    assert output.read_bytes()[:3] == b"ID3" or output.read_bytes()[0] == 0xFF


@needs_ffmpeg
def test_a_clip_that_is_not_audio_is_an_error_that_names_it(tmp_path):
    class Broken:
        def synthesize(self, speeches, workdir):
            path = workdir / "broken.mp3"
            path.write_text("not audio")
            return [path] * len(speeches)

    with pytest.raises(TtsError, match=r"broken\.mp3"):
        render(SCRIPT, Broken(), tmp_path / "narration.wav", shutil.which("ffmpeg"))


def test_a_script_with_nothing_to_say_is_refused(tmp_path):
    with pytest.raises(TtsError, match="nothing to say"):
        render([Pause(1.0)], ToneBackend(), tmp_path / "narration.wav", "ffmpeg")


def _voice(identifier: str, *languages) -> SimpleNamespace:
    return SimpleNamespace(id=identifier, languages=list(languages))


def test_a_voice_is_matched_on_its_language_however_the_system_spells_it():
    voices = [_voice("english", "en_US"), _voice("japanese", b"ja-JP"), _voice("espeak/pt-br")]

    assert _pick_voice(voices, "ja") == "japanese"
    assert _pick_voice(voices, "pt") == "espeak/pt-br"


def test_a_natural_voice_is_preferred_to_a_novelty_one():
    voices = [
        _voice("com.apple.speech.synthesis.voice.Albert", "en_US"),
        _voice("com.apple.voice.compact.en-US.Samantha", "en_US"),
    ]

    assert _pick_voice(voices, "en") == "com.apple.voice.compact.en-US.Samantha"


def test_no_voice_for_the_language_is_an_error_not_a_fallback():
    with pytest.raises(TtsError, match="'ja'"):
        _pick_voice([_voice("english", "en_US")], "ja")
