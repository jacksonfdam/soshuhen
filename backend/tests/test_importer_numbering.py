"""Numbering a PDF's entries, and telling a web novel volume from a light novel one.

The web novel numbers its chapters across the whole work, so its numbers are
the chapter numbers as they come. The light novel restarts at 1 every volume
and rewrites the web chapters, so its numbers say nothing outside the volume.
"""

from decimal import Decimal

import pytest

from app.importer.numbering import number_book, volume_from_filename
from app.importer.pdf import PdfBook, PdfEntry


def book(*titles: str, producer: str | None = "Microsoft Word", images=None) -> PdfBook:
    images = images or {}
    return PdfBook(
        producer=producer,
        entries=[PdfEntry(title=t, pages=[f"text of {t}"], images=images.get(t, [])) for t in titles],
    )


def numbers(volume) -> list[Decimal]:
    return [chapter.number for chapter in volume.chapters]


def test_web_volume_one_numbers_prologues_and_pov():
    chapters = [f"Chapter {n}" for n in range(1, 10)]
    read = number_book(
        book(
            "Cover", "Characters", "Prologue 1", "Prologue 2", "Prologue 3", "Prologue POV",
            *chapters, "POV Chapter", "Chapter 10",
        ),
        "WN - Tsukimichi - Volume 01.pdf",
        known_max=None,
    )

    assert numbers(read) == [
        Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4"),
        *[Decimal(n) for n in range(1, 10)], Decimal("9.5"), Decimal(10),
    ]
    assert [e.title for e in read.chapters[0].entries] == ["Cover", "Characters", "Prologue 1"]
    assert read.edition == "web"
    assert read.volume == Decimal(1)


def test_two_side_entries_after_one_chapter_take_5_then_6():
    read = number_book(
        book("Chapter 26", "POV Chapter", "Side Story", "Chapter 27"), "x_02.pdf", known_max=None
    )

    assert numbers(read) == [Decimal(26), Decimal("26.5"), Decimal("26.6"), Decimal(27)]


def test_chapter_title_is_the_text_after_the_number():
    read = number_book(book("Chapter 213 Today Kuzunoha leaves"), "x_15.pdf", known_max=None)

    assert read.chapters[0].title == "Today Kuzunoha leaves"


def test_a_side_entry_keeps_its_whole_bookmark_as_title():
    read = number_book(book("Chapter 9", "POV Chapter: Tomoe"), "x_01.pdf", known_max=None)

    assert read.chapters[1].title == "POV Chapter: Tomoe"


def test_front_matter_is_never_a_chapter_and_its_image_is_the_cover():
    read = number_book(
        book("Cover", "Map", "Chapter 134", images={"Cover": [b"cover-bytes"]}),
        "x_08.pdf",
        known_max=None,
    )

    assert numbers(read) == [Decimal(134)]
    assert read.cover == b"cover-bytes"


def test_restart_at_one_after_higher_known_chapters_is_light():
    read = number_book(book("Chapter 1", "Chapter 2"), "x - Volume 19.pdf", known_max=Decimal(295))

    assert read.edition == "light"


def test_first_volume_starting_at_one_is_web():
    read = number_book(book("Chapter 1", "Chapter 2"), "x_01.pdf", known_max=None)

    assert read.edition == "web"


def test_calibre_book_restarting_at_one_is_light():
    read = number_book(
        book("Chapter 1", "Chapter 2", producer="calibre 3.48.0"), "x - Volume 19.pdf", known_max=None
    )

    assert read.edition == "light"


def test_filename_prefix_decides_the_edition():
    light = number_book(
        book("Chapter 1", "Chapter 2"), "LN - Tsukimichi - Volume 01.pdf", known_max=None
    )
    web = number_book(
        book("Chapter 1", "Chapter 2"), "WN - Tsukimichi - Volume 03.pdf", known_max=Decimal(295)
    )

    assert light.edition == "light"
    assert web.edition == "web"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Tsuki ga Michibiku Isekai Douchuu_01.pdf", Decimal(1)),
        ("Tsuki ga Michibiku Isekai Douchuu_12_(v2).pdf", Decimal(12)),
        ("Tsuki ga Michibiku Isekai Douchuu_15 (Chapter 213-231).pdf", Decimal(15)),
        ("Tsukimichi Moonlit Fantasy - Volume 19.pdf", Decimal(19)),
        ("WN - Tsukimichi Moonlit Fantasy - Tsuki ga Michibiku Isekai Dochu - Volume 07.pdf", Decimal(7)),
        ("Some Series Vol. 8.5.pdf", Decimal("8.5")),
        ("notes.pdf", None),
    ],
)
def test_volume_from_filename(name, expected):
    assert volume_from_filename(name) == expected


def test_round_numbers_never_read_as_exponents():
    # Decimal("10").normalize() is 1E+1, which a file name would spell literally.
    read = number_book(book("Chapter 80", "Chapter 100"), "x - Volume 10.pdf", known_max=None)

    assert [str(n) for n in numbers(read)] == ["80", "100"]
    assert str(read.volume) == "10"


def test_entries_before_the_first_chapter_are_front_matter():
    # "Table of Contents" as 0.5 in every volume would make the second volume
    # collide with the first and be refused, with nothing the user could edit.
    read = number_book(
        book("Table of Contents", "Chapter 27", "Chapter 28"), "x_02.pdf", known_max=None
    )

    assert numbers(read) == [Decimal(27), Decimal(28)]
    assert [e.title for e in read.chapters[0].entries] == ["Table of Contents", "Chapter 27"]


def test_an_unnumbered_prologue_after_numbered_ones_still_counts():
    read = number_book(
        book("Prologue 1", "Prologue POV", "Chapter 1"), "x_01.pdf", known_max=None
    )

    assert numbers(read) == [Decimal("0.1"), Decimal("0.2"), Decimal(1)]
