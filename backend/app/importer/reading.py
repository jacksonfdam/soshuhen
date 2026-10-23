"""From staged files to a plan, the one path both the preview and the job take."""

import hashlib
from decimal import Decimal

from app.importer.numbering import ReadVolume, number_book, volume_from_filename
from app.importer.pdf import UnreadablePdf, read_pdf
from app.importer.plan import Existing, Override, PlannedFile, plan_import


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_files(
    files: list[tuple[str, str, bytes]], *, known_max: Decimal | None
) -> list[tuple[str, str, ReadVolume | None]]:
    """Read every file, in volume order, so a light novel volume is recognised by
    restarting at 1 after the web chapters dropped alongside it."""
    order = sorted(
        files, key=lambda f: (volume_from_filename(f[0]) is None, volume_from_filename(f[0]) or 0)
    )
    read: dict[str, ReadVolume | None] = {}
    for name, sha256, data in order:
        try:
            volume = number_book(read_pdf(data), name, known_max=known_max)
        except UnreadablePdf:
            read[sha256] = None
            continue
        read[sha256] = volume
        if volume.edition == "web" and volume.chapters:
            highest = max(c.number for c in volume.chapters)
            known_max = highest if known_max is None else max(known_max, highest)
    return [(name, sha256, read[sha256]) for name, sha256, _ in files]


def build_plan(
    slug: str,
    files: list[tuple[str, str, bytes]],
    existing: Existing,
    overrides: dict[str, Override],
) -> tuple[list[PlannedFile], dict[str, ReadVolume | None]]:
    known_max = max(existing.chapters) if existing.chapters else None
    read = read_files(files, known_max=known_max)
    return plan_import(slug, read, existing, overrides), {sha: volume for _, sha, volume in read}
