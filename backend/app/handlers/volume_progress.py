"""Which volume the reading in Komga amounts to, and what each list may be sent.

Pure: Komga books, volume rows and chapter rows in, numbers out. The handler
reads them and writes the result.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class VolumeRow:
    number: Decimal
    first_part: Decimal | None
    last_part: Decimal | None
    komga_book_id: str | None


def furthest_volume(
    books, volumes: list[VolumeRow], chapter_books: dict[Decimal, str | None]
) -> tuple[int | None, Decimal | None]:
    """The furthest volume read, and the last part it collects.

    A volume is read when its own book is finished, or when every part in its
    range is: each part has a chapter row, each row has a Komga book, and every
    one of those books is finished. A part never downloaded, or never even
    discovered, keeps the volume unread.

    Every list takes a whole count, so a half volume counts as the one below.
    """
    completed = {book.id for book in books if book.completed}
    best: VolumeRow | None = None
    for volume in volumes:
        if not (_book_read(volume, completed) or _parts_read(volume, completed, chapter_books)):
            continue
        if best is None or volume.number > best.number:
            best = volume
    if best is None:
        return None, None
    return int(best.number), best.last_part


def _book_read(volume: VolumeRow, completed: set[str]) -> bool:
    return volume.komga_book_id is not None and volume.komga_book_id in completed


def _parts_read(
    volume: VolumeRow, completed: set[str], chapter_books: dict[Decimal, str | None]
) -> bool:
    if volume.first_part is None or volume.last_part is None:
        return False
    in_range = [
        book for number, book in chapter_books.items()
        if volume.first_part <= number <= volume.last_part
    ]
    # Fewer rows than parts in the range means some part was never discovered.
    expected = int(volume.last_part - volume.first_part) + 1
    if len(in_range) < expected:
        return False
    return all(book is not None and book in completed for book in in_range)


def pushable_volume(read_volume: int | None, total: int | None, current: int | None) -> int | None:
    """The volume to send one list entry, or None when it would not move forward.

    Capped at the list's own total when it states one: no provider documents
    what it does with a count past it.
    """
    if read_volume is None:
        return None
    volume = min(read_volume, total) if total else read_volume
    return volume if volume > (current or 0) else None
