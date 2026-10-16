"""The bell: what discovery found new, and marking it read."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.notifications import announce_read

router = APIRouter(prefix="/api", tags=["notifications"])

Session = Annotated[AsyncSession, Depends(db_session)]


def _number(value: Any) -> float | None:
    # JSON numbers, not the strings a Decimal would serialise to: 128.5 has to
    # reach the panel as 128.5, not "128.50".
    return float(value) if value is not None else None


@router.get("/notifications")
async def list_notifications(
    session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 30
) -> dict[str, Any]:
    rows = (
        await session.execute(
            text(
                """
                select n.id, n.series_id, s.canonical_title, s.meta ->> 'cover_url' as cover_url,
                       n.kind, n.count, n.first_number, n.last_number, n.volume_number,
                       n.created_at, n.read_at
                  from notification n
                  join series s on s.id = n.series_id
                 order by n.created_at desc, n.id desc
                 limit :limit
                """
            ),
            {"limit": limit},
        )
    ).all()
    # Counted on its own: the badge is every unread row, not the unread rows
    # that happen to fit on this page.
    unread = (
        await session.execute(text("select count(*) from notification where read_at is null"))
    ).scalar_one()
    return {
        "items": [
            {
                "id": row.id,
                "series_id": row.series_id,
                "series_title": row.canonical_title,
                "cover_url": row.cover_url,
                "kind": row.kind,
                "count": row.count,
                "first_number": _number(row.first_number),
                "last_number": _number(row.last_number),
                "volume_number": _number(row.volume_number),
                "created_at": row.created_at.isoformat(),
                "read_at": row.read_at.isoformat() if row.read_at else None,
            }
            for row in rows
        ],
        "unread_count": unread,
    }


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: int, session: Session) -> dict[str, bool]:
    found = (
        await session.execute(
            text(
                "update notification set read_at = coalesce(read_at, now())"
                " where id = :id returning id"
            ),
            {"id": notification_id},
        )
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="no such notification")
    await announce_read(session, notification_id)
    await session.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(session: Session) -> dict[str, int]:
    marked = (
        await session.execute(
            text("update notification set read_at = now() where read_at is null")
        )
    ).rowcount
    await announce_read(session, None)
    await session.commit()
    return {"marked": marked}
