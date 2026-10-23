"""The import job: staged PDFs into the library's files and rows.

It runs on the download lane because it writes /manga. Everything it writes
looks like a downloaded chapter or an owned volume, so Komga, reconciliation and
the readers need nothing new to pick it up - and it never marks anything read.
"""

import zipfile
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.downloader.paths import chapter_path, volume_path
from app.enums import JobType, Lane, types_for
from app.handlers import import_files
from app.handlers.base import JobContext, PermanentError
from app.importer import staging
from app.importer.reading import sha256_of
from app.queue import repo
from tests.pdf_fixture import make_pdf

SLUG = "tsukimichi"
WEB_1 = (
    "WN - Tsukimichi - Volume 01.pdf",
    [("Cover", ["c"]), ("Prologue 1", ["Start."]), ("Chapter 1 Road", ["One."]), ("Chapter 2", ["Two."])],
)
WEB_2 = ("WN - Tsukimichi - Volume 02.pdf", [("Chapter 3", ["Three."]), ("Chapter 4", ["Four."])])
LIGHT_1 = ("LN - Tsukimichi - Volume 01.pdf", [("Chapter 1", ["Uno."]), ("Chapter 2", ["Dos."])])


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    (tmp_path / "manga").mkdir()
    (tmp_path / "cache").mkdir()
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "manga"))
    monkeypatch.setenv("READER_CACHE_PATH", str(tmp_path / "cache"))
    get_settings.cache_clear()
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, series, list_entry, chapter, volume restart identity cascade")
        )
        await session.commit()
    yield
    get_settings.cache_clear()


def library():
    return get_settings().library_path


async def a_series(session) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('Tsukimichi', :slug, false, '{}'::jsonb, 'prose') returning id"
            ),
            {"slug": SLUG},
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into list_entry (series_id, provider, provider_media_id, status,"
            " user_progress_chapter, synonyms, raw)"
            " values (:s, 'mal', '1', 'reading', 2, '[]'::jsonb, '{}'::jsonb)"
        ),
        {"s": series_id},
    )
    await session.commit()
    return int(series_id)


def stage(*books) -> str:
    files = []
    for name, entries in books:
        data = make_pdf(entries)
        files.append((name, sha256_of(data), data))
    return staging.stage(files)


async def run(session, series_id: int, token: str, overrides: dict | None = None) -> None:
    await repo.enqueue(
        session,
        JobType.IMPORT_FILES,
        {"series_id": series_id, "token": token, "overrides": overrides or {}},
    )
    await session.commit()
    job = await repo.lease(session, types=[*types_for(Lane.DOWNLOAD)])
    await session.commit()
    await import_files.handle(JobContext(session=session, job=job))
    await session.commit()


async def rows(session, sql: str, **params):
    return (await session.execute(text(sql), params)).all()


async def test_web_volume_writes_one_epub_per_chapter_and_a_volume_row():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await run(session, series_id, stage(WEB_1))

        chapters = await rows(session, "select number, title, state, file_path, source_url from chapter order by number")
        volume = (await rows(session, "select number, edition, first_part, last_part, file_path, state from volume"))[0]

    assert [c.number for c in chapters] == [Decimal("0.1"), Decimal(1), Decimal(2)]
    assert {c.state for c in chapters} == {"downloaded"}
    assert all(c.source_url is None for c in chapters)
    assert chapters[1].title == "Road"
    for chapter in chapters:
        expected = chapter_path(library(), SLUG, chapter.number, chapter.title, kind="prose")
        assert chapter.file_path == str(expected)
        assert zipfile.ZipFile(expected).read("mimetype") == b"application/epub+zip"
    assert (volume.number, volume.edition, volume.state) == (Decimal(1), "web", "downloaded")
    assert (volume.first_part, volume.last_part) == (Decimal("0.1"), Decimal(2))
    assert volume.file_path is None


async def test_light_volume_writes_one_volume_file_and_no_chapters():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await run(session, series_id, stage(LIGHT_1))

        chapters = await rows(session, "select id from chapter")
        volume = (await rows(session, "select number, edition, first_part, file_path, status from volume"))[0]

    assert chapters == []
    expected = volume_path(library(), SLUG, Decimal(1))
    assert (volume.number, volume.edition, volume.status) == (Decimal(1), "light", "owned")
    assert volume.first_part is None
    assert volume.file_path == str(expected)
    assert zipfile.ZipFile(expected).read("mimetype") == b"application/epub+zip"


async def test_both_editions_of_one_volume_are_imported_side_by_side():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await run(session, series_id, stage(WEB_1, LIGHT_1))

        editions = await rows(session, "select edition from volume where number = 1 order by edition")

    assert [v.edition for v in editions] == ["light", "web"]


async def test_import_marks_nothing_read():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        await run(session, series_id, stage(WEB_1, WEB_2))

        progress = await rows(session, "select user_progress_chapter from list_entry")
        jobs = {j.type for j in await rows(session, "select type from job where state = 'pending'")}

    assert progress[0].user_progress_chapter == 2
    assert jobs.isdisjoint({"progress_push", "progress_write", "list_write"})


async def test_import_enqueues_a_komga_scan_and_discards_the_staged_files():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        token = stage(WEB_2)
        await run(session, series_id, token)

        jobs = await rows(session, "select type from job where state = 'pending'")

    assert [j.type for j in jobs] == ["komga_scan"]
    assert staging.staged(token) is None


async def test_rerun_after_a_crash_is_idempotent():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        token = stage(WEB_1, WEB_2)
        await run(session, series_id, token)
        # The worker died after the first volume: the second never landed.
        await session.execute(text("delete from chapter where number >= 3"))
        await session.execute(text("delete from volume where number = 2"))
        await session.commit()
        retry = stage(WEB_1, WEB_2)

        await run(session, series_id, retry)

        count = (await rows(session, "select count(*) as n from chapter"))[0].n
        volumes = await rows(session, "select number from volume order by number")

    assert count == 5
    assert [v.number for v in volumes] == [Decimal(1), Decimal(2)]
    assert list(library().rglob("*.part")) == []


async def test_replace_removes_only_its_own_old_file():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        folder = library() / SLUG
        folder.mkdir()
        old = folder / f"{SLUG} - Ch.0003 - Old title.epub"
        old.write_bytes(b"old")
        neighbour = folder / f"{SLUG} - Ch.0004 - Keep.epub"
        neighbour.write_bytes(b"keep")
        await session.execute(
            text(
                "insert into chapter (series_id, number, title, state, file_path)"
                " values (:s, 3, 'Old title', 'downloaded', :p)"
            ),
            {"s": series_id, "p": str(old)},
        )
        await session.commit()
        data = make_pdf(WEB_2[1])
        token = staging.stage([(WEB_2[0], sha256_of(data), data)])

        await run(session, series_id, token, {sha256_of(data): {"volume": None, "edition": None, "replace": True}})

        chapter = (await rows(session, "select file_path from chapter where number = 3"))[0]

    assert not old.exists()
    assert chapter.file_path == str(chapter_path(library(), SLUG, Decimal(3), None, kind="prose"))
    assert neighbour.exists() or (folder / f"{SLUG} - Ch.0004.epub").exists()


async def test_staged_files_gone_is_permanent():
    async with get_sessionmaker()() as session:
        series_id = await a_series(session)
        with pytest.raises(PermanentError):
            await run(session, series_id, "gone")
