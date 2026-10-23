"""Chapter numbers for a PDF's entries, and which edition the PDF is.

Web novel numbers run across the whole work and are kept as they come. What
has no number of its own - prologues, POV and side chapters - is slotted
between its neighbours with a fraction, so it sorts where the reader met it
and never takes a number a real chapter could arrive with later.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.importer.pdf import PdfBook, PdfEntry

Edition = Literal["web", "light"]

_CHAPTER = re.compile(r"^\s*chapter\s+(\d+(?:\.\d+)?)\b[\s:.\-–—]*(.*)$", re.IGNORECASE)
_PROLOGUE = re.compile(r"^\s*prologue\s+(\d)\b[\s:.\-–—]*(.*)$", re.IGNORECASE)
_UNNUMBERED_PROLOGUE = re.compile(r"^\s*prologue\b", re.IGNORECASE)
_FRONT_MATTER = re.compile(r"^\s*(cover|characters|map)\b", re.IGNORECASE)
_PREFIX = re.compile(r"^\s*(LN|WN)\s*-\s", re.IGNORECASE)
_VOLUME_WORD = re.compile(r"\bvol(?:ume)?\.?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_UNDERSCORE = re.compile(r"_(\d+(?:\.\d+)?)(?=\D|$)")


@dataclass(frozen=True)
class NumberedChapter:
    number: Decimal
    title: str | None
    entries: list[PdfEntry]


@dataclass(frozen=True)
class ReadVolume:
    volume: Decimal | None
    edition: Edition
    chapters: list[NumberedChapter]
    cover: bytes | None


def _plain(value: str) -> Decimal:
    # normalize() alone turns 10 into 1E+1, which a file name spells literally.
    number = Decimal(value)
    return number.quantize(Decimal(1)) if number == number.to_integral() else number.normalize()


def volume_from_filename(name: str) -> Decimal | None:
    match = _VOLUME_WORD.search(name) or _UNDERSCORE.search(name)
    return _plain(match.group(1)) if match else None


def _edition(
    name: str, producer: str | None, first: Decimal | None, known_max: Decimal | None
) -> Edition:
    # The user's own label beats anything read from the content.
    prefix = _PREFIX.match(name)
    if prefix:
        return "light" if prefix.group(1).upper() == "LN" else "web"
    restarts = first == 1
    if restarts and known_max is not None and known_max > 1:
        return "light"
    if restarts and producer and producer.lower().startswith("calibre"):
        return "light"
    return "web"


def number_book(book: PdfBook, filename: str, *, known_max: Decimal | None) -> ReadVolume:
    chapters: list[NumberedChapter] = []
    pending: list[PdfEntry] = []
    cover: bytes | None = None
    last_main = Decimal(0)
    last_prologue = Decimal(0)
    sides = 0
    first: Decimal | None = None

    for entry in book.entries:
        if _FRONT_MATTER.match(entry.title):
            if cover is None and entry.title.strip().lower().startswith("cover") and entry.images:
                cover = entry.images[0]
            pending.append(entry)
            continue

        title: str | None
        if match := _CHAPTER.match(entry.title):
            number = _plain(match.group(1))
            title = match.group(2).strip() or None
            last_main, sides = number, 0
            if first is None:
                first = number
        elif match := _PROLOGUE.match(entry.title):
            number = Decimal(f"0.{match.group(1)}")
            title = match.group(2).strip() or None
            last_main = last_prologue = number
            sides = 0
        elif _UNNUMBERED_PROLOGUE.match(entry.title):
            number = last_prologue + Decimal("0.1")
            title = entry.title.strip()
            last_main = last_prologue = number
            sides = 0
        else:
            number = last_main + Decimal("0.5") + Decimal("0.1") * sides
            title = entry.title.strip()
            sides += 1

        chapters.append(NumberedChapter(number=number, title=title, entries=[*pending, entry]))
        pending = []

    if pending and chapters:
        last = chapters[-1]
        chapters[-1] = NumberedChapter(last.number, last.title, [*last.entries, *pending])

    return ReadVolume(
        volume=volume_from_filename(filename),
        edition=_edition(filename, book.producer, first, known_max),
        chapters=chapters,
        cover=cover,
    )
