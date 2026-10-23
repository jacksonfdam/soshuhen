"""One entry per bookmark, with the text and images of the pages it spans."""

import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnreadablePdf(Exception):
    """A file the import cannot split into chapters: not a PDF, no bookmarks, or no text.

    A scanned book has pages but no text, and a PDF without bookmarks has text
    but no chapters; importing either would make one unreadable giant chapter.
    """


@dataclass(frozen=True)
class PdfEntry:
    title: str
    pages: list[str]
    images: list[bytes]


@dataclass(frozen=True)
class PdfBook:
    producer: str | None
    entries: list[PdfEntry]


def _flatten(reader: PdfReader, outline) -> list[tuple[str, int]]:
    marks: list[tuple[str, int]] = []
    items = list(outline)
    for index, item in enumerate(items):
        if isinstance(item, list):
            marks.extend(_flatten(reader, item))
            continue
        # A bookmark whose children follow it is a container, a volume heading
        # over its chapters; the chapters are the entries.
        if index + 1 < len(items) and isinstance(items[index + 1], list):
            continue
        page = reader.get_destination_page_number(item)
        if page is not None and page >= 0:
            marks.append((str(item.title).strip(), page))
    return marks


def _images(page) -> list[bytes]:
    try:
        return [image.data for image in page.images]
    except Exception:  # noqa: BLE001 - a broken image must not lose the chapter's text
        return []


def read_pdf(data: bytes) -> PdfBook:
    try:
        reader = PdfReader(io.BytesIO(data))
        outline = reader.outline
    except (PdfReadError, ValueError, OSError) as exc:
        raise UnreadablePdf(f"not a readable PDF: {exc}") from exc

    marks = sorted(_flatten(reader, outline), key=lambda mark: mark[1])
    # Bookmarks sharing a page: only the last one owns any text.
    by_page: dict[int, str] = {}
    for title, page in marks:
        by_page[page] = title
    starts = sorted(by_page.items())
    if not starts:
        raise UnreadablePdf("the PDF has no bookmarks to split chapters by")

    texts = [page.extract_text() or "" for page in reader.pages]
    if not any(text.strip() for text in texts):
        raise UnreadablePdf("the PDF has no text; a scanned book cannot be imported")

    entries: list[PdfEntry] = []
    for index, (first, title) in enumerate(starts):
        last = starts[index + 1][0] if index + 1 < len(starts) else len(reader.pages)
        span = range(first, last)
        entries.append(
            PdfEntry(
                title=title,
                pages=[texts[number] for number in span],
                images=[image for number in span for image in _images(reader.pages[number])],
            )
        )

    producer = (reader.metadata or {}).get("/Producer")
    return PdfBook(producer=str(producer) if producer else None, entries=entries)
