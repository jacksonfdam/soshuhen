"""What an import will write, and why any file is left out.

The preview shows this plan and the job recomputes it from the same staged
files, so the user's review and the write can never disagree about a file.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.downloader.paths import chapter_filename, volume_filename
from app.importer.numbering import Edition, ReadVolume

Status = Literal["ready", "exists", "conflict", "unreadable", "duplicate"]


@dataclass(frozen=True)
class Existing:
    chapters: frozenset[Decimal]
    volumes: frozenset[tuple[Decimal, Edition]]


@dataclass(frozen=True)
class Override:
    volume: Decimal | None = None
    edition: Edition | None = None
    replace: bool = False


@dataclass
class PlannedFile:
    name: str
    sha256: str
    volume: Decimal | None
    edition: Edition
    chapters: list[Decimal]
    outputs: list[str]
    status: Status
    reason: str | None = None
    titles: list[str | None] = field(default_factory=list)


def _repeated(numbers: list[Decimal]) -> Decimal | None:
    seen: set[Decimal] = set()
    for number in numbers:
        if number in seen:
            return number
        seen.add(number)
    return None


def plan_import(
    slug: str,
    files: list[tuple[str, str, ReadVolume | None]],
    existing: Existing,
    overrides: dict[str, Override],
) -> list[PlannedFile]:
    planned: list[PlannedFile] = []
    hashes: set[str] = set()
    volumes: set[tuple[Decimal, Edition]] = set()
    chapters_in_drop: dict[Decimal, str] = {}

    for name, sha256, read in files:
        override = overrides.get(sha256, Override())
        if read is None:
            planned.append(
                PlannedFile(name, sha256, None, override.edition or "web", [], [], "unreadable",
                            "no bookmarks or no text; a scanned PDF cannot be imported")
            )
            continue

        volume = override.volume if override.volume is not None else read.volume
        edition: Edition = override.edition or read.edition
        is_web = edition == "web"
        numbers = [c.number for c in read.chapters] if is_web else []
        titles = [c.title for c in read.chapters] if is_web else []
        outputs = (
            [chapter_filename(slug, c.number, c.title, kind="prose") for c in read.chapters]
            if is_web
            else [volume_filename(slug, volume)] if volume is not None else []
        )
        item = PlannedFile(name, sha256, volume, edition, numbers, outputs, "ready", None, titles)
        planned.append(item)

        if sha256 in hashes:
            item.status, item.reason = "duplicate", "the same file is already in this drop"
        elif volume is None:
            item.status, item.reason = "conflict", "no volume number"
        elif (volume, edition) in volumes:
            item.status, item.reason = "duplicate", f"another file in this drop is {edition} volume {volume}"
        elif (twice := _repeated(numbers)) is not None:
            item.status, item.reason = "conflict", f"chapter {twice} appears twice in this file"
        elif (clash := next((n for n in numbers if n in chapters_in_drop), None)) is not None:
            item.status, item.reason = (
                "conflict", f"chapter {clash} is also in {chapters_in_drop[clash]}"
            )
        elif not override.replace and (
            (volume, edition) in existing.volumes or any(n in existing.chapters for n in numbers)
        ):
            item.status, item.reason = "exists", "the library already has it"

        hashes.add(sha256)
        if item.status in ("ready", "exists"):
            if volume is not None:
                volumes.add((volume, edition))
            for number in numbers:
                chapters_in_drop.setdefault(number, name)

    return planned
