"""Turn one prose chapter into the EPUB 3 file Komga reads.

Hand-rolled, like the CBZ writer: the package is five small files, and every
field written here was chosen from what Komga's own EpubMetadataProvider and
EpubExtractor read (gotson/komga, verified 2026-10-14) - title, creator,
description, language, belongs-to-collection with group-position for the
series and number, and the manifest item marked cover-image for the
thumbnail.
"""

import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from app.downloader.cbz import page_extension, place_file

_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
}
_PLACEHOLDER = re.compile(r"\{\{img:(\d+)\}\}")

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass
class EpubChapter:
    series: str
    number: Decimal
    identifier: str
    title: str | None
    body: str
    images: list[bytes]
    cover: bytes | None
    language: str = "en"
    authors: list[str] = field(default_factory=list)
    summary: str | None = None

    @property
    def full_title(self) -> str:
        name = f"{self.series} - Chapter {_number(self.number)}"
        return f"{name}: {self.title}" if self.title else name


async def write_epub(chapter: EpubChapter, destination: Path) -> None:
    """Build the package in a scratch file and rename it into place.

    Komga scans on a schedule and on demand, and a half-written zip it indexes
    becomes a broken book in the library - so the destination only ever holds
    a complete file, exactly as with write_cbz.
    """
    files = _package(chapter)

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, scratch_name = tempfile.mkstemp(dir=destination.parent, suffix=".epub.part")
    os.close(handle)
    scratch = Path(scratch_name)
    try:
        with zipfile.ZipFile(scratch, "w") as archive:
            # First and stored: the OCF spec requires it, and readers find the
            # format by reading those bytes at a fixed offset.
            archive.writestr(
                zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED
            )
            for name, data, compress in files:
                archive.writestr(name, data, compress)
        await place_file(scratch, destination)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise


def _package(chapter: EpubChapter) -> list[tuple[str, bytes, int]]:
    image_names: list[str] = []
    files: list[tuple[str, bytes, int]] = []
    for index, data in enumerate(chapter.images, start=1):
        name = f"images/{index:03d}.{page_extension(data)}"
        image_names.append(name)
        # Already compressed formats; deflating them spends CPU for nothing.
        files.append((f"OEBPS/{name}", data, zipfile.ZIP_STORED))

    cover_name = None
    if chapter.cover is not None:
        cover_name = f"images/cover.{page_extension(chapter.cover)}"
        files.append((f"OEBPS/{cover_name}", chapter.cover, zipfile.ZIP_STORED))

    body = _resolve_images(chapter.body, image_names)
    files.append(("META-INF/container.xml", CONTAINER.encode(), zipfile.ZIP_DEFLATED))
    files.append(
        ("OEBPS/chapter.xhtml", _chapter_xhtml(chapter, body).encode(), zipfile.ZIP_DEFLATED)
    )
    files.append(("OEBPS/nav.xhtml", _nav(chapter).encode(), zipfile.ZIP_DEFLATED))
    files.append(
        ("OEBPS/content.opf", _opf(chapter, image_names, cover_name).encode(),
         zipfile.ZIP_DEFLATED)
    )
    return files


def _resolve_images(body: str, image_names: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index >= len(image_names):
            # Shipping the chapter without the image would look like a working
            # download with a hole in it, the same failure write_cbz refuses.
            raise ValueError(f"chapter body references image {index}, which was not fetched")
        return f'<img src="{image_names[index]}" alt=""/>'

    return _PLACEHOLDER.sub(replace, body)


def _chapter_xhtml(chapter: EpubChapter, body: str) -> str:
    heading = escape(chapter.title or f"Chapter {_number(chapter.number)}")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang={quoteattr(chapter.language)}>\n'
        f"<head><meta charset=\"utf-8\"/><title>{escape(chapter.full_title)}</title></head>\n"
        f"<body><section><h2>{heading}</h2>{body}</section></body>\n"
        "</html>\n"
    )


def _nav(chapter: EpubChapter) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f"<head><meta charset=\"utf-8\"/><title>{escape(chapter.full_title)}</title></head>\n"
        '<body><nav epub:type="toc"><ol>'
        f'<li><a href="chapter.xhtml">{escape(chapter.full_title)}</a></li>'
        "</ol></nav></body>\n"
        "</html>\n"
    )


def _opf(chapter: EpubChapter, image_names: list[str], cover_name: str | None) -> str:
    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = [
        f'<dc:identifier id="book-id">{escape(chapter.identifier)}</dc:identifier>',
        f"<dc:title>{escape(chapter.full_title)}</dc:title>",
        f"<dc:language>{escape(chapter.language)}</dc:language>",
        *(f"<dc:creator>{escape(author)}</dc:creator>" for author in chapter.authors),
        *(
            [f"<dc:description>{escape(chapter.summary)}</dc:description>"]
            if chapter.summary
            else []
        ),
        f'<meta property="dcterms:modified">{modified}</meta>',
        f'<meta property="belongs-to-collection" id="series">{escape(chapter.series)}</meta>',
        '<meta refines="#series" property="collection-type">series</meta>',
        f'<meta refines="#series" property="group-position">{_number(chapter.number)}</meta>',
    ]
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
    ]
    for index, name in enumerate(image_names, start=1):
        media_type = _MEDIA_TYPES[name.rsplit(".", 1)[1]]
        manifest.append(f'<item id="img{index:03d}" href="{name}" media-type="{media_type}"/>')
    if cover_name is not None:
        media_type = _MEDIA_TYPES[cover_name.rsplit(".", 1)[1]]
        manifest.append(
            f'<item id="cover" href="{cover_name}" media-type="{media_type}" '
            'properties="cover-image"/>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="book-id">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        + "\n".join(metadata)
        + "\n</metadata>\n<manifest>\n"
        + "\n".join(manifest)
        + '\n</manifest>\n<spine><itemref idref="chapter"/></spine>\n</package>\n'
    )


def _number(number: Decimal) -> str:
    integral = int(number)
    return str(integral) if number == integral else format(number.normalize(), "f")
