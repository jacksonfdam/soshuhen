"""The reader's pure pieces and the schema they rest on."""

import os
import time
import zipfile

import pytest
from sqlalchemy import text

from app import settings_store
from app.db import get_sessionmaker
from app.downloader.limits import reader_semaphore, source_semaphore
from app.enums import ChapterState, JobType, Lane, ProgressSource, lane_of
from app.handlers import reader_cache
from app.reader import archive, cache
from app.reader import pages as page_json
from app.sources.base import PageRef


async def test_the_reader_tables_exist():
    async with get_sessionmaker()() as session:
        for table in ("reading_position", "series_reader_pref", "chapter_page_list"):
            found = await session.execute(
                text("select to_regclass(:name) is not null"), {"name": table}
            )
            assert found.scalar_one(), table


async def test_the_new_states_and_job_are_named():
    assert ChapterState.STREAMING == "streaming"
    assert ProgressSource.READER == "reader"
    # A short write to Komga; it must never wait behind archives.
    assert lane_of(JobType.KOMGA_READ_PROGRESS) is Lane.FETCH


async def test_reader_defaults_have_packaged_values():
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from setting where key like 'reader_default_%'"))
        await session.commit()
        assert await settings_store.get(session, settings_store.READER_DEFAULT_MODE) == "paged_rtl"
        assert (
            await settings_store.get(session, settings_store.READER_DEFAULT_SCALE) == "fit_screen"
        )
        assert (
            await settings_store.get(session, settings_store.READER_DEFAULT_BACKGROUND) == "black"
        )


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _cbz(path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_page_names_are_images_in_natural_order(tmp_path):
    """Komga-adopted archives were not written by us: `Page 10` must not sort
    before `Page 2`, and ComicInfo.xml or a folder entry is not a page."""
    path = _cbz(
        tmp_path / "c.cbz",
        {
            "ComicInfo.xml": b"<x/>",
            "pages/": b"",
            "pages/Page 10.jpg": JPEG + b"10",
            "pages/Page 2.jpg": JPEG + b"2",
            "pages/Page 1.png": PNG,
        },
    )
    assert archive.page_names(path) == [
        "pages/Page 1.png",
        "pages/Page 2.jpg",
        "pages/Page 10.jpg",
    ]


def test_read_page_returns_bytes_and_their_real_format(tmp_path):
    path = _cbz(tmp_path / "c.cbz", {"001.jpg": JPEG, "002.jpg": PNG})
    data, extension = archive.read_page(path, 1)
    assert data == PNG
    # The extension comes from the bytes, not the member name.
    assert extension == "png"


def test_read_page_past_the_end_raises_index_error(tmp_path):
    path = _cbz(tmp_path / "c.cbz", {"001.jpg": JPEG})
    with pytest.raises(IndexError):
        archive.read_page(path, 1)


def test_inside_refuses_a_path_outside_the_library(tmp_path):
    library = tmp_path / "manga"
    library.mkdir()
    assert archive.inside(library / "a" / "b.cbz", library)
    assert not archive.inside(tmp_path / "elsewhere.cbz", library)
    assert not archive.inside(library / ".." / "elsewhere.cbz", library)


def test_cache_writes_finds_counts_and_reads_back(tmp_path):
    cache.write_page(tmp_path, 7, 0, JPEG)
    cache.write_page(tmp_path, 7, 2, PNG)
    assert cache.find_page(tmp_path, 7, 0).name == "000.jpg"
    assert cache.find_page(tmp_path, 7, 1) is None
    assert cache.cached_count(tmp_path, 7) == 2
    assert cache.read_all(tmp_path, 7, 3) == [JPEG, None, PNG]


def test_cache_counts_nothing_for_a_chapter_never_streamed(tmp_path):
    assert cache.cached_count(tmp_path, 99) == 0


def test_a_half_written_page_is_neither_found_nor_counted(tmp_path):
    directory = tmp_path / "7"
    directory.mkdir()
    (directory / "tmpabc.part").write_bytes(JPEG[:3])
    assert cache.cached_count(tmp_path, 7) == 0
    assert cache.find_page(tmp_path, 7, 0) is None


def test_remove_deletes_the_chapter_directory(tmp_path):
    cache.write_page(tmp_path, 7, 0, JPEG)
    cache.remove(tmp_path, 7)
    assert not (tmp_path / "7").exists()
    cache.remove(tmp_path, 7)  # Removing twice is not an error.


def test_stale_chapters_are_judged_by_their_newest_page(tmp_path):
    now = time.time()
    cache.write_page(tmp_path, 1, 0, JPEG)
    cache.write_page(tmp_path, 2, 0, JPEG)
    old = now - 8 * 86400
    for path in [*(tmp_path / "1").iterdir(), tmp_path / "1"]:
        os.utime(path, (old, old))
    (tmp_path / "not-a-chapter").mkdir()
    assert cache.stale_chapters(tmp_path, 7 * 86400, now=now) == [1]


def test_stale_chapters_of_a_missing_root_is_empty(tmp_path):
    assert cache.stale_chapters(tmp_path / "absent", 1) == []


def test_page_refs_round_trip_through_json():
    original = [
        PageRef(url="https://a/1.jpg", headers={"Referer": "https://a/"}),
        PageRef(url="/2.jpg"),
    ]
    assert page_json.load(page_json.dump(original)) == original


async def test_the_reader_has_one_slot_of_its_own_per_site():
    """A download batch holds its slot for the whole batch; sharing those would
    leave someone staring at a blank page for minutes."""
    reader = await reader_semaphore("site-a")
    assert reader is await reader_semaphore("site-a")
    assert reader is not await source_semaphore("site-a", 2)
    assert reader._value == 1


async def test_a_stored_page_list_round_trips():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', 's-pages', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state)"
                    " values (:s, 1, 'known') returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        assert await reader_cache.stored_page_list(session, chapter_id) is None

        listed = [PageRef(url="/1.jpg"), PageRef(url="/2.jpg", headers={"Referer": "x"})]
        await reader_cache.store_page_list(session, chapter_id, listed)
        await reader_cache.store_page_list(session, chapter_id, listed[:1])
        await session.commit()

        assert await reader_cache.stored_page_list(session, chapter_id) == listed[:1]


def test_mac_metadata_and_hidden_files_are_not_pages(tmp_path):
    """An archive zipped on a Mac carries __MACOSX/._001.jpg beside every page.
    Counted as pages they shift the order and are not images at all."""
    path = _cbz(
        tmp_path / "c.cbz",
        {
            "001.jpg": JPEG,
            "__MACOSX/._001.jpg": b"\x00\x05\x16\x07",
            ".hidden.jpg": b"junk",
            "002.jpg": PNG,
        },
    )
    assert archive.page_names(path) == ["001.jpg", "002.jpg"]
