"""Finishing a light novel volume in the reader moves the lists, forward only."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import komga_read_progress, progress_push
from app.handlers.base import JobContext
from app.queue import repo
from tests.test_volume_progress_push import FakeKomgaClient, RecordingProvider, _book

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


async def _exec(statement: str, params: dict | None = None):
    async with get_sessionmaker()() as session:
        result = await session.execute(text(statement), params or {})
        await session.commit()
        return result


async def _series(volume_progress: int | None = None) -> int:
    series_id = (
        await _exec(
            "insert into series (canonical_title, slug, needs_review, meta, kind, komga_series_id)"
            " values ('Moon', 'moon', false, '{}'::jsonb, 'prose', 'K') returning id"
        )
    ).scalar_one()
    await _exec(
        "insert into list_entry (provider, provider_media_id, series_id, synonyms, status,"
        " user_progress_chapter, user_progress_volume, raw)"
        " values ('local', 'L1', :s, '[]'::jsonb, 'reading', 0, cast(:v as integer),"
        " '{}'::jsonb)",
        {"s": series_id, "v": volume_progress},
    )
    return int(series_id)


async def _volume(series_id: int, number: int, *, edition: str = "light",
                  book: str | None = None) -> int:
    return int(
        (
            await _exec(
                "insert into volume (series_id, number, source_volume_id, status, state,"
                " edition, komga_book_id)"
                " values (:s, :n, :v, 'owned', 'downloaded', :e, :b) returning id",
                {"s": series_id, "n": number, "v": f"import:{number}{edition}", "e": edition,
                 "b": book},
            )
        ).scalar_one()
    )


async def _payloads(job_type: JobType) -> list[dict]:
    rows = await _exec("select payload from job where type = :t order by id", {"t": str(job_type)})
    return [row[0] for row in rows.all()]


async def test_a_light_volume_with_a_komga_book_queues_the_mark_and_the_push(client):
    series_id = await _series()
    volume_id = await _volume(series_id, 2, book="V2")
    response = await client.post(f"/api/reader/volumes/{volume_id}/complete")
    assert response.json() == {"progress_queued": True, "komga_queued": True}
    assert await _payloads(JobType.KOMGA_READ_PROGRESS) == [
        {"book_id": "V2", "push_series_id": series_id}
    ]


async def test_read_at_is_accepted(client):
    series_id = await _series()
    volume_id = await _volume(series_id, 2, book="V2")
    response = await client.post(
        f"/api/reader/volumes/{volume_id}/complete", json={"read_at": "2026-10-24T08:00:00Z"}
    )
    assert response.status_code == 200


async def test_a_volume_komga_never_indexed_queues_nothing(client):
    series_id = await _series()
    volume_id = await _volume(series_id, 2)
    response = await client.post(f"/api/reader/volumes/{volume_id}/complete")
    assert response.json() == {"progress_queued": False, "komga_queued": False}
    assert await _payloads(JobType.KOMGA_READ_PROGRESS) == []


async def test_a_web_volume_is_finished_through_its_chapters(client):
    series_id = await _series()
    volume_id = await _volume(series_id, 2, edition="web")
    assert (await client.post(f"/api/reader/volumes/{volume_id}/complete")).status_code == 409


async def test_an_unknown_volume_is_not_found(client):
    assert (await client.post("/api/reader/volumes/999/complete")).status_code == 404


class FakeKomga:
    has_credentials = True

    def __init__(self):
        self.marked: list[str] = []

    async def set_read_progress(self, book_id: str, *, page: int, completed: bool) -> None:
        self.marked.append(book_id)


async def _run_mark(monkeypatch, payload: dict) -> FakeKomga:
    fake = FakeKomga()
    monkeypatch.setattr(komga_read_progress, "from_settings", lambda: fake)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.KOMGA_READ_PROGRESS, payload)
        await session.commit()
        job = await repo.lease(session, types=[str(JobType.KOMGA_READ_PROGRESS)])
        await session.commit()
        await komga_read_progress.handle(JobContext(session=session, job=job))
        await session.commit()
    return fake


async def test_the_mark_queues_one_progress_push_after_komga_has_it(monkeypatch):
    series_id = await _series()
    fake = await _run_mark(monkeypatch, {"book_id": "V2", "push_series_id": series_id})
    await _run_mark(monkeypatch, {"book_id": "V3", "push_series_id": series_id})
    assert fake.marked == ["V2"]
    assert await _payloads(JobType.PROGRESS_PUSH) == [{"series_id": series_id}]


async def test_a_chapter_mark_queues_no_push(monkeypatch):
    await _run_mark(monkeypatch, {"book_id": "C1"})
    assert await _payloads(JobType.PROGRESS_PUSH) == []


async def test_rereading_an_earlier_volume_lowers_no_list(monkeypatch):
    series_id = await _series(volume_progress=10)
    await _volume(series_id, 3, book="V3")
    provider = RecordingProvider()
    monkeypatch.setattr(progress_push, "from_settings", lambda: FakeKomgaClient([_book("V3")]))
    monkeypatch.setattr(progress_push, "get_source", lambda p: provider)

    async def token(session, p):
        return "t"

    monkeypatch.setattr(progress_push, "access_token_for", token)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.PROGRESS_PUSH, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        await session.commit()
        await progress_push.handle(JobContext(session=session, job=job))
        await session.commit()
    assert provider.calls == []
    stored = await _exec("select user_progress_volume from list_entry")
    assert stored.scalar_one() == 10


async def test_a_prose_chapter_finishes_like_a_comic_one(client):
    series_id = await _series()
    chapter_id = (
        await _exec(
            "insert into chapter (series_id, number, state, komga_book_id)"
            " values (:s, 5, 'downloaded', 'C5') returning id",
            {"s": series_id},
        )
    ).scalar_one()
    response = await client.post(f"/api/reader/chapters/{chapter_id}/complete")
    assert response.json() == {"progress_queued": True, "komga_queued": True}
    assert await _payloads(JobType.PROGRESS_WRITE) == [
        {"series_id": series_id, "chapter": 5, "source": "reader"}
    ]
