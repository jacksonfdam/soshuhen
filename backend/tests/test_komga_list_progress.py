"""Komga learns what was read anywhere else: in Soshuhen's reader before it
had indexed the chapter, or in Mihon through the lists."""

from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import komga_scan
from app.handlers.base import JobContext
from app.queue import repo

EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


class Book:
    def __init__(self, book_id: str, path: str, completed: bool = False):
        self.id = book_id
        self.path = path
        self.completed = completed

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]


class FakeKomga:
    has_credentials = True

    def __init__(self, books):
        self.books = books
        self.marked: list[str] = []

    async def ensure_library(self, name, path):
        return "lib-1"

    async def scan_library(self, library_id):
        return None

    async def find_series(self, root, slug, library_id):
        return "komga-series-1"

    async def books_of_series(self, series_id):
        return self.books

    async def set_read_progress(self, book_id, *, page, completed):
        self.marked.append(book_id)


async def _series(progress: int | None) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, chapter, series, list_entry restart identity cascade")
        )
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('K', 'k-progress', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        if progress is not None:
            await session.execute(
                text(
                    "insert into list_entry (provider, provider_media_id, series_id,"
                    " title_romaji, synonyms, raw, status, user_progress_chapter)"
                    " values ('local', :m, :s, 'K', '[]'::jsonb, '{}'::jsonb, 'reading', :p)"
                ),
                {"m": str(series_id), "s": series_id, "p": progress},
            )
        for number in (1, 2, 3):
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, file_path)"
                    " values (:s, :n, 'downloaded', :p)"
                ),
                {"s": series_id, "n": number, "p": f"/manga/k/c{number}.cbz"},
            )
        await session.commit()
    return int(series_id)


async def _scan(monkeypatch, series_id, client):
    monkeypatch.setattr(komga_scan, "SCAN_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(komga_scan, "from_settings", lambda: client)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await komga_scan.handle(JobContext(session=session, job=job))
        await session.commit()


def _books(read: frozenset[str] = frozenset()):
    return [Book(f"b{n}", f"/manga/k/c{n}.cbz", completed=f"b{n}" in read) for n in (1, 2, 3)]


async def test_books_up_to_list_progress_are_marked_read(monkeypatch):
    series_id = await _series(2)
    client = FakeKomga(_books())
    await _scan(monkeypatch, series_id, client)
    assert client.marked == ["b1", "b2"]


async def test_a_book_komga_already_has_as_read_is_not_marked_again(monkeypatch):
    series_id = await _series(2)
    client = FakeKomga(_books(read=frozenset({"b1"})))
    await _scan(monkeypatch, series_id, client)
    assert client.marked == ["b2"]


async def test_a_series_with_no_progress_marks_nothing(monkeypatch):
    series_id = await _series(None)
    client = FakeKomga(_books())
    await _scan(monkeypatch, series_id, client)
    assert client.marked == []
