"""Put the J-Novel Club catalogue row back, using migration 0021's own SQL.

test_catalogue_repo truncates site_catalogue, and the session-wide migration
runs once, so any module after it would find no J-Novel Club row and no source
in the registry - green alone, red in the full suite. Replaying the migration's
statements, rather than a copy of them, keeps this honest about what 0021 seeds.
"""

import importlib.util
from pathlib import Path

from app.db import get_sessionmaker
from app.sources import registry

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0021_seed_jnovelclub.py"


def _migration():
    spec = importlib.util.spec_from_file_location("seed_jnovelclub_0021", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def seed_jnovelclub() -> None:
    migration = _migration()
    async with get_sessionmaker()() as session:
        await session.execute(migration.CATALOGUE)
        await session.execute(migration.PREFERENCE)
        await session.commit()
        await registry.reload(session)
