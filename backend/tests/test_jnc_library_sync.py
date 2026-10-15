"""The J-Novel Club library becomes volume rows, and new or revised ones download."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, lane_of


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
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
