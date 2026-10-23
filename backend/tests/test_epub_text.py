"""Reading an EPUB's sections, and making them safe to put in the interface's DOM."""

import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from app.downloader.epub import EpubChapter, write_epub
from app.reader import epub_text

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)

CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)


def _xhtml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>t</title><style>body{{color:red}}</style></head><body>{body}</body></html>"
    )


def _book(path: Path, *, nav: bool, sections: dict[str, str]) -> Path:
    """An EPUB laid out the way other tools write them: content in a subfolder,
    sections in their own folder, images in a sibling one."""
    manifest = [
        f'<item id="s{i}" href="text/{name}" media-type="application/xhtml+xml"/>'
        for i, name in enumerate(sections)
    ]
    manifest.append('<item id="img" href="images/a.png" media-type="image/png"/>')
    manifest.append('<item id="css" href="style.css" media-type="text/css"/>')
    if nav:
        manifest.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
    else:
        manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    spine = "".join(f'<itemref idref="s{i}"/>' for i in range(len(sections)))
    if nav:
        spine = '<itemref idref="nav" linear="no"/>' + spine
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f"<metadata/><manifest>{''.join(manifest)}</manifest>"
        f'<spine{"" if nav else " toc=\"ncx\""}>{spine}</spine></package>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OPS/book.opf", opf)
        archive.writestr("OPS/images/a.png", PNG)
        archive.writestr("OPS/style.css", "p{}")
        archive.writestr("secret.txt", "not for you")
        for name, body in sections.items():
            archive.writestr(f"OPS/text/{name}", _xhtml(body))
        if nav:
            archive.writestr(
                "OPS/nav.xhtml",
                _xhtml(
                    '<nav epub:type="toc"><ol>'
                    '<li><a href="text/one.xhtml">Prologue</a></li>'
                    '<li><a href="text/two.xhtml#start">Chapter 1</a></li>'
                    "</ol></nav>"
                ),
            )
        else:
            archive.writestr(
                "OPS/toc.ncx",
                '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
                '<navPoint id="a"><navLabel><text>Prologue</text></navLabel>'
                '<content src="text/one.xhtml"/></navPoint>'
                '<navPoint id="b"><navLabel><text>Chapter 1</text></navLabel>'
                '<content src="text/two.xhtml"/></navPoint>'
                "</navMap></ncx>",
            )
    return path


def _url(href: str) -> str:
    return f"/res/{href}"


def test_sections_follow_the_spine_with_nav_titles(tmp_path):
    path = _book(tmp_path / "b.epub", nav=True, sections={"one.xhtml": "<p>a</p>",
                                                          "two.xhtml": "<p>b</p>"})
    assert epub_text.sections(path) == [
        epub_text.Section(0, "Prologue", "OPS/text/one.xhtml"),
        epub_text.Section(1, "Chapter 1", "OPS/text/two.xhtml"),
    ]


def test_ncx_titles_when_there_is_no_nav(tmp_path):
    path = _book(tmp_path / "b.epub", nav=False, sections={"one.xhtml": "<p>a</p>",
                                                           "two.xhtml": "<p>b</p>"})
    assert [s.title for s in epub_text.sections(path)] == ["Prologue", "Chapter 1"]


async def test_written_chapter_epub_has_one_section(tmp_path):
    path = tmp_path / "c.epub"
    await write_epub(
        EpubChapter(
            series="S", number=Decimal(3), identifier="id", title="The Road",
            body="<p>Hello <em>there</em>.</p>{{img:0}}", images=[PNG], cover=None,
        ),
        path,
    )
    [section] = epub_text.sections(path)
    html = epub_text.section_html(path, 0, _url)
    assert "<p>Hello <em>there</em>.</p>" in html
    assert '<img src="/res/OEBPS/images/001.png" alt="">' in html
    assert section.index == 0


def test_script_and_handlers_are_removed(tmp_path):
    body = (
        '<p onclick="steal()" style="position:fixed" class="x">Text<script>alert(1)</script></p>'
        '<a href="javascript:alert(2)">link</a><iframe src="https://evil"></iframe>'
        "<svg><text>drawn</text></svg><custom-tag>kept text</custom-tag>"
    )
    path = _book(tmp_path / "b.epub", nav=True, sections={"one.xhtml": body})
    html = epub_text.section_html(path, 0, _url)
    assert html == "<p>Text</p><a>link</a>kept text"


def test_remote_and_escaping_images_are_dropped(tmp_path):
    body = (
        '<img src="https://evil.example/x.png"/><img src="../../../secret.txt"/>'
        '<img src="data:image/png;base64,AAAA"/><p>after</p>'
    )
    path = _book(tmp_path / "b.epub", nav=True, sections={"one.xhtml": body})
    assert epub_text.section_html(path, 0, _url) == "<p>after</p>"


def test_local_images_point_at_the_resource_route(tmp_path):
    body = '<figure><img src="../images/a.png" alt="Map" width="9"/></figure>'
    path = _book(tmp_path / "b.epub", nav=True, sections={"one.xhtml": body})
    html = epub_text.section_html(path, 0, _url)
    assert html == '<figure><img src="/res/OPS/images/a.png" alt="Map"></figure>'


def test_resource_refuses_non_images_and_unknown_hrefs(tmp_path):
    path = _book(tmp_path / "b.epub", nav=True, sections={"one.xhtml": "<p>a</p>"})
    assert epub_text.resource(path, "OPS/images/a.png") == (PNG, "image/png")
    for href in ("OPS/style.css", "secret.txt", "OPS/../secret.txt", "OPS/images/missing.png"):
        with pytest.raises(KeyError):
            epub_text.resource(path, href)


def test_a_bad_section_index_is_an_index_error(tmp_path):
    path = _book(tmp_path / "b.epub", nav=True, sections={"one.xhtml": "<p>a</p>"})
    with pytest.raises(IndexError):
        epub_text.section_html(path, 5, _url)


def test_broken_zip_raises_epub_broken(tmp_path):
    path = tmp_path / "broken.epub"
    path.write_bytes(b"not a zip")
    with pytest.raises(epub_text.EpubBroken):
        epub_text.sections(path)
