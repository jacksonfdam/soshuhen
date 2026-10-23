"""The PDF builder the importer's tests stand on.

The user's own PDFs are copyrighted and never enter the repository, so every
importer test builds its input here; a builder whose text pypdf cannot read back
would make every one of them pass or fail for the wrong reason.
"""

import io

from pypdf import PdfReader

from tests.pdf_fixture import make_pdf


def test_fixture_round_trips_titles_and_text():
    data = make_pdf([("Cover", ["x"]), ("Chapter 1 Start", ["one", "two"])])

    reader = PdfReader(io.BytesIO(data))

    assert len(reader.pages) == 3
    assert [item.title for item in reader.outline] == ["Cover", "Chapter 1 Start"]
    assert "two" in reader.pages[2].extract_text()


def test_fixture_nests_bookmarks_under_one_parent():
    data = make_pdf([("Chapter 1", ["a"]), ("Chapter 2", ["b"])], nested_under="Volume 3")

    outline = PdfReader(io.BytesIO(data)).outline

    assert outline[0].title == "Volume 3"
    assert [item.title for item in outline[1]] == ["Chapter 1", "Chapter 2"]
