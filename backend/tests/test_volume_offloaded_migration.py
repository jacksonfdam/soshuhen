"""A volume can be offloaded: its file left the server for a device that holds it."""

from sqlalchemy import text

from app.db import get_sessionmaker


async def test_volume_accepts_offloaded_state():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta, kind)"
                    " values ('Novel', 'novel', false, '{}'::jsonb, 'prose') returning id"
                )
            )
        ).scalar_one()
        volume_id = (
            await session.execute(
                text(
                    "insert into volume (series_id, number, source_volume_id, status, state)"
                    " values (:s, 1, 'V1', 'owned', 'downloaded') returning id"
                ),
                {"s": series_id},
            )
        ).scalar_one()
        await session.execute(
            text("update volume set state = 'offloaded' where id = :id"), {"id": volume_id}
        )
        await session.commit()
        state = (
            await session.execute(text("select state from volume where id = :id"), {"id": volume_id})
        ).scalar_one()
    assert state == "offloaded"
