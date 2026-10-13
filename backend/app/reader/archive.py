"""Pages read straight out of a chapter archive already in the library.

Values in, values out: this takes a path and returns bytes, and never learns
which chapter the path belongs to.
"""

import re
import zipfile
from pathlib import Path

from app.downloader.cbz import page_extension

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")


def _natural(name: str) -> list[object]:
    # Archives Komga adopted were written by other tools, and plain sorting
    # puts "Page 10" before "Page 2".
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def page_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if _is_page(name)]
    return sorted(names, key=_natural)


def _is_page(name: str) -> bool:
    # An archive zipped on a Mac carries __MACOSX/._001.jpg beside every page:
    # resource forks with an image's name and no image inside. Counted, they
    # shift every page after them by one.
    if name.endswith("/") or name.startswith("__MACOSX/"):
        return False
    if name.rsplit("/", 1)[-1].startswith("."):
        return False
    return name.lower().endswith(_IMAGE_SUFFIXES)


def read_page(path: Path, index: int) -> tuple[bytes, str]:
    names = page_names(path)
    if not 0 <= index < len(names):
        raise IndexError(index)
    with zipfile.ZipFile(path) as archive:
        data = archive.read(names[index])
    return data, page_extension(data)


def inside(path: Path, root: Path) -> bool:
    """Whether a stored file path really points into the library.

    file_path is ours rather than the visitor's, but it is also what Komga
    reported, and serving whatever a row names is how a bad row becomes a file
    read anywhere on the host.
    """
    return path.resolve().is_relative_to(root.resolve())
