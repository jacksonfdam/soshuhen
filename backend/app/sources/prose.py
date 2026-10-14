"""Reduce a site's chapter HTML to the XHTML an EPUB can carry.

Each source cuts away its own chrome first - ads, navigation, translator
banners - because only it knows what those look like. What is left still comes
from a site nobody here controls, so this keeps an allowlist rather than a
blocklist: a tag nobody thought of is unwrapped, never passed through.
"""

import html
import re
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser, Node

from app.sources.base import ChapterUnavailable

INLINE = {"em", "strong", "i", "b"}
BLOCK = {"p", "blockquote", "h1", "h2", "h3", "h4", "ul", "ol", "li"}
VOID = {"br", "hr"}
# Dropped with everything inside them. Unwrapping a script would print its
# source into the chapter.
DROPPED = {"script", "style", "iframe", "noscript", "form", "button", "svg", "nav", "aside",
           "template", "select", "textarea", "input"}
# Containers a site uses for layout. Unwrapped, or turned into a paragraph
# when they hold no block of their own - several sites put each paragraph in
# a bare div, and unwrapping those would run the whole chapter together.
CONTAINERS = {"div", "section", "article", "main", "center"}
# XML 1.0 refuses these outright, and a single one makes the EPUB unreadable.
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
_BLOCK_OPEN = re.compile(r"^<(p|blockquote|h[1-4]|ul|ol|li|hr)\b")


def clean_chapter_html(fragment: str, base_url: str) -> tuple[str, list[str]]:
    """The chapter as XHTML, and the image URLs it references, in order."""
    # NUL goes before parsing, not after: selectolax repeats the text that
    # follows one ("a\x00b" parses to "abb"), which no later pass can undo.
    tree = HTMLParser(fragment.replace("\x00", ""))
    root = tree.body or tree.root
    images: list[str] = []
    pieces = _children(root, images, base_url)
    body = "".join(_wrap_loose(pieces)).strip()

    if not _has_content(body):
        raise ChapterUnavailable("the chapter has no text once the page around it is removed")
    return body, images


def _children(node: Node, images: list[str], base_url: str) -> list[str]:
    out: list[str] = []
    for child in node.iter(include_text=True):
        out.extend(_render(child, images, base_url))
    return out


def _render(node: Node, images: list[str], base_url: str) -> list[str]:
    tag = node.tag
    if tag == "-text":
        return [_text(node.text(deep=False))]
    if tag in DROPPED or tag == "_comment":
        return []
    if tag in VOID:
        return [f"<{tag}/>"]
    if tag == "img":
        src = node.attributes.get("data-src") or node.attributes.get("src")
        if not src:
            return []
        resolved = urljoin(base_url, src)
        # An inline data: or javascript: image is not a fetchable address, and
        # fetch_pages would fail the whole batch on it with a bare ConnectError.
        # Dropped here rather than kept as a placeholder nothing can resolve.
        if urlparse(resolved).scheme not in ("http", "https"):
            return []
        images.append(resolved)
        return [f"{{{{img:{len(images) - 1}}}}}"]

    inner = _children(node, images, base_url)
    if tag in INLINE:
        content = "".join(inner)
        return [f"<{tag}>{content}</{tag}>"] if content.strip() else inner
    if tag in BLOCK:
        content = "".join(inner).strip()
        if tag == "p" and not _has_content(content):
            return []
        return [f"<{tag}>{content}</{tag}>"]
    if tag in CONTAINERS and not any(_BLOCK_OPEN.match(piece) for piece in inner):
        content = "".join(inner).strip()
        return [f"<p>{content}</p>"] if _has_content(content) else []
    return inner


def _text(value: str | None) -> str:
    cleaned = _INVALID_XML.sub("", (value or "").replace("\xa0", " "))
    # A literal `{{img:N}}` in the chapter text would otherwise be resolved as one of
    # our image placeholders, or fail the EPUB when no such image exists.
    return html.escape(cleaned, quote=False).replace("{", "&#123;")


def _wrap_loose(pieces: list[str]) -> list[str]:
    """Wrap runs of top-level inline content in a paragraph.

    Text sitting directly in the chapter container, separated by <br>, is how
    a good half of these sites lay a chapter out.
    """
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        content = "".join(run).strip()
        while content.endswith("<br/>"):
            content = content.removesuffix("<br/>").rstrip()
        if content and (re.sub(r"<[^>]+>", "", content).strip() or "{{img:" in content):
            # A run that is nothing but one image stays bare: an <img> may sit
            # directly in <body>, and wrapping it adds a blank line around it.
            if re.fullmatch(r"\{\{img:\d+\}\}", content):
                out.append(content)
            else:
                out.append(f"<p>{content}</p>")
        run.clear()

    for piece in pieces:
        if _BLOCK_OPEN.match(piece):
            flush()
            out.append(piece)
        else:
            run.append(piece)
    flush()
    return out


def _has_content(markup: str) -> bool:
    if "{{img:" in markup:
        return True
    text_only = re.sub(r"<[^>]+>", "", markup)
    return bool(text_only.strip())
