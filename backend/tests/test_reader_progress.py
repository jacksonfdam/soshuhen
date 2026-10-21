"""Finishing a chapter in the reader moves the lists and Komga forward."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import komga_read_progress, progress_write
from app.handlers.base import JobContext
from app.queue import repo

EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, series, list_entry restart identity cascade")
        )
        await session.commit()


async def _series_at(progress: int | None, *, total: int | None = None) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('S', 's-progress', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        if progress is not None:
            await session.execute(
                text(
                    "insert into list_entry (provider, provider_media_id, series_id,"
                    " title_romaji, synonyms, raw, status, user_progress_chapter, total_chapters)"
                    " values ('local', :m, :s, 'S', '[]'::jsonb, '{}'::jsonb, 'reading', :p, :t)"
                ),
                {"m": str(series_id), "s": series_id, "p": progress, "t": total},
            )
        await session.commit()
    return int(series_id)


async def _chapter(series_id: int, number: str, book: str | None = None) -> int:
    async with get_sessionmaker()() as session:
        chapter_id = (
            await session.execute(
                text(
                    "insert into chapter (series_id, number, state, komga_book_id)"
                    " values (:s, :n, 'known', :b) returning id"
                ),
                {"s": series_id, "n": Decimal(number), "b": book},
            )
        ).scalar_one()
        await session.commit()
    return int(chapter_id)


async def _jobs(job_type: JobType) -> list[dict]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text("select payload from job where type = :t order by id"), {"t": str(job_type)}
        )
        return [row[0] for row in rows.all()]


async def test_completing_a_chapter_queues_a_reader_progress_write(client):
    series_id = await _series_at(3)
    chapter_id = await _chapter(series_id, "5")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body == {"progress_queued": True, "komga_queued": False}
    assert await _jobs(JobType.PROGRESS_WRITE) == [
        {"series_id": series_id, "chapter": 5, "source": "reader"}
    ]


async def test_completing_a_chapter_behind_the_lists_queues_nothing(client):
    """Read in Mihon up to 15, then reread 10 here: the lists must stay at 15."""
    series_id = await _series_at(15)
    chapter_id = await _chapter(series_id, "10")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body["progress_queued"] is False
    assert await _jobs(JobType.PROGRESS_WRITE) == []


async def test_a_fractional_chapter_completes_its_whole_number(client):
    series_id = await _series_at(22)
    chapter_id = await _chapter(series_id, "23.5")
    await client.post(f"/api/reader/chapters/{chapter_id}/complete")
    assert (await _jobs(JobType.PROGRESS_WRITE))[0]["chapter"] == 23


async def test_a_chapter_past_the_counted_ceiling_is_still_written(client):
    """The ceiling counts chapter rows, which is a guard against a typed number.

    A source that only lists chapters 100 to 120 has 21 rows, and the reader
    finishing chapter 110 is proof the chapter exists, not a typo.
    """
    series_id = await _series_at(3, total=4)
    chapter_id = await _chapter(series_id, "9")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body["progress_queued"] is True


async def test_a_series_on_no_list_queues_no_progress(client):
    series_id = await _series_at(None)
    chapter_id = await _chapter(series_id, "1")
    body = (await client.post(f"/api/reader/chapters/{chapter_id}/complete")).json()
    assert body["progress_queued"] is False


async def test_completing_an_unknown_chapter_is_404(client):
    assert (await client.post("/api/reader/chapters/999999/complete")).status_code == 404


async def test_completing_queues_komga_only_with_a_book_id(client):
    series_id = await _series_at(0)
    indexed = await _chapter(series_id, "1", book="book-1")
    unindexed = await _chapter(series_id, "2")
    assert (await client.post(f"/api/reader/chapters/{indexed}/complete")).json()["komga_queued"]
    second = await client.post(f"/api/reader/chapters/{unindexed}/complete")
    assert not second.json()["komga_queued"]
    assert await _jobs(JobType.KOMGA_READ_PROGRESS) == [{"book_id": "book-1"}]


async def test_progress_write_records_the_reader_as_the_source():
    series_id = await _series_at(1)
    async with get_sessionmaker()() as session:
        await repo.enqueue(
            session,
            JobType.PROGRESS_WRITE,
            {"series_id": series_id, "chapter": 2, "source": "reader"},
            series_id=series_id,
        )
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await progress_write.handle(JobContext(session=session, job=job))
        await session.commit()
        source = (
            await session.execute(
                text("select source from progress_event where series_id = :s"), {"s": series_id}
            )
        ).scalar_one()
    assert source == "reader"


class FakeKomga:
    has_credentials = True

    def __init__(self):
        self.marked: list[tuple[str, bool]] = []

    async def set_read_progress(self, book_id: str, *, page: int, completed: bool) -> None:
        self.marked.append((book_id, completed))


async def test_the_komga_job_marks_the_book_read(monkeypatch):
    fake = FakeKomga()
    monkeypatch.setattr(komga_read_progress, "from_settings", lambda: fake)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.KOMGA_READ_PROGRESS, {"book_id": "book-9"})
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await komga_read_progress.handle(JobContext(session=session, job=job))
    assert fake.marked == [("book-9", True)]


async def _run_progress_write() -> None:
    async with get_sessionmaker()() as session:
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await progress_write.handle(JobContext(session=session, job=job))
        await session.commit()


async def _events(series_id: int) -> list[tuple[int, datetime, datetime]]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text(
                "select chapter, created_at, now() as db_now from progress_event"
                " where series_id = :s order by id"
            ),
            {"s": series_id},
        )
        return [(int(r.chapter), r.created_at, r.db_now) for r in rows.all()]


async def test_a_completion_with_read_at_records_that_time(client):
    series_id = await _series_at(3)
    chapter_id = await _chapter(series_id, "4")
    read_at = datetime.now(UTC) - timedelta(days=2)
    await client.post(
        f"/api/reader/chapters/{chapter_id}/complete", json={"read_at": read_at.isoformat()}
    )
    await _run_progress_write()
    [(chapter, created_at, _)] = await _events(series_id)
    assert (chapter, created_at) == (4, read_at)


async def test_a_completion_without_a_body_still_works(client):
    series_id = await _series_at(3)
    chapter_id = await _chapter(series_id, "4")
    response = await client.post(f"/api/reader/chapters/{chapter_id}/complete")
    assert response.json()["progress_queued"] is True
    assert "read_at" not in (await _jobs(JobType.PROGRESS_WRITE))[0]


async def test_replayed_out_of_order_keeps_the_higher_chapter_with_its_time(client):
    """Offline, 4 then 5 were read; the queue replays 5 first, then 4."""
    series_id = await _series_at(3)
    four = await _chapter(series_id, "4")
    five = await _chapter(series_id, "5")
    t1 = datetime.now(UTC) - timedelta(hours=3)
    t2 = datetime.now(UTC) - timedelta(hours=2)
    await client.post(f"/api/reader/chapters/{five}/complete", json={"read_at": t2.isoformat()})
    await client.post(f"/api/reader/chapters/{four}/complete", json={"read_at": t1.isoformat()})
    [payload] = await _jobs(JobType.PROGRESS_WRITE)
    assert (payload["chapter"], payload["read_at"]) == (5, t2.isoformat())
    await _run_progress_write()
    [(chapter, created_at, _)] = await _events(series_id)
    assert (chapter, created_at) == (5, t2)


async def test_a_raised_chapter_carries_its_own_time(client):
    """4 at t1 is waiting; 5 at t2 raises it, and the time must move with it."""
    series_id = await _series_at(3)
    four = await _chapter(series_id, "4")
    five = await _chapter(series_id, "5")
    t1 = datetime.now(UTC) - timedelta(hours=3)
    t2 = datetime.now(UTC) - timedelta(hours=2)
    await client.post(f"/api/reader/chapters/{four}/complete", json={"read_at": t1.isoformat()})
    await client.post(f"/api/reader/chapters/{five}/complete", json={"read_at": t2.isoformat()})
    [payload] = await _jobs(JobType.PROGRESS_WRITE)
    assert (payload["chapter"], payload["read_at"]) == (5, t2.isoformat())


async def test_a_future_completion_time_is_clamped(client):
    series_id = await _series_at(3)
    chapter_id = await _chapter(series_id, "4")
    future = datetime.now(UTC) + timedelta(days=1)
    await client.post(
        f"/api/reader/chapters/{chapter_id}/complete", json={"read_at": future.isoformat()}
    )
    await _run_progress_write()
    [(_, created_at, db_now)] = await _events(series_id)
    assert created_at <= db_now
