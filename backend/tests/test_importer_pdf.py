"""Reading a novel PDF into one entry per bookmark.

A bookmark is the only structure a compiled novel reliably carries: the text
itself has no markup, and headings are just larger type. Everything the import
does downstream trusts these ranges, so a wrong range is a chapter that starts
in the middle of another.
"""

import pytest

from app.importer.pdf import UnreadablePdf, read_pdf
from tests.pdf_fixture import make_pdf


def test_one_entry_per_bookmark_with_its_page_range():
    data = make_pdf([("Cover", ["c"]), ("Chapter 1", ["a", "b"]), ("Chapter 2", ["d"])])

    book = read_pdf(data)

    assert [e.title for e in book.entries] == ["Cover", "Chapter 1", "Chapter 2"]
    assert [len(e.pages) for e in book.entries] == [1, 2, 1]
    assert "b" in book.entries[1].pages[1]


def test_nested_bookmarks_read_like_flat_ones():
    data = make_pdf([("Chapter 1", ["a"]), ("Chapter 2", ["b"])], nested_under="Volume 3")

    book = read_pdf(data)

    assert [e.title for e in book.entries] == ["Chapter 1", "Chapter 2"]
    assert [len(e.pages) for e in book.entries] == [1, 1]


def test_bookmarks_sharing_a_page_keep_the_last():
    # Two bookmarks on one page: the first would be an empty chapter.
    data = make_pdf([("Characters", []), ("Chapter 1", ["a"]), ("Chapter 2", ["b"])])

    book = read_pdf(data)

    assert [e.title for e in book.entries] == ["Chapter 1", "Chapter 2"]


def test_bookmarks_out_of_order_are_sorted_by_page():
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    source = make_pdf([(None, ["a", "b", "c"])])
    writer = PdfWriter(clone_from=PdfReader(BytesIO(source)))
    writer.add_outline_item("Chapter 2", 2)
    writer.add_outline_item("Chapter 1", 0)
    out = BytesIO()
    writer.write(out)

    book = read_pdf(out.getvalue())

    assert [e.title for e in book.entries] == ["Chapter 1", "Chapter 2"]
    assert [len(e.pages) for e in book.entries] == [2, 1]


def test_pages_before_the_first_bookmark_are_dropped():
    data = make_pdf([(None, ["front"]), ("Chapter 1", ["a"])])

    book = read_pdf(data)

    assert len(book.entries) == 1
    assert "front" not in book.entries[0].pages[0]


def test_no_bookmarks_is_unreadable():
    with pytest.raises(UnreadablePdf):
        read_pdf(make_pdf([(None, ["a", "b"])]))


def test_no_text_is_unreadable():
    with pytest.raises(UnreadablePdf):
        read_pdf(make_pdf([("Chapter 1", [""]), ("Chapter 2", [""])]))


def test_not_a_pdf_is_unreadable():
    with pytest.raises(UnreadablePdf):
        read_pdf(b"not a pdf at all")


def test_producer_is_read():
    data = make_pdf([("Chapter 1", ["a"])], producer="calibre 3.48.0")

    assert read_pdf(data).producer.startswith("calibre")
