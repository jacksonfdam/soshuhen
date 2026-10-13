"""The reader's pure pieces and the schema they rest on."""

import pytest
from sqlalchemy import text

from app import settings_store
from app.db import get_sessionmaker
from app.enums import ChapterState, JobType, Lane, ProgressSource, lane_of

pytestmark = pytest.mark.asyncio


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
