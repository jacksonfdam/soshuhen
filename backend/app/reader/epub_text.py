"""The text of an EPUB already in the library, made safe for the web reader.

Values in, values out: a path and an index in, a list or a string out. It never
learns which chapter or volume the path belongs to.

Its output goes straight into the interface's own DOM, so a section is rebuilt
from an allowlist rather than cleaned of what is known to be dangerous. An
EPUB is the user's own file, but it was written by tools nobody here audited,
and a book that runs a script in the page that holds their library is a book
that can drive the api.
"""

import posixpath
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from selectolax.parser import HTMLParser, Node


class EpubBroken(ValueError):
    """Not a zip, or a zip without the package an EPUB must carry."""


@dataclass(frozen=True)
class Section:
    index: int
    title: str | None
    href: str


@dataclass(frozen=True)
class _Package:
    sections: tuple[Section, ...]
    images: dict[str, str]


ALLOWED = frozenset(
    ["p", "h1", "h2", "h3", "h4", "h5", "h6", "em", "i", "b", "strong", "u", "s", "small", "span", "div", "section", "blockquote", "ul", "ol", "li", "br", "hr", "img", "figure", "figcaption", "sup", "sub", "table", "thead", "tbody", "tr", "th", "td", "a"]
)
VOID = frozenset({"br", "hr", "img"})
# Removed with everything inside them. Unknown tags only lose their markup; these
# would leave behind code, styling or form chrome as if it were the book's text.
DROPPED = frozenset(
    ["script", "style", "iframe", "object", "embed", "svg", "math", "head", "noscript", "template", "form", "button", "input", "select", "textarea", "title"]
)

_OPF = "{http://www.idpf.org/2007/opf}"
_CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_NCX = "{http://www.daisy.org/z3986/2005/ncx/}"


def sections(path: Path) -> list[Section]:
    return list(_package(path, path.stat().st_mtime_ns).sections)


def section_html(path: Path, index: int, resource_url: Callable[[str], str]) -> str:
    package = _package(path, path.stat().st_mtime_ns)
    if not 0 <= index < len(package.sections):
        raise IndexError(index)
    href = package.sections[index].href
    with _open(path) as archive:
        try:
            raw = archive.read(href).decode("utf-8", errors="replace")
        except KeyError as exc:
            raise EpubBroken(f"spine names {href}, which the archive lacks") from exc
    body = HTMLParser(raw).body
    if body is None:
        return ""

    def image(src: str) -> str | None:
        resolved = _resolve(href, src)
        return resource_url(resolved) if resolved in package.images else None

    return "".join(_render(child, image) for child in body.iter(include_text=True))


def resource(path: Path, href: str) -> tuple[bytes, str]:
    """An image the package declares. Anything else is a KeyError, so a route
    serving this cannot be walked to other members of the archive."""
    package = _package(path, path.stat().st_mtime_ns)
    media_type = package.images.get(href)
    if media_type is None:
        raise KeyError(href)
    with _open(path) as archive:
        return archive.read(href), media_type


def _render(node: Node, image: Callable[[str], str | None]) -> str:
    tag = node.tag
    if tag == "-text":
        return escape(node.text(deep=False), quote=False)
    if tag in DROPPED or tag.startswith(("_", "!")):
        return ""
    inner = "".join(_render(child, image) for child in node.iter(include_text=True))
    if tag not in ALLOWED:
        return inner
    if tag == "img":
        src = image(node.attributes.get("src") or "")
        if src is None:
            return ""
        alt = node.attributes.get("alt") or ""
        return f'<img src="{escape(src)}" alt="{escape(alt)}">'
    if tag in VOID:
        return f"<{tag}>"
    return f"<{tag}>{inner}</{tag}>"


def _resolve(base: str, src: str) -> str | None:
    """The archive member a reference in `base` points at, or None for one that
    leaves the archive: a remote address, a data URI, an absolute path, or
    enough `..` to climb past the root."""
    parts = urlsplit(src)
    if parts.scheme or parts.netloc or not parts.path or parts.path.startswith("/"):
        return None
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(parts.path)))
    if joined.startswith("../") or joined == "..":
        return None
    return joined


@lru_cache(maxsize=64)
def _package(path: Path, _mtime: int) -> _Package:
    # Keyed on the modification time too: a volume re-downloaded over the same
    # name is a different book.
    with _open(path) as archive:
        try:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(f".//{_CONTAINER}rootfile")
            if rootfile is None:
                raise EpubBroken("container.xml names no package")
            opf_href = rootfile.attrib["full-path"]
            opf = ElementTree.fromstring(archive.read(opf_href))
        except (KeyError, ElementTree.ParseError) as exc:
            raise EpubBroken(f"no readable package: {exc}") from exc

        manifest: dict[str, tuple[str, str, str]] = {}
        for item in opf.iterfind(f"{_OPF}manifest/{_OPF}item"):
            resolved = _resolve(opf_href, item.attrib.get("href", ""))
            if resolved is None:
                continue
            manifest[item.attrib.get("id", "")] = (
                resolved,
                item.attrib.get("media-type", ""),
                item.attrib.get("properties", ""),
            )

        titles: dict[str, str] = {}
        nav = next((m for m in manifest.values() if "nav" in m[2].split()), None)
        if nav is not None and nav[0] in archive.namelist():
            titles = _nav_titles(nav[0], archive.read(nav[0]).decode("utf-8", errors="replace"))
        if not titles:
            spine = opf.find(f"{_OPF}spine")
            ncx = manifest.get(spine.attrib.get("toc", "") if spine is not None else "")
            if ncx is not None and ncx[0] in archive.namelist():
                titles = _ncx_titles(ncx[0], archive.read(ncx[0]))

    found: list[Section] = []
    for itemref in opf.iterfind(f"{_OPF}spine/{_OPF}itemref"):
        entry = manifest.get(itemref.attrib.get("idref", ""))
        if entry is None or itemref.attrib.get("linear") == "no" or entry is nav:
            continue
        found.append(Section(len(found), titles.get(entry[0]), entry[0]))
    images = {href: media for href, media, _ in manifest.values() if media.startswith("image/")}
    return _Package(tuple(found), images)


def _nav_titles(nav_href: str, raw: str) -> dict[str, str]:
    tree = HTMLParser(raw)
    titles: dict[str, str] = {}
    for nav in tree.css("nav"):
        if nav.attributes.get("epub:type") not in (None, "toc"):
            continue
        for link in nav.css("a"):
            target = _resolve(nav_href, (link.attributes.get("href") or "").split("#")[0])
            text = link.text(strip=True)
            if target and text:
                titles.setdefault(target, text)
        if titles:
            break
    return titles


def _ncx_titles(ncx_href: str, raw: bytes) -> dict[str, str]:
    try:
        tree = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return {}
    titles: dict[str, str] = {}
    for point in tree.iter(f"{_NCX}navPoint"):
        label = point.findtext(f"{_NCX}navLabel/{_NCX}text")
        content = point.find(f"{_NCX}content")
        if not label or content is None:
            continue
        target = _resolve(ncx_href, content.attrib.get("src", "").split("#")[0])
        if target:
            titles.setdefault(target, label.strip())
    return titles


def _open(path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise EpubBroken(f"{path.name} is not a zip") from exc
