"""An EPUB in a drop: one light novel volume, placed in the library as it is.

A publisher's or Calibre's EPUB is already the book the readers open, so it is
never split or rebuilt. All the import decides is which volume it is.
"""

from decimal import Decimal

from app.downloader.paths import volume_filename
from app.importer.plan import Existing, Override, plan_import
from app.importer.reading import read_files, sha256_of
from tests.epub_fixture import make_epub

NOTHING = Existing(chapters=frozenset(), volumes=frozenset())


def read_one(name: str, data: bytes):
    [(_, _, read)] = read_files([(name, sha256_of(data), data)], known_max=None)
    return read


def test_an_epub_is_a_whole_light_volume_numbered_from_its_name():
    read = read_one("LN - Tsukimichi - Volume 03.epub", make_epub())

    assert (read.volume, read.edition, read.whole_file) == (Decimal(3), "light", True)
    assert read.chapters == []


def test_an_epub_without_a_number_in_its_name_takes_calibres_series_index():
    read = read_one("Tsukimichi.epub", make_epub(series_index="4.0"))

    assert read.volume == Decimal(4)


def test_an_epub_is_light_even_when_its_name_says_wn():
    # It is placed as one book; a web novel volume is a range of chapter files.
    read = read_one("WN - Tsukimichi - Volume 02.epub", make_epub())

    assert read.edition == "light"


def test_an_epub_plans_one_volume_file():
    data = make_epub()
    files = read_files([("LN - T - Volume 05.epub", sha256_of(data), data)], known_max=None)

    [planned] = plan_import("t", files, NOTHING, {})

    assert planned.status == "ready"
    assert planned.outputs == [volume_filename("t", Decimal(5))]


def test_an_epub_overridden_to_web_is_a_conflict():
    data = make_epub()
    sha = sha256_of(data)
    files = read_files([("LN - T - Volume 05.epub", sha, data)], known_max=None)

    [planned] = plan_import("t", files, NOTHING, {sha: Override(edition="web")})

    assert planned.status == "conflict"
    assert "whole" in planned.reason


def test_a_zip_that_is_not_an_epub_is_unreadable():
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("notes.txt", "hi")

    assert read_one("notes.epub", out.getvalue()) is None
