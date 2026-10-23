"""New chapters, newest first, for a screen that groups them by day.

"New" means found after its series was already being followed: a chapter is a
backlog chapter when it was inserted by the first discovery of one of its
series' mappings, and `chapter_discover` stamps the chapter and that mapping in
one transaction, so the two timestamps are equal for exactly those rows. A
series first mapped today would otherwise fill today with its whole history,
and so would every change of source.

Read from the chapter table rather than from `notification`, whose read rows
are deleted after thirty days and which holds a range, not the chapters in it.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session

router = APIRouter(prefix="/api/updates", tags=["updates"])

Session = Annotated[AsyncSession, Depends(db_session)]

# Enough for a screen a person scrolls; a library catching up after months
# offline is still bounded by it.
MAX_ROWS = 500


@router.get("")
async def updates(session: Session, days: Annotated[int, Query(ge=1, le=90)] = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            text(
                """
                select c.id, c.number, c.title, c.state, c.discovered_at,
                       s.id as series_id, s.canonical_title, s.kind
                  from chapter c
                  join series s on s.id = c.series_id
                 where c.discovered_at >= :since
                   and c.discovered_at > (
                       select min(m.discovered_at) from source_mapping m
                        where m.series_id = c.series_id
                   )
                   and not exists (
                       select 1 from source_mapping m
                        where m.series_id = c.series_id
                          and m.discovered_at = c.discovered_at
                   )
                 order by c.discovered_at desc, s.canonical_title, c.number desc
                 limit :limit
                """
            ),
            {"since": since, "limit": MAX_ROWS + 1},
        )
    ).all()

    return {
        "days": days,
        # One past the cap was asked for so the screen can say it stopped
        # short, rather than presenting a cut-off list as the whole period.
        "truncated": len(rows) > MAX_ROWS,
        "chapters": [
            {
                "id": row.id,
                "number": float(row.number),
                "title": row.title,
                "state": row.state,
                "discovered_at": row.discovered_at.isoformat(),
                "series_id": row.series_id,
                "series_title": row.canonical_title,
                "prose": row.kind == "prose",
            }
            for row in rows[:MAX_ROWS]
        ],
    }
