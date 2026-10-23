"""The .tachibk codec: what Soshuhen writes, it reads back, and it reads what kotlinx writes."""

import gzip

from app.mihon import protobuf as pb
from app.mihon.backup import (
    TRACKER_ANILIST,
    MihonBackup,
    MihonChapter,
    MihonManga,
    MihonTracking,
    read_backup,
    source_id,
    write_backup,
)


def test_the_source_id_is_mihons():
    # MangaDex (English) as Mihon lists it: HttpSource.generateId("MangaDex", "en", 1).
    assert source_id("MangaDex", "en") == 2499283573021220255


def test_a_backup_survives_a_round_trip():
    original = MihonBackup(
        mangas=[
            MihonManga(
                source_id=source_id("MangaDex", "en"),
                url="/manga/abc",
                title="Frieren",
                thumbnail_url="https://x.test/c.jpg",
                chapters=[
                    MihonChapter(url="/chapter/1", name="Chapter 1", number=1.0, read=True),
                    MihonChapter(url="/chapter/2", name="Chapter 2.5", number=2.5, bookmark=True),
                ],
                tracking=[
                    MihonTracking(
                        tracker=TRACKER_ANILIST,
                        media_id=118586,
                        url="https://anilist.co/manga/118586",
                        title="Frieren",
                        last_chapter_read=1.0,
                        status=1,
                    )
                ],
            )
        ],
        sources={source_id("MangaDex", "en"): "MangaDex"},
    )

    data = write_backup(original)

    assert data[:2] == b"\x1f\x8b"
    assert read_backup(data) == original


def test_a_bare_message_reads_too():
    data = gzip.decompress(write_backup(MihonBackup(mangas=[MihonManga(source_id=1, url="/a")])))
    assert read_backup(data).mangas[0].url == "/a"


def test_unknown_fields_are_skipped_and_the_legacy_media_id_is_used():
    tracking = pb.varint(1, TRACKER_ANILIST) + pb.varint(2, 0) + pb.varint(3, 42)
    manga = (
        pb.varint(1, 7)
        + pb.string(2, "/m")
        + pb.string(7, "Action")  # genre, which this module does not keep
        + pb.varint(13, 1700000000000)  # dateAdded
        + pb.string(18, tracking)
        + pb.string(112, b"{}")  # memo
    )
    backup = read_backup(pb.string(1, manga) + pb.string(2, pb.string(1, "Default")))

    assert backup.mangas[0].tracking[0].media_id == 42
    assert backup.mangas[0].source_id == 7


def test_a_source_id_with_the_top_bit_set_reads_back_signed():
    # Mihon clears the sign bit for generated ids, but a source may set its own.
    assert read_backup(write_backup(MihonBackup(mangas=[MihonManga(source_id=-5, url="/")]))).mangas[
        0
    ].source_id == -5


def test_packed_varints_decode():
    assert pb.packed_varints(bytes([1, 0x96, 0x01, 3])) == [1, 150, 3]
