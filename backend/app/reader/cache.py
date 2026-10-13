"""Where a streamed chapter's pages wait to become an archive.

One directory per chapter id, one file per page named by its index. Pages are
written to a scratch file and renamed into place, so the worker that builds
the archive never reads half a page.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from app.downloader.cbz import page_extension

_SCRATCH = ".part"


def chapter_dir(root: Path, chapter_id: int) -> Path:
    return root / str(chapter_id)


def write_page(root: Path, chapter_id: int, index: int, data: bytes) -> Path:
    directory = chapter_dir(root, chapter_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{index:03d}.{page_extension(data)}"
    handle, scratch = tempfile.mkstemp(dir=directory, suffix=_SCRATCH)
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    os.replace(scratch, destination)
    return destination


def find_page(root: Path, chapter_id: int, index: int) -> Path | None:
    directory = chapter_dir(root, chapter_id)
    if not directory.is_dir():
        return None
    for candidate in directory.glob(f"{index:03d}.*"):
        if not candidate.name.endswith(_SCRATCH):
            return candidate
    return None


def cached_count(root: Path, chapter_id: int) -> int:
    directory = chapter_dir(root, chapter_id)
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if not path.name.endswith(_SCRATCH))


def read_all(root: Path, chapter_id: int, page_count: int) -> list[bytes | None]:
    pages: list[bytes | None] = []
    for index in range(page_count):
        found = find_page(root, chapter_id, index)
        pages.append(found.read_bytes() if found is not None else None)
    return pages


def touch(root: Path, chapter_id: int) -> None:
    """A page served from the cache is still a chapter being read."""
    directory = chapter_dir(root, chapter_id)
    if directory.is_dir():
        os.utime(directory)


def remove(root: Path, chapter_id: int) -> None:
    shutil.rmtree(chapter_dir(root, chapter_id), ignore_errors=True)


def stale_chapters(root: Path, max_age_seconds: float, *, now: float | None = None) -> list[int]:
    """Chapters nobody has read from for longer than `max_age_seconds`.

    Judged by the newest file rather than the directory alone: writing a page
    updates the directory, but reading one back from the cache does not, and
    `touch` is what covers that case.
    """
    if not root.is_dir():
        return []
    current = time.time() if now is None else now
    stale: list[int] = []
    for directory in root.iterdir():
        if not directory.is_dir() or not directory.name.isdigit():
            continue
        newest = max(
            [directory.stat().st_mtime, *(path.stat().st_mtime for path in directory.iterdir())]
        )
        if current - newest > max_age_seconds:
            stale.append(int(directory.name))
    return sorted(stale)
