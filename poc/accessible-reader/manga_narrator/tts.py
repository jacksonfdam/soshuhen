"""Stage 3: speak a script into one audio file.

A backend only has to turn sentences into audio files, in whatever format it produces. Everything
else (decoding, silences, joining, the output format) happens once, here, through ffmpeg. That is
what keeps a backend to a few lines and lets gTTS, which writes MP3, and pyttsx3, which writes WAV
or AIFF depending on the platform, share one assembly path.
"""

import shutil
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from manga_narrator.narration import Pause, Segment, Speech, Voice

# What every clip is decoded to before joining: mono 16-bit PCM. 24 kHz is gTTS's native rate, so
# its output is never resampled upwards.
SAMPLE_RATE = 24_000
SAMPLE_WIDTH = 2


class TtsError(RuntimeError):
    """Speech could not be produced; the message says what to change."""


class TtsBackend(Protocol):
    def synthesize(self, speeches: Sequence[Speech], workdir: Path) -> list[Path]:
        """One audio file per speech, in the same order, in any format ffmpeg reads.

        Takes the whole batch because pyttsx3 has to: its event loop is only reliably run once
        per process on macOS.
        """
        ...


class GttsBackend:
    """Google Translate's speech endpoint. Good voices in every language, needs the network.

    The text of the page is sent to Google. That is the trade against the offline backend, and
    the reason the choice is a flag rather than a constant.
    """

    def __init__(self, dialogue_language: str, narrator_language: str) -> None:
        self._languages = {Voice.DIALOGUE: dialogue_language, Voice.NARRATOR: narrator_language}

    def synthesize(self, speeches: Sequence[Speech], workdir: Path) -> list[Path]:
        from gtts import gTTS
        from gtts.tts import gTTSError

        paths: list[Path] = []
        for index, speech in enumerate(speeches):
            path = workdir / f"{index:04d}.mp3"
            try:
                gTTS(speech.text, lang=self._languages[speech.voice]).save(str(path))
            except (gTTSError, OSError) as error:
                raise TtsError(
                    f"gTTS could not speak line {index + 1} ({error}). It needs network access; "
                    "use --tts pyttsx3 to synthesise offline."
                ) from error
            paths.append(path)
        return paths


class Pyttsx3Backend:
    """The operating system's own voices. Offline and private; quality depends on what is installed."""

    def __init__(self, dialogue_language: str, narrator_language: str) -> None:
        import pyttsx3

        self._engine = pyttsx3.init()
        voices = self._engine.getProperty("voices")
        self._voices = {
            Voice.DIALOGUE: _pick_voice(voices, dialogue_language),
            Voice.NARRATOR: _pick_voice(voices, narrator_language),
        }

    def synthesize(self, speeches: Sequence[Speech], workdir: Path) -> list[Path]:
        paths: list[Path] = []
        for index, speech in enumerate(speeches):
            path = workdir / f"{index:04d}.wav"
            self._engine.setProperty("voice", self._voices[speech.voice])
            self._engine.save_to_file(speech.text, str(path))
            paths.append(path)
        self._engine.runAndWait()

        missing = [path.name for path in paths if not path.exists() or path.stat().st_size == 0]
        if missing:
            raise TtsError(f"pyttsx3 wrote no audio for {len(missing)} of {len(paths)} lines.")
        return paths


def _pick_voice(voices: Sequence[object], language: str) -> str:
    """The id of an installed voice that speaks `language`.

    Fails rather than falling back to the default voice: an English voice handed Japanese text
    reads out silence or spells punctuation, and the file it produces looks like a success.
    """

    def speaks(voice: object) -> bool:
        tags = [
            tag.decode(errors="ignore") if isinstance(tag, bytes) else str(tag)
            for tag in getattr(voice, "languages", None) or []
        ]
        # espeak reports no language list and encodes it in the id instead.
        tags.append(str(getattr(voice, "id", "")).rsplit("/", 1)[-1])
        return any(tag.lower().replace("-", "_").startswith(language.lower()) for tag in tags)

    matches = [str(voice.id) for voice in voices if speaks(voice)]  # type: ignore[attr-defined]
    if not matches:
        raise TtsError(
            f"No installed system voice speaks '{language}'. Install one in the operating "
            "system's speech settings, or use --tts gtts."
        )
    # macOS lists its novelty voices (Albert, Bells, Zarvox) before the natural ones.
    natural = [voice for voice in matches if ".compact." in voice or ".premium." in voice]
    return (natural or matches)[0]


def require_ffmpeg() -> str:
    """Path to ffmpeg, checked before the slow stages so a missing tool fails in a second."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise TtsError(
            "ffmpeg was not found on PATH. Install it (brew install ffmpeg, apt install ffmpeg) "
            "and run again."
        )
    return ffmpeg


def render(script: Sequence[Segment], backend: TtsBackend, output: Path, ffmpeg: str) -> float:
    """Speak the script into `output` (.wav or .mp3) and return its length in seconds."""
    speeches = [segment for segment in script if isinstance(segment, Speech)]
    if not speeches:
        raise TtsError("There is nothing to say: the script has no speech in it.")

    with tempfile.TemporaryDirectory(prefix="manga-narrator-") as tmp:
        clips = iter(backend.synthesize(speeches, Path(tmp)))
        pcm = bytearray()
        for segment in script:
            if isinstance(segment, Pause):
                pcm += _silence(segment.seconds)
            else:
                pcm += _decode(next(clips), ffmpeg)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".wav":
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(bytes(pcm))
    else:
        _encode(bytes(pcm), output, ffmpeg)

    return len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)


def _silence(seconds: float) -> bytes:
    return bytes(round(seconds * SAMPLE_RATE) * SAMPLE_WIDTH)


def _pcm_arguments() -> list[str]:
    return ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1"]


def _decode(clip: Path, ffmpeg: str) -> bytes:
    """A clip in any format, as raw PCM in the one format the clips are joined in."""
    command = [ffmpeg, "-v", "error", "-i", str(clip), *_pcm_arguments(), "-"]
    return _run(command, None, f"decode {clip.name}")


def _encode(pcm: bytes, output: Path, ffmpeg: str) -> None:
    # ffmpeg picks the codec from the extension, which is what lets .mp3, .ogg or .m4a all work.
    command = [ffmpeg, "-v", "error", "-y", *_pcm_arguments(), "-i", "-", str(output)]
    _run(command, pcm, f"write {output.name}")


def _run(command: list[str], stdin: bytes | None, purpose: str) -> bytes:
    try:
        # No shell and a list of arguments: file names reach ffmpeg as data, never as syntax.
        result = subprocess.run(command, input=stdin, capture_output=True, check=True)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace").strip()
        raise TtsError(f"ffmpeg could not {purpose}: {detail}") from error
    return result.stdout
