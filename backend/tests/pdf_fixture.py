"""Builds small text PDFs with bookmarks, the shape of a novel compiled in Word.

The importer reads what a real compilation has: a bookmark per chapter, text a
PDF reader can extract, and nothing else it can rely on. Pages are drawn with a
hand-written content stream so no PDF-writing dependency joins the image.
"""

import io

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

Entry = tuple[str | None, list[str]]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content(text: str) -> bytes:
    lines = text.split("\n")
    ops = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            ops.append("T*")
        ops.append(f"({_escape(line)}) Tj")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def make_pdf(
    entries: list[Entry], *, nested_under: str | None = None, producer: str = "Microsoft Word"
) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)

    starts: list[tuple[str, int]] = []
    for title, pages in entries:
        if title is not None:
            starts.append((title, len(writer.pages)))
        for text in pages:
            page = writer.add_blank_page(width=612, height=792)
            stream = DecodedStreamObject()
            stream.set_data(_content(text))
            page[NameObject("/Contents")] = ArrayObject([writer._add_object(stream)])
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
            )

    parent = None
    if nested_under is not None:
        parent = writer.add_outline_item(nested_under, starts[0][1] if starts else 0)
    for title, page_number in starts:
        writer.add_outline_item(title, page_number, parent=parent)

    writer.add_metadata({"/Producer": producer})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
