"""Migration 0020 seeds the prose natives, with EmpireNovel switched off."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_the_prose_natives_are_seeded_with_empirenovel_off():
    # Other modules truncate site_catalogue, so the migration's own inserts are
    # replayed first; they are idempotent and are what is under test.
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0020_seed_prose_sources.py"
    spec = importlib.util.spec_from_file_location("seed_prose_sources", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    keys = [site[0] for site in migration.SITES]
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from source_pref where key = any(:k)"), {"k": keys})
        await session.execute(text("delete from site_catalogue where key = any(:k)"), {"k": keys})
        for key, name, base_url, enabled in migration.SITES:
            await session.execute(
                migration.CATALOGUE, {"key": key, "name": name, "base_url": base_url}
            )
            await session.execute(migration.PREFERENCE, {"key": key, "enabled": enabled})
        await session.commit()
        rows = (
            await session.execute(
                text(
                    """
                    select c.key, c.template, p.enabled
                      from site_catalogue c join source_pref p on p.key = c.key
                     where c.key in ('lolobun', 'novelight', 'empirenovel')
                     order by c.key
                    """
                )
            )
        ).all()
    assert [(r.key, r.template, r.enabled) for r in rows] == [
        ("empirenovel", "native", False),
        ("lolobun", "native", True),
        ("novelight", "native", True),
    ]
