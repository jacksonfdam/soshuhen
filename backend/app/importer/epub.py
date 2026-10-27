"""An EPUB in a drop is one light novel volume, kept exactly as it came.

Its own markup, cover and table of contents are what every reader opens, so
nothing is extracted or rebuilt; the only question is which volume it is. The
file name answers first, as it does for a PDF, and the package's series index
- what Calibre writes - answers when the name carries no number.
"""

import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, InvalidOperation

from app.downloader.epub import is_epub
from app.importer.numbering import ReadVolume, volume_from_filename
from app.importer.pdf import UnreadablePdf

_CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}


def _series_index(archive: zipfile.ZipFile) -> Decimal | None:
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    rootfile = container.find(".//c:rootfile", _CONTAINER_NS)
    if rootfile is None:
        return None
    package = ET.fromstring(archive.read(posixpath.normpath(rootfile.get("full-path", ""))))
    for meta in package.iterfind(".//opf:metadata/opf:meta", _OPF_NS):
        # Calibre's EPUB 2 attribute, and EPUB 3's collection position.
        if meta.get("name") == "calibre:series_index":
            value = meta.get("content")
        elif meta.get("property") == "group-position":
            value = meta.text
        else:
            continue
        try:
            number = Decimal((value or "").strip())
        except InvalidOperation:
            continue
        if number.is_finite() and number > 0:
            return number.quantize(Decimal(1)) if number == number.to_integral() else number.normalize()
    return None


def read_epub(data: bytes, filename: str) -> ReadVolume:
    if not is_epub(data):
        raise UnreadablePdf("not an EPUB: a zip without the EPUB mimetype entry")
    volume = volume_from_filename(filename)
    if volume is None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                volume = _series_index(archive)
        except (KeyError, ET.ParseError, zipfile.BadZipFile, ValueError):
            volume = None
    return ReadVolume(volume=volume, edition="light", chapters=[], cover=None, whole_file=True)


def looks_like_epub(name: str, data: bytes) -> bool:
    return data[:2] == b"PK" or bool(re.search(r"\.epub$", name, re.IGNORECASE))
