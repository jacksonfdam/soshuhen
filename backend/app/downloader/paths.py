"""Where a chapter file belongs on disk.

The layout is chosen so Komga parses series and chapter number without help:
one folder per series, four-digit zero-padded chapter numbers so lexical order
matches numeric order.
"""

import re
from decimal import Decimal
from pathlib import Path

from app.text_utils import slugify

_UNSAFE = re.compile(r"[^\w\s.\-]", re.UNICODE)
MAX_TITLE_LENGTH = 80


def format_number(number: Decimal) -> str:
    """0012 for chapter 12, 0012.5 for a half chapter."""
    integral = int(number)
    if number == integral:
        return f"{integral:04d}"
    fraction = format(number.normalize(), "f").split(".")[1]
    return f"{integral:04d}.{fraction}"


def safe_component(value: str) -> str:
    cleaned = _UNSAFE.sub("", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:MAX_TITLE_LENGTH].strip(" .")


# The stem is the same for both kinds, so ordering, the number parsed back out
# of a Komga filename and the reconcile-by-path logic never learn that two
# formats exist.
_EXTENSIONS = {"comic": "cbz", "prose": "epub"}
ARCHIVE_SUFFIXES = (".cbz", ".epub")


def chapter_filename(
    series_slug: str, number: Decimal, title: str | None = None, *, kind: str = "comic"
) -> str:
    stem = f"{series_slug} - Ch.{format_number(number)}"
    if title:
        safe = safe_component(title)
        if safe:
            stem = f"{stem} - {safe}"
    return f"{stem}.{_EXTENSIONS.get(kind, 'cbz')}"


def series_dir(library_root: Path, series_slug: str) -> Path:
    return library_root / slugify(series_slug)


def chapter_path(
    library_root: Path,
    series_slug: str,
    number: Decimal,
    title: str | None = None,
    *,
    kind: str = "comic",
) -> Path:
    return series_dir(library_root, series_slug) / chapter_filename(
        series_slug, number, title, kind=kind
    )


def existing_chapter_file(
    library_root: Path, series_slug: str, number: Decimal, title: str | None
) -> Path | None:
    """A chapter already in the library, in whichever format it was written.

    Both formats count. A series whose kind is corrected after files exist
    must not redownload a backlog the library already holds, and a file
    written before a title was known carries no title suffix.
    """
    for kind in _EXTENSIONS:
        for candidate_title in (title, None):
            path = chapter_path(library_root, series_slug, number, candidate_title, kind=kind)
            if path.exists():
                return path
    return None


_NUMBER_IN_NAME = re.compile(r"\bCh\.(\d+(?:\.\d+)?)")


def number_from_filename(filename: str) -> Decimal | None:
    """Inverse of the naming rule, for files Komga reports that we did not place."""
    match = _NUMBER_IN_NAME.search(filename)
    return Decimal(match.group(1)) if match else None


def volume_filename(series_slug: str, number: Decimal, title: str | None = None) -> str:
    """A whole volume, named apart from the chapters beside it.

    `Vol.` rather than `Ch.` so number_from_filename never reads a volume as a
    chapter: reconciliation matches books to chapter rows by that number, and
    volume 16 would otherwise claim chapter 16's row.
    """
    stem = f"{series_slug} - Vol.{format_number(number)}"
    if title:
        safe = safe_component(title)
        if safe:
            stem = f"{stem} - {safe}"
    return f"{stem}.epub"


def volume_path(
    library_root: Path, series_slug: str, number: Decimal, title: str | None = None
) -> Path:
    return series_dir(library_root, series_slug) / volume_filename(series_slug, number, title)


_VOLUME_IN_NAME = re.compile(r"\bVol\.(\d+(?:\.\d+)?)")


def volume_number_from_filename(filename: str) -> Decimal | None:
    """Inverse of volume_filename, for the books Komga reports."""
    match = _VOLUME_IN_NAME.search(filename)
    return Decimal(match.group(1)) if match else None
