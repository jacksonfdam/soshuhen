"""Mihon's backup file (`.tachibk`): read and written, as far as Soshuhen has use for it.

The field numbers come from Mihon's own models, read on 2026-10-23 from
app/src/main/java/eu/kanade/tachiyomi/data/backup/models/ in mihonapp/mihon:
Backup, BackupManga, BackupChapter, BackupTracking and BackupSource. The file
is that Backup message, gzipped (BackupCreator writes it through okio's gzip
sink). Fields this module does not name are skipped on reading and left out on
writing; Mihon gives every one of them a default.

Pure: bytes in, dataclasses out, and back. Matching a backup against the library
is app/api/routes_backup.py's job.
"""

import gzip
import hashlib
from dataclasses import dataclass, field

from app.mihon import protobuf as pb

# TrackerManager in Mihon. These are the three Soshuhen also writes to.
TRACKER_MAL = 1
TRACKER_ANILIST = 2
TRACKER_MANGABAKA = 11


@dataclass
class MihonChapter:
    url: str
    name: str
    number: float = 0.0
    read: bool = False
    bookmark: bool = False


@dataclass
class MihonTracking:
    tracker: int
    media_id: int
    url: str = ""
    title: str = ""
    last_chapter_read: float = 0.0
    status: int = 0


@dataclass
class MihonManga:
    source_id: int
    url: str
    title: str = ""
    thumbnail_url: str | None = None
    favorite: bool = True
    chapters: list[MihonChapter] = field(default_factory=list)
    tracking: list[MihonTracking] = field(default_factory=list)


@dataclass
class MihonBackup:
    mangas: list[MihonManga] = field(default_factory=list)
    #: source id -> the name Mihon showed for it
    sources: dict[int, str] = field(default_factory=dict)


def source_id(name: str, lang: str, version: int = 1) -> int:
    """The id Mihon gives an HttpSource: HttpSource.generateId.

    The first eight bytes of the MD5 of "name/lang/version", big-endian, with
    the sign bit cleared. An extension that overrides `id` or `versionId`
    gets another number, and the catalogue records neither.
    """
    digest = hashlib.md5(f"{name.lower()}/{lang}/{version}".encode(), usedforsecurity=False).digest()
    return int.from_bytes(digest[:8], "big") & (2**63 - 1)


def _text(raw: int | bytes) -> str:
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""


def _chapter(data: bytes) -> MihonChapter:
    chapter = MihonChapter(url="", name="")
    for number, wire, raw in pb.fields(data):
        match number:
            case 1:
                chapter.url = _text(raw)
            case 2:
                chapter.name = _text(raw)
            case 4 if wire == pb.VARINT:
                chapter.read = bool(raw)
            case 5 if wire == pb.VARINT:
                chapter.bookmark = bool(raw)
            case 9 if wire == pb.FIXED32:
                chapter.number = pb.float32(raw)  # type: ignore[arg-type]
    return chapter


def _tracking(data: bytes) -> MihonTracking:
    track = MihonTracking(tracker=0, media_id=0)
    legacy_id = 0
    for number, wire, raw in pb.fields(data):
        match number:
            case 1 if wire == pb.VARINT:
                track.tracker = int(raw)  # type: ignore[arg-type]
            case 3 if wire == pb.VARINT:
                legacy_id = int(raw)  # type: ignore[arg-type]
            case 4:
                track.url = _text(raw)
            case 5:
                track.title = _text(raw)
            case 6 if wire == pb.FIXED32:
                track.last_chapter_read = pb.float32(raw)  # type: ignore[arg-type]
            case 9 if wire == pb.VARINT:
                track.status = int(raw)  # type: ignore[arg-type]
            case 100 if wire == pb.VARINT:
                track.media_id = pb.signed64(int(raw))  # type: ignore[arg-type]
    # mediaIdInt (3) is what backups made before the Long field existed carry.
    if not track.media_id:
        track.media_id = legacy_id
    return track


def _manga(data: bytes) -> MihonManga:
    manga = MihonManga(source_id=0, url="")
    for number, wire, raw in pb.fields(data):
        match number:
            case 1 if wire == pb.VARINT:
                manga.source_id = pb.signed64(int(raw))  # type: ignore[arg-type]
            case 2:
                manga.url = _text(raw)
            case 3:
                manga.title = _text(raw)
            case 9:
                manga.thumbnail_url = _text(raw) or None
            case 16 if wire == pb.BYTES:
                manga.chapters.append(_chapter(raw))  # type: ignore[arg-type]
            case 18 if wire == pb.BYTES:
                manga.tracking.append(_tracking(raw))  # type: ignore[arg-type]
            case 100 if wire == pb.VARINT:
                manga.favorite = bool(raw)
    return manga


def read_backup(data: bytes) -> MihonBackup:
    """A .tachibk file's contents. Accepts it gzipped, as Mihon writes it, or bare."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    backup = MihonBackup()
    for number, wire, raw in pb.fields(data):
        if wire != pb.BYTES:
            continue
        if number == 1:
            backup.mangas.append(_manga(raw))  # type: ignore[arg-type]
        elif number == 101:
            name, sid = "", 0
            for inner, inner_wire, value in pb.fields(raw):  # type: ignore[arg-type]
                if inner == 1:
                    name = _text(value)
                elif inner == 2 and inner_wire == pb.VARINT:
                    sid = pb.signed64(int(value))  # type: ignore[arg-type]
            backup.sources[sid] = name
    return backup


def write_backup(backup: MihonBackup) -> bytes:
    """The gzipped file Mihon restores."""
    out = bytearray()
    for manga in backup.mangas:
        body = bytearray()
        body += pb.varint(1, manga.source_id)
        body += pb.string(2, manga.url)
        body += pb.string(3, manga.title)
        if manga.thumbnail_url:
            body += pb.string(9, manga.thumbnail_url)
        for chapter in manga.chapters:
            inner = (
                pb.string(1, chapter.url)
                + pb.string(2, chapter.name)
                + pb.varint(4, chapter.read)
                + pb.varint(5, chapter.bookmark)
                + pb.float_(9, chapter.number)
            )
            body += pb.string(16, inner)
        for track in manga.tracking:
            inner = (
                pb.varint(1, track.tracker)
                + pb.varint(2, 0)
                + pb.string(4, track.url)
                + pb.string(5, track.title)
                + pb.float_(6, track.last_chapter_read)
                + pb.varint(9, track.status)
                + pb.varint(100, track.media_id)
            )
            body += pb.string(18, inner)
        body += pb.varint(100, manga.favorite)
        out += pb.string(1, bytes(body))
    for sid, name in backup.sources.items():
        out += pb.string(101, pb.string(1, name) + pb.varint(2, sid))
    return gzip.compress(bytes(out))
