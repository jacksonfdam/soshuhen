"""Builds minimal EPUB containers, the shape a publisher's or Calibre's volume has.

Only what the import reads: the mimetype entry first and stored, a container
pointing at the package, and the package's series metadata.
"""

import io
import zipfile


def make_epub(*, title: str = "A Volume", series_index: str | None = None) -> bytes:
    meta = f"<dc:title>{title}</dc:title>"
    if series_index is not None:
        meta += f'<meta name="calibre:series_index" content="{series_index}"/>'
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="id">fixture</dc:identifier>{meta}</metadata>'
        '<manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c"/></spine></package>'
    )
    container = (
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/c.xhtml", "<html><body><p>Text.</p></body></html>")
    return out.getvalue()
