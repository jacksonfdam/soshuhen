"""Where a volume lives on disk, and how a downloaded one is recognised."""

import io
import zipfile
from decimal import Decimal
from pathlib import Path

from app.downloader.epub import is_epub
from app.downloader.paths import (
    number_from_filename,
    volume_filename,
    volume_number_from_filename,
    volume_path,
)


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def test_a_volume_is_named_apart_from_its_chapters():
    assert volume_filename("apothecary", Decimal(16), "Volume 16") == (
        "apothecary - Vol.0016 - Volume 16.epub"
    )
    assert volume_filename("apothecary", Decimal(3)) == "apothecary - Vol.0003.epub"
    assert volume_path(Path("/m"), "apothecary", Decimal(3)) == Path(
        "/m/apothecary/apothecary - Vol.0003.epub"
    )


def test_volume_numbers_read_back_and_never_as_chapters():
    name = volume_filename("apothecary", Decimal(16), "Volume 16")
    assert volume_number_from_filename(name) == Decimal(16)
    assert number_from_filename(name) is None
    assert volume_number_from_filename("apothecary - Ch.0016.epub") is None


def test_an_epub_is_recognised_by_its_container():
    good = _zip([("mimetype", b"application/epub+zip"), ("OEBPS/content.opf", b"<x/>")])
    assert is_epub(good)


def test_an_html_page_is_not_an_epub():
    assert not is_epub(b"<!DOCTYPE html><html>Link expired</html>")


def test_a_zip_without_the_mimetype_first_is_not_an_epub():
    assert not is_epub(_zip([("OEBPS/content.opf", b"<x/>")]))
    assert not is_epub(_zip([("OEBPS/a", b"x"), ("mimetype", b"application/epub+zip")]))
    assert not is_epub(_zip([("mimetype", b"application/zip")]))


def test_a_chapter_title_mentioning_a_volume_is_not_a_volume():
    # A chapter titled "Vol.3 Extra Story" must never be adopted as volume 3:
    # the scan would lock it as "Vol. 3" and a revision would delete it.
    name = "mushoku - Ch.0012 - Vol.3 Extra Story.epub"
    assert volume_number_from_filename(name) is None
    assert volume_number_from_filename("mushoku - Vol.0003 - Ch.5 notes.epub") == Decimal(3)
    # ...and the reverse: a volume titled with "Ch.5" is never chapter 5.
    assert number_from_filename("mushoku - Vol.0003 - Ch.5 notes.epub") is None
