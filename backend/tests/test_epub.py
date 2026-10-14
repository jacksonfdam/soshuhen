"""write_epub produces the EPUB 3 package Komga's metadata provider reads."""

import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from app.downloader.epub import EpubChapter, write_epub

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "x": "http://www.w3.org/1999/xhtml",
}


def _chapter(**overrides) -> EpubChapter:
    values = {
        "series": "The Weakest of the Four",
        "number": Decimal("12.5"),
        "identifier": "soshuhen:7:12.5",
        "title": "A Bad Day",
        "body": "<p>Hello {{img:0}}</p><p>Bye &amp; done</p>",
        "images": [PNG],
        "cover": JPEG,
        "authors": ["Mirriad"],
        "summary": "A summary.",
    }
    values.update(overrides)
    return EpubChapter(**values)


def test_a_title_that_already_says_chapter_is_not_prefixed_twice():
    chapter = _chapter(title="Chapter 1: The Brave", number=Decimal(1))
    assert chapter.full_title == "The Weakest of the Four - Chapter 1: The Brave"
    assert _chapter(title="chapter 2").full_title == "The Weakest of the Four - chapter 2"


async def test_mimetype_comes_first_and_uncompressed(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"


async def test_every_manifest_item_exists_and_the_container_points_at_the_opf(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = container.find(".//c:rootfile", NS).get("full-path")
        assert opf_path == "OEBPS/content.opf"
        opf = ET.fromstring(archive.read(opf_path))
        names = set(archive.namelist())
        for item in opf.findall(".//opf:manifest/opf:item", NS):
            assert f"OEBPS/{item.get('href')}" in names


async def test_the_metadata_is_what_komga_reads(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
    meta = opf.find("opf:metadata", NS)
    assert meta.find("dc:title", NS).text == "The Weakest of the Four - Chapter 12.5: A Bad Day"
    assert meta.find("dc:language", NS).text == "en"
    assert meta.find("dc:creator", NS).text == "Mirriad"
    assert meta.find("dc:description", NS).text == "A summary."
    assert meta.find("dc:identifier", NS).text == "soshuhen:7:12.5"
    collection = meta.find("opf:meta[@property='belongs-to-collection']", NS)
    assert collection.text == "The Weakest of the Four"
    refines = f"#{collection.get('id')}"
    position = meta.find(f"opf:meta[@refines='{refines}'][@property='group-position']", NS)
    assert position.text == "12.5"
    kind = meta.find(f"opf:meta[@refines='{refines}'][@property='collection-type']", NS)
    assert kind.text == "series"
    assert meta.find("opf:meta[@property='dcterms:modified']", NS) is not None


async def test_the_cover_is_marked_cover_image(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
        cover = [
            item for item in opf.findall(".//opf:item", NS)
            if "cover-image" in (item.get("properties") or "")
        ]
        assert len(cover) == 1
        assert cover[0].get("href") == "images/cover.jpg"
        assert archive.read("OEBPS/images/cover.jpg") == JPEG


async def test_placeholders_become_images_and_the_chapter_parses(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(), out)
    with zipfile.ZipFile(out) as archive:
        chapter = archive.read("OEBPS/chapter.xhtml").decode()
        assert "{{img:" not in chapter
        assert 'src="images/001.png"' in chapter
        assert archive.read("OEBPS/images/001.png") == PNG
        ET.fromstring(chapter)


async def test_no_cover_means_no_cover_item(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(cover=None), out)
    with zipfile.ZipFile(out) as archive:
        assert "OEBPS/images/cover.jpg" not in archive.namelist()
        assert b"cover-image" not in archive.read("OEBPS/content.opf")


async def test_a_missing_image_fails_the_chapter_and_leaves_nothing(tmp_path):
    out = tmp_path / "a.epub"
    with pytest.raises(ValueError, match="image 0"):
        await write_epub(_chapter(images=[]), out)
    assert list(tmp_path.iterdir()) == []


async def test_a_chapter_without_a_title_is_named_by_number(tmp_path):
    out = tmp_path / "a.epub"
    await write_epub(_chapter(title=None, number=Decimal("3")), out)
    with zipfile.ZipFile(out) as archive:
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
    assert opf.find(".//dc:title", NS).text == "The Weakest of the Four - Chapter 3"
