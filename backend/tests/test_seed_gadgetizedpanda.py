"""Migration 0030 seeds Gadgetized Panda as an enabled native source."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_gadgetizedpanda_is_seeded_enabled_and_native():
    # Other modules truncate site_catalogue, so the migration's own inserts are
    # replayed first; they are idempotent and are what is under test.
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0030_seed_gadgetizedpanda.py"
    spec = importlib.util.spec_from_file_location("seed_gadgetizedpanda", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from source_pref where key = :k"), {"k": migration.KEY})
        await session.execute(text("delete from site_catalogue where key = :k"), {"k": migration.KEY})
        await session.execute(migration.CATALOGUE, migration.ROW)
        await session.execute(migration.PREFERENCE, {"key": migration.KEY})
        await session.commit()
        row = (
            await session.execute(
                text(
                    """
                    select c.key, c.template, c.base_url, p.enabled
                      from site_catalogue c join source_pref p on p.key = c.key
                     where c.key = 'gadgetizedpanda'
                    """
                )
            )
        ).one()
    assert (row.key, row.template, row.base_url, row.enabled) == (
        "gadgetizedpanda",
        "native",
        "https://gadgetizedpanda.net",
        True,
    )


def test_the_catalogue_key_is_the_registered_site():
    from app.sources.registry import NATIVE_SOURCES

    assert NATIVE_SOURCES["gadgetizedpanda"].site == "gadgetizedpanda"
