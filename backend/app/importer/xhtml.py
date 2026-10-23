"""Page text into the XHTML body write_epub takes.

Extracted text keeps the page's line breaks and its furniture - page numbers,
the title repeated at the top of every page. Joining lines back into paragraphs
and dropping that furniture is what makes it read like a book again.
"""

import re
from collections import Counter
from xml.sax.saxutils import escape

from app.importer.pdf import PdfEntry

_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d+\s*$", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SENTENCE_END = re.compile(r"[.!?…\"'”’)\]]$")
_STARTS_NEW = re.compile(r"^[A-Z\"'“‘(\[—–-]")


def _furniture(pages: list[list[str]]) -> set[str]:
    """Lines at the top or bottom of most pages: running headers and footers."""
    if len(pages) < 3:
        return set()
    edges = Counter()
    for lines in pages:
        content = [line for line in lines if line.strip()]
        if content:
            edges.update({content[0].strip(), content[-1].strip()})
    return {line for line, count in edges.items() if count * 2 >= len(pages)}


def _paragraphs(pages: list[str]) -> list[str]:
    split = [_CONTROL.sub("", page).strip().split("\n") for page in pages]
    furniture = _furniture(split)
    paragraphs: list[str] = []
    current = ""
    for lines in split:
        # A page break is not a paragraph break: sentences run across pages.
        for raw in lines:
            line = raw.strip()
            if not line:
                if current:
                    paragraphs.append(current)
                    current = ""
                continue
            if line in furniture or _PAGE_NUMBER.match(line):
                continue
            if current and _SENTENCE_END.search(current) and _STARTS_NEW.match(line):
                paragraphs.append(current)
                current = line
            else:
                current = f"{current} {line}" if current else line
    if current:
        paragraphs.append(current)
    return paragraphs


def _text(value: str) -> str:
    # A literal {{img:N}} in the prose would be taken for an image reference.
    return escape(value.replace("{{", "{\u200b{"))


def entries_to_body(entries: list[PdfEntry], *, own_heading: bool = True) -> tuple[str, list[bytes]]:
    """The body and its images, in order. Without own_heading the last entry gets no
    heading, because write_epub already heads the chapter with its title."""
    parts: list[str] = []
    images: list[bytes] = []
    for index, entry in enumerate(entries):
        if own_heading or index < len(entries) - 1:
            parts.append(f"<h2>{_text(entry.title)}</h2>")
        for image in entry.images:
            parts.append(f"<p>{{{{img:{len(images)}}}}}</p>")
            images.append(image)
        parts.extend(f"<p>{_text(paragraph)}</p>" for paragraph in _paragraphs(entry.pages))
    return "".join(parts), images
