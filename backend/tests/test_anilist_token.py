"""A token AniList no longer accepts.

AniList answers a revoked token with a 400 and a GraphQL body saying
"Invalid token". Read only by status, that was a bare `400 Bad Request` retried
three times over half an hour, when the only thing that helps is signing in
again.
"""

import httpx
import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import base as handlers_base
from app.providers.anilist import AniListSource
from app.providers.base import TokenRejected, WriteRefused
from app.queue import repo
from app.worker.runner import run_job

pytestmark = pytest.mark.asyncio

INVALID_TOKEN = {"data": None, "errors": [{"message": "Invalid token", "status": 400}]}


def _source(status: int, body: dict) -> AniListSource:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    return AniListSource(client=httpx.AsyncClient(transport=transport))


async def test_a_rejected_token_names_the_fix():
    with pytest.raises(TokenRejected, match="reconnect AniList"):
        await _source(400, INVALID_TOKEN).fetch_list("revoked")


async def test_a_rejected_token_on_a_write_is_not_a_refused_write():
    # WriteRefused makes progress pushing retry without the volume; a dead
    # token would be refused identically, so it must not look like one.
    with pytest.raises(TokenRejected) as caught:
        await _source(400, INVALID_TOKEN).push_progress("revoked", "1", 5)
    assert not isinstance(caught.value, WriteRefused)


async def test_an_unauthorised_status_is_a_rejected_token():
    with pytest.raises(TokenRejected):
        await _source(401, {"errors": [{"message": "Unauthorized."}]}).fetch_list("revoked")


async def test_any_other_bad_request_is_left_alone():
    body = {"data": None, "errors": [{"message": "Syntax Error", "status": 400}]}
    with pytest.raises(httpx.HTTPStatusError):
        await _source(400, body).fetch_list("fine")


@pytest.fixture
async def clean_queue():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job, job_event restart identity cascade"))
        await session.commit()


async def test_the_worker_does_not_retry_a_rejected_token(clean_queue, monkeypatch):
    async def rejects(ctx):
        raise TokenRejected("AniList rejected the stored token; reconnect AniList")

    monkeypatch.setitem(handlers_base._REGISTRY, JobType.LIST_SYNC, rejects)
    async with get_sessionmaker()() as session:
        job_id = await repo.enqueue(session, JobType.LIST_SYNC, {"provider": "anilist"})
        await session.commit()
        job = await repo.lease(session, types=types_for(Lane.FETCH))
        await session.commit()
    assert job is not None and job.id == job_id

    await run_job(job)

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text("select state, permanent, last_error from job where id = :id"),
                {"id": job_id},
            )
        ).one()
    assert (row.state, row.permanent) == ("failed", True)
    assert "reconnect AniList" in row.last_error
