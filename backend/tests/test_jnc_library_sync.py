"""The J-Novel Club library becomes volume rows, and new or revised ones download."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, lane_of
from app.handlers.base import JobContext
from app.handlers.jnc_library_sync import handle, needs_download, volume_news
from app.queue import repo
from app.sources.base import ProseSource, RegisteredSource, SignInRequired, install_registry
from app.sources.jnovelclub import OwnedVolume


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job, notification restart identity cascade"))
        await session.commit()


def test_volume_downloads_run_where_files_are_written():
    assert lane_of(JobType.VOLUME_DOWNLOAD) == Lane.DOWNLOAD
    assert lane_of(JobType.JNC_LIBRARY_SYNC) == Lane.FETCH


async def test_a_volume_is_unique_per_series_and_number():
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('A', 'a', false, '{}'::jsonb, 'prose') returning id"
                )
            )
        ).scalar_one()
        insert = text(
            "insert into volume (series_id, number, source_volume_id, status)"
            " values (:s, 16, :v, 'owned')"
        )
        await session.execute(insert, {"s": series_id, "v": "VOL-16"})
        with pytest.raises(Exception, match="unique|duplicate"):
            await session.execute(insert, {"s": series_id, "v": "VOL-OTHER"})

OLD = datetime(2026, 9, 1, tzinfo=UTC)
NEW = datetime(2026, 10, 1, tzinfo=UTC)


def test_what_needs_downloading():
    base = {"status": "owned", "has_link": True, "state": "known",
            "downloaded_updated": None, "last_updated": OLD}
    assert needs_download(**base)
    assert not needs_download(**{**base, "status": "preorder"})
    assert not needs_download(**{**base, "has_link": False})
    # In flight is the job table's to say (enqueue dedupes), not the row's.
    assert needs_download(**{**base, "state": "queued"})
    assert not needs_download(**{**base, "state": "downloaded", "downloaded_updated": OLD})
    assert needs_download(**{**base, "state": "downloaded", "downloaded_updated": OLD,
                             "last_updated": NEW})


class FakeJnc(ProseSource):
    site = "jnovelclub"
    domains = ("j-novel.club",)

    def __init__(self, owned=None, signed_in=True, ranges=None):
        self.owned = owned or []
        self.signed_in = signed_in
        self.ranges = ranges if ranges is not None else {Decimal(16): (Decimal(204), Decimal(216))}

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def fetch_chapter(self, chapter_url, *, language="en"):
        raise NotImplementedError

    async def library(self):
        if not self.signed_in:
            raise SignInRequired("J-Novel Club is not signed in")
        return self.owned

    async def part_ranges(self, series_slug):
        return self.ranges


def _owned(number=16, *, slug="the-apothecary-diaries", status="owned", updated=OLD):
    return OwnedVolume(slug, f"VOL-{number}", Decimal(number), f"Volume {number}", status,
                       updated, "https://cdn.example/v.epub?sig=x")


async def _mapped_series(session, slug="the-apothecary-diaries") -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta, kind)"
                " values ('The Apothecary Diaries', 'apothecary', false, '{}'::jsonb, 'prose')"
                " returning id"
            )
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active)"
            " values (:s, 'jnovelclub', :u, true)"
        ),
        {"s": series_id, "u": f"https://j-novel.club/series/{slug}"},
    )
    await session.commit()
    return int(series_id)


async def _run(session, source) -> JobContext:
    install_registry({"jnovelclub": RegisteredSource(source, "https://labs.j-novel.club")})
    await repo.enqueue(session, JobType.JNC_LIBRARY_SYNC, {})
    await session.commit()
    job = await repo.lease(session, types=[str(JobType.JNC_LIBRARY_SYNC)])
    await session.commit()
    ctx = JobContext(session=session, job=job)
    await handle(ctx)
    await session.commit()
    return ctx


async def _volumes(session):
    return (
        await session.execute(
            text("select number, status, state, first_part, last_part from volume order by number")
        )
    ).all()


async def _queued(session) -> int:
    return (
        await session.execute(text("select count(*) from job where type = 'volume_download'"))
    ).scalar_one()


async def test_an_owned_volume_of_a_mapped_series_is_recorded_and_queued():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        rows = await _volumes(session)
        assert [(r.number, r.status, r.state, r.first_part, r.last_part) for r in rows] == [
            (Decimal("16.00"), "owned", "queued", Decimal("204.00"), Decimal("216.00"))
        ]
        assert await _queued(session) == 1


async def test_a_preorder_is_recorded_but_not_queued():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned(status="preorder")]))
        assert [r.state for r in await _volumes(session)] == ["known"]
        assert await _queued(session) == 0


async def test_an_unmapped_series_is_reported_not_recorded():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        ctx = await _run(session, FakeJnc([_owned(slug="some-other-series")]))
        assert await _volumes(session) == []
        log = (
            await session.execute(
                text("select string_agg(message, ' ') from job_event where job_id = :j"),
                {"j": ctx.job.id},
            )
        ).scalar_one()
        assert "some-other-series" in log


async def test_not_signed_in_is_done_not_failed():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc(signed_in=False))
        assert await _volumes(session) == []


async def test_a_second_sync_with_nothing_new_queues_nothing():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        await session.execute(
            text(
                "update volume set state = 'downloaded', file_path = '/m/a.epub',"
                " downloaded_updated = :d"
            ),
            {"d": OLD},
        )
        await session.execute(text("delete from job where type = 'volume_download'"))
        await session.commit()
        await _run(session, FakeJnc([_owned()]))
        row = (await session.execute(text("select state, file_path from volume"))).one()
        assert (row.state, row.file_path) == ("downloaded", "/m/a.epub")
        assert await _queued(session) == 0


async def test_a_revised_volume_is_queued_again():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        await session.execute(
            text("update volume set state = 'downloaded', downloaded_updated = :d"), {"d": OLD}
        )
        await session.execute(text("delete from job where type = 'volume_download'"))
        await session.commit()
        await _run(session, FakeJnc([_owned(updated=NEW)]))
        assert [r.state for r in await _volumes(session)] == ["queued"]
        assert await _queued(session) == 1


async def test_a_volume_left_queued_without_a_job_is_queued_again():
    # "Cancel queue" deletes the job and leaves the row saying queued.
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        await session.execute(text("delete from job where type = 'volume_download'"))
        await session.commit()
        await _run(session, FakeJnc([_owned()]))
        assert await _queued(session) == 1


async def test_a_volume_already_waiting_is_not_queued_twice():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        await _run(session, FakeJnc([_owned()]))
        assert await _queued(session) == 1


async def test_a_number_taken_by_another_edition_skips_that_volume_only():
    async with get_sessionmaker()() as session:
        series_id = await _mapped_series(session)
        await session.execute(
            text(
                "insert into volume (series_id, number, source_volume_id, status)"
                " values (:s, 16, 'VOL-OLD-EDITION', 'owned')"
            ),
            {"s": series_id},
        )
        await session.commit()
        ctx = await _run(session, FakeJnc([_owned(16), _owned(17)]))
        numbers = (await session.execute(
            text("select number, source_volume_id from volume order by number")
        )).all()
        assert [(r.number, r.source_volume_id) for r in numbers] == [
            (Decimal("16.00"), "VOL-OLD-EDITION"), (Decimal("17.00"), "VOL-17"),
        ]
        log = (await session.execute(
            text("select string_agg(message, ' ') from job_event where job_id = :j"),
            {"j": ctx.job.id},
        )).scalar_one()
        assert "volume 16" in log


D = Decimal


def test_volume_news():
    assert volume_news(before=None, status="owned", last_part=D(216)).new_volume
    assert not volume_news(before=None, status="preorder", last_part=None).new_volume
    assert volume_news(before=("preorder", None), status="owned", last_part=D(216)).new_volume
    assert not volume_news(before=("owned", D(216)), status="owned", last_part=D(216)).new_volume
    assert volume_news(
        before=("owned", D(214)), status="owned", last_part=D(216)
    ).new_parts == (D(215), D(216))
    assert volume_news(before=("owned", D(216)), status="owned", last_part=D(216)).new_parts is None
    # A range unknown last time is not a range that grew.
    assert volume_news(before=("owned", None), status="owned", last_part=D(216)).new_parts is None


async def _notifications(session):
    return (
        await session.execute(
            text(
                "select kind, count, first_number, last_number, volume_number"
                " from notification order by id"
            )
        )
    ).all()


async def test_first_sync_of_a_series_records_nothing():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned()]))
        assert await _notifications(session) == []


async def test_a_newly_owned_volume_is_announced():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned(16)]))
        await _run(session, FakeJnc([_owned(16), _owned(17)]))
        assert await _notifications(session) == [
            ("volumes", 1, D("17.00"), D("17.00"), None)
        ]


async def test_a_preorder_is_not_news_until_it_is_owned():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned(16)]))
        await _run(session, FakeJnc([_owned(16), _owned(17, status="preorder")]))
        assert await _notifications(session) == []
        await _run(session, FakeJnc([_owned(16), _owned(17)]))
        assert [n.kind for n in await _notifications(session)] == ["volumes"]


async def test_new_parts_of_a_known_volume_are_announced():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned(16)], ranges={D(16): (D(204), D(214))}))
        await _run(session, FakeJnc([_owned(16)], ranges={D(16): (D(204), D(216))}))
        assert await _notifications(session) == [
            ("parts", 2, D("215.00"), D("216.00"), D("16.00"))
        ]


async def test_a_volume_skipped_for_its_number_announces_nothing():
    async with get_sessionmaker()() as session:
        await _mapped_series(session)
        await _run(session, FakeJnc([_owned(16)]))
        other_edition = OwnedVolume(
            "the-apothecary-diaries", "VOL-16-OTHER", D(16), "Volume 16", "owned", OLD,
            "https://cdn.example/v.epub?sig=y",
        )
        await _run(session, FakeJnc([_owned(16), other_edition]))
        assert await _notifications(session) == []
